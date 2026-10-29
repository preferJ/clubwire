# Clubwire API 목록

> 자동 생성(OpenAPI). 상세 스키마는 서버 실행 후 `/docs` 또는 `docs/openapi.json`.  
> 클럽 API는 공통 접두사 `/api/clubs/{club_slug}`를 생략해 표시합니다. `/api/admin/...`는 슈퍼관리자 API의 전체 경로입니다.
> 인증: 🔓 공개 / 🔑 관리자(Bearer 토큰). 클럽 관리자는 `POST /api/clubs/{club_slug}/admin/auth`, 슈퍼관리자는 `POST /api/admin/auth`로 각각 로그인합니다.

| 인증 | Method | Path | 설명 |
|:---:|---|---|---|
| 🔓 | GET | `/` | 클럽 정보(공개) |
| 🔓 | POST | `/admin/auth` | 관리자 모드 진입(PIN 입력 → 토큰) |
| 🔑 | GET | `/admin/config` | 운영 설정 조회 |
| 🔑 | PATCH | `/admin/config` | 운영 설정 변경(이력/버전 기록) |
| 🔑 | GET | `/admin/config/history` | 설정 변경 이력 |
| 🔑 | PATCH | `/admin/content` | 운영수칙·상단 공지 수정 |
| 🔑 | GET | `/admin/me` | 관리자 모드 확인 |
| 🔑 | POST | `/admin/pin` | 관리자 암호 변경 |
| 🔓 | GET | `/content` | 운영수칙과 상단 공지(공개) |
| 🔓 | GET | `/summary` | 클럽 요약(공개): 활동 멤버 · 올해 일정 · 올해 기사 수 |
| 🔓 | GET | `/members` | 멤버 목록(공개) |
| 🔑 | POST | `/members` | 멤버 등록 |
| 🔑 | PATCH | `/members/{member_id}` | 멤버 수정/비활성화(active=false). 가입일·출생연도·등번호는 null로 지울 수 있음. 삭제는 하지 않음 |
| 🔓 | GET | `/sessions` | 일정 목록(관리자: 예정/완료/삭제 구분) |
| 🔑 | POST | `/sessions` | 일정 생성 |
| 🔑 | DELETE | `/sessions/{session_id}` | 일정 삭제(관리자 보관함으로 이동, 완료 기록 보존) |
| 🔓 | GET | `/sessions/{session_id}` | 일정 상세(참석자/팀/경기) — 공개, 관리자는 팀 전력 Snapshot 포함 |
| 🔑 | PATCH | `/sessions/{session_id}` | 일정 수정 |
| 🔑 | POST | `/sessions/{session_id}/cancel` | 일정 취소(경기 시작 전만) |
| 🔑 | POST | `/sessions/{session_id}/close` | [일정마감] 수정 잠금 → 자동 타이틀/통계/마감 기사 |
| 🔑 | POST | `/sessions/{session_id}/guests` | 게스트 추가(인원수에만 포함) |
| 🔑 | DELETE | `/sessions/{session_id}/guests/{guest_id}` | 게스트 제외 |
| 🔑 | POST | `/sessions/{session_id}/members` | 참석자 등록 |
| 🔑 | DELETE | `/sessions/{session_id}/members/{member_id}` | 참석 취소(ABSENT 처리) |
| 🔓 | GET | `/sessions/{session_id}/summary` | 오늘 기록 요약(팀 성적, 득점/도움 상위, 미확정 경기 수) |
| 🔓 | GET | `/sessions/{session_id}/teams` | 세션 팀 명단(공개) |
| 🔑 | GET | `/sessions/{session_id}/teams/assignments` | 수동 변경 이력 |
| 🔑 | POST | `/sessions/{session_id}/teams/assignments` | 확정 후 수동 변경(ADD 지각/MOVE 이동/REMOVE 제외) |
| 🔑 | POST | `/sessions/{session_id}/teams/confirm` | [일정확정] 팀 확정 → PRE_MATCH 기사 생성 |
| 🔑 | POST | `/sessions/{session_id}/teams/generate` | 자동 팀 편성 미리보기(여러 번 가능) |
| 🔓 | GET | `/live` | 진행/대기 중인 경기(공개, 홈 LIVE 배너용) |
| 🔓 | GET | `/matches/{match_id}` | 경기 상태 + 이벤트 타임라인(공개). 새 클라이언트는 이걸로 타이머 복원 |
| 🔑 | POST | `/matches/{match_id}/cancel` | 경기 취소 |
| 🔑 | POST | `/matches/{match_id}/end` | 경기 종료(관리자) |
| 🔑 | POST | `/matches/{match_id}/events/{event_id}/cancel` | 골 취소(삭제하지 않고 취소 이벤트 기록) |
| 🔑 | POST | `/matches/{match_id}/finalize` | 기록 확정 → Rating/Stats/Pair 반영(중복 호출 409) |
| 🔑 | POST | `/matches/{match_id}/goals` | 골 등록(+점수 동시 반영, 멱등키 지원) |
| 🔑 | POST | `/matches/{match_id}/members` | 출전 명단 추가/팀 변경(교체 투입 등) |
| 🔑 | DELETE | `/matches/{match_id}/members/{member_id}` | 출전 명단 제외(결장) |
| 🔑 | POST | `/matches/{match_id}/pause` | 일시정지 |
| 🔑 | POST | `/matches/{match_id}/resume` | 재개 |
| 🔑 | POST | `/matches/{match_id}/start` | 경기 시작(출전 명단/전력 Snapshot 생성) |
| 🔑 | POST | `/matches/{match_id}/unfinalize` | 확정 해제(일정마감 전까지) |
| 🔑 | POST | `/sessions/{session_id}/matches/next` | 다음 경기 생성(READY). 두 팀은 관리자가 지정 |
| 🔑 | GET | `/sessions/{session_id}/matches/next-suggestion` | 다음 경기 대진 화면용: 팀별 경기 수 + 추천 대진 |
| 🔑 | POST | `/admin/rebuild` | [관리자] Rating/통계/Pair 전체 재계산 |
| 🔓 | GET | `/stats/members` | 개인 통계 목록(공개) |
| 🔓 | GET | `/stats/members/{member_id}` | 개인 상세 통계: 최근 폼, 자주 같은 팀, 자주 만난 상대(공개) |
| 🔓 | GET | `/stats/mvp-race` | 이달의 MVP 후보 1~3위(실력 점수 상승률 %만, 점수 자체는 비공개) + 지난달 MVP(공개) |
| 🔓 | GET | `/stats/pairs` | 두 선수 관계(같이 뛴 기록 / 상대 전적, 공개) |
| 🔓 | GET | `/titles/awards` | 타이틀 수여 이력(공개) |
| 🔑 | POST | `/titles/awards` | 타이틀 수여(수동 타이틀. 기본 타이틀은 모두 자동 집계) |
| 🔑 | POST | `/titles/awards/{member_title_id}/cancel` | 타이틀 수여 취소 |
| 🔓 | GET | `/titles/types` | 타이틀 종류(공개) |
| 🔑 | POST | `/titles/types` | 타이틀 종류 추가 |
| 🔑 | PATCH | `/titles/types/{title_type_id}` | 타이틀 종류 수정/비활성화 |
| 🔑 | GET | `/admin/insights` | [관리자] Insight 목록 |
| 🔓 | GET | `/articles` | 기사 목록(공개: 게시본 / 관리자: all=true면 전체) |
| 🔓 | GET | `/articles/{article_id}` | 기사 상세 |
| 🔑 | PATCH | `/articles/{article_id}` | 관리자 게시 전 기사 수정 |
| 🔑 | POST | `/articles/{article_id}/publish` | 기사 게시(같은 일정/종류의 기존 게시본은 SUPERSEDED) |
| 🔑 | POST | `/articles/{article_id}/regenerate` | 기사 재생성(새 버전, 기존 보존) |
| 🔑 | POST | `/articles/{article_id}/reject` | 기사 반려/내리기 |
| 🔓 | GET | `/health` | Health |
| 🔑 | PATCH | `/admin/appearance` | 클럽 엠블럼과 기본 테마 저장 |
| 🔓 | POST | `/api/admin/auth` | 전체 관리자 모드 진입(PIN 입력 → 토큰) |
| 🔑 | GET | `/api/admin/clubs` | 슈퍼관리자: 운영팀 목록 |
| 🔑 | POST | `/api/admin/clubs` | 슈퍼관리자: 운영팀 추가 |
| 🔑 | DELETE | `/api/admin/clubs/{club_id}` | 슈퍼관리자: 팀 제거(기록 보존·접근 중지) |
| 🔑 | PATCH | `/api/admin/clubs/{club_id}` | 슈퍼관리자: 운영팀 수정 |
| 🔑 | POST | `/api/admin/clubs/{club_id}/restore` | 슈퍼관리자: 제거된 팀 복원 |
| 🔑 | GET | `/api/admin/me` | 전체 관리자 모드 확인 |
| 🔓 | GET | `/appearance` | 클럽 엠블럼과 기본 테마 조회 |
| 🔓 | GET | `/appearance/crest` | 공개 이미지 엠블럼(PNG) |

WebSocket: `GET /ws/clubs/{club_slug}` (누구나 구독, 메시지 종류는 app/api/ws.py 참고)
