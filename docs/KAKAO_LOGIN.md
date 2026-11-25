# 카카오 로그인과 선수 연결

카카오 로그인으로 계정을 확인하고, 관리자가 기존 선수와 연결을 승인한다. 카카오 닉네임과 선수 이름이 같다는 이유로 자동 연결하거나 관리자 권한을 주지 않는다. 로그인하지 않아도 선수·일정·기록·기사를 볼 수 있다. 경기 조작은 연결 승인된 해당 일정 참석자 또는 기존 클럽 관리자에게 허용한다.

## 서버 설정

Kakao Developers에서 서비스에 사용할 앱을 만들고 카카오 로그인을 활성화한다. 앱의 REST API 키를 서버 `.env`의 `KAKAO_CLIENT_ID`에 넣는다. 클라이언트 시크릿을 활성화했다면 `KAKAO_CLIENT_SECRET`도 설정한다. 이메일·전화번호 수집은 필요하지 않다. 닉네임이 제공되지 않으면 화면에는 ‘카카오 회원’으로 표시한다.

카카오 콘솔의 Redirect URI와 아래 값을 문자 단위로 동일하게 등록한다.

```ini
KAKAO_CLIENT_ID=앱의_REST_API_키
KAKAO_CLIENT_SECRET=활성화했다면_클라이언트_시크릿
KAKAO_REDIRECT_URI=https://prefer.tail4eaf9e.ts.net/api/auth/kakao/callback
USER_TOKEN_TTL_MIN=10080
```

`SECRET_KEY`는 기존 서버의 32자 이상 임의 값을 유지한다. 키·시크릿은 프론트 `.env`나 Git에 넣지 않는다. 실제 값을 채운 뒤 백엔드를 다시 시작한다. 서버 주소가 변경되면 카카오 콘솔과 `.env`의 Redirect URI를 함께 변경한다.

로컬 개발은 다음처럼 프론트 개발 서버의 `/api` 프록시를 사용할 수 있다. 해당 URI도 카카오 콘솔에 등록한다.

```ini
KAKAO_REDIRECT_URI=http://localhost:5173/api/auth/kakao/callback
```

공개 주소는 HTTPS만 허용하며 HTTP는 localhost/127.0.0.1/::1 개발 주소만 허용한다. 운영 설정과 로컬 설정을 동시에 사용할 때는 별도 서버 환경으로 구분한다. 프론트·API는 같은 출처로 제공해야 한다.

## DB·프론트 반영

```powershell
cd C:\clubwire
.\.venv\Scripts\python.exe -m alembic upgrade head
cd frontend
npm ci
npm run build
```

`0016`은 `APP_USER`, `MEMBER_ACCOUNT_LINK`, `MEMBER_LINK_REQUEST`와 `MATCH_EVENT.USER_ID`를 추가한다. 기존 선수·경기·관리자 PIN은 유지한다.

## 이용 흐름

1. 일반 사용자가 클럽의 계정 화면에서 ‘카카오 로그인’을 누른다.
2. 카카오 로그인 후 본인에 해당하는 기존 선수를 선택하고 연결을 신청한다.
3. 클럽 관리자가 회원 연결 관리에서 실제 본인 여부를 확인하고 승인하거나 거절한다.
4. 승인된 사용자 중 해당 일정 참석자만 경기 조작이 가능하다. 관리자 첫 경기 시작·기록 확정·일정 마감 규칙은 유지한다.
5. 잘못 승인했거나 연결을 바꿀 때는 관리자가 기존 연결을 해제한다. 권한은 다음 API 요청부터 즉시 회수된다.

하나의 카카오 계정은 클럽마다 한 선수에 연결할 수 있다. 한 선수에 두 계정을 승인할 수 없다. 로그인만 했거나 승인 대기 중인 계정에는 경기 조작 권한이 없다. 휴면/비활성 또는 삭제된 선수는 승인 연결이 남아 있어도 경기 조작 권한이 없다. 로그아웃하면 같은 계정의 기존 앱 세션도 모두 만료된다.

## API

| 경로 | 권한·응답 |
|---|---|
| `GET /api/auth/kakao/login?clubSlug=ypr` | 활성 클럽 확인 후 카카오 인증 화면으로 이동 |
| `GET /api/auth/kakao/callback` | state 확인 → 코드 교환 → 카카오 ID 확인 → 앱 세션 쿠키 발급 |
| `GET /api/auth/me` | `{configured, user, csrfToken}`. 사용자 없으면 user/csrfToken은 null |
| `POST /api/auth/logout` | 사용자 쿠키와 `X-CSRF-Token` 필요 |
| `GET /api/clubs/{slug}/account` | 로그인 정보 + 해당 클럽의 승인된 link/최근 request |
| `POST /api/clubs/{slug}/account/link` | 로그인 사용자, `{memberId}`, 승인 신청 |
| `DELETE /api/clubs/{slug}/account/link` | 자신의 대기 중 신청 취소 |
| `GET /api/clubs/{slug}/admin/accounts` | 관리자, 대기 중 requests와 승인된 links |
| `POST /api/clubs/{slug}/admin/accounts/{requestId}/approve` | 관리자 승인 |
| `POST /api/clubs/{slug}/admin/accounts/{requestId}/reject` | 관리자 거절 |
| `DELETE /api/clubs/{slug}/admin/accounts/{linkId}` | 관리자 승인 연결 해제 |

사용자 세션은 HttpOnly·SameSite=Lax 쿠키에 저장하고, HTTPS에서는 Secure를 적용한다. 카카오 access/refresh token은 DB나 프론트 저장소에 보관하지 않는다. 쿠키로 인증하는 쓰기 요청은 `/api/auth/me`에서 받은 CSRF 토큰을 `X-CSRF-Token`으로 전송한다. 관리자 Bearer 토큰은 별도의 ADMIN 역할로 검증한다.

OAuth state는 브라우저별 서명된 10분 쿠키와 비교하고 콜백 후 제거한다. 로그인 후 이동 경로는 확인된 클럽의 `/c/{slug}/account`로 고정하며 외부 redirect URL을 받지 않는다. 인증 관련 응답은 캐시하지 않는다.

## 확인

자동 테스트는 카카오 응답을 모의 처리하여 state 누락/불일치/만료, 사용자 취소, 로그인 쿠키, CSRF, 로그아웃 후 세션 재사용 차단, 선수 연결 승인·취소·거절·해제, 다른 클럽 접근 차단을 확인한다. 카카오 앱 키를 설정한 실제 로그인 왕복은 운영 도메인에서 별도로 확인한다. 카카오 앱이 개발 중 상태라면 콘솔 정책에 따라 등록된 테스트 사용자만 로그인할 수 있으므로 서비스 이용 가능 상태도 확인한다.
