# Clubwire

아마추어 풋살팀 운영(참석 → 자동 팀 편성 → LIVE 경기 → 기록 확정) + **The Wire**(데이터 기반 AI 기사).

- 백엔드: Python 3.12~3.13 (3.15처럼 갓 나온 버전은 일부 라이브러리 Windows용 사전 빌드본이 없어 설치 실패) / FastAPI / SQLAlchemy 2 / Alembic / Pydantic v2 / MySQL 8.0
- 프론트: React 18 + TypeScript + Vite (`frontend/`, 모바일 우선)
- 조회는 공개(URL), 쓰기는 **관리자 모드**(클럽 PIN → Bearer 토큰)
- LIVE 경기는 WebSocket으로 실시간 전파, 타이머는 서버가 자동 종료

## 1. 실행

```bash
# 0) MySQL 8.x DB + 접속 계정 준비 (.env.example 의 DATABASE_URL 이 clubwire/clubwire 계정을 씀)
mysql -uroot -p -e "CREATE DATABASE clubwire CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
  CREATE USER 'clubwire'@'localhost' IDENTIFIED BY 'clubwire';
  GRANT ALL PRIVILEGES ON clubwire.* TO 'clubwire'@'localhost';"

# 1) 의존성
pip install -r requirements.txt

# 2) 환경변수 (.env.example 복사 후 수정: DATABASE_URL, SECRET_KEY, OPENAI_API_KEY)
cp .env.example .env

# 3) 테이블 생성
alembic upgrade head            # 또는 docs/schema.sql 실행

# 4) 클럽 생성 (관리자 PIN 7777)
python -m app.cli create-club --slug ypr --name "YPR" --pin 7777

# 5) 서버
uvicorn app.main:app --reload --port 8000
# API 문서: http://localhost:8000/docs

# 6) 프론트(개발): Vite가 /api, /ws 를 8000으로 프록시
cd frontend && npm install && npm run dev      # http://localhost:5173/c/ypr
```

배포할 때는 `cd frontend && npm run build` 후 백엔드만 띄우면 `frontend/dist`를 같은 서버에서 서빙한다
(`http://서버/c/ypr`). 관리자 모드는 화면 오른쪽 위 자물쇠 → PIN 입력.

첫 화면(`/`)은 기본으로 `/c/ypr`로 이동한다. `frontend/.env`가 있다면 `VITE_DEFAULT_CLUB=ypr`로 변경한 뒤 프론트엔드를 다시 빌드한다. 이 변수를 명시적으로 비우면 클럽 주소 입력 화면을 표시한다.

### 기존 sanha 클럽을 YPR로 변경

기존 선수·일정·경기·기사 기록을 유지하려면 DB 초기화 대신 프로젝트 루트에서 다음 명령을 한 번 실행한다. `.env`의 `DATABASE_URL`에 연결된 DB에서 클럽 주소와 이름만 바꾸며, 클럽 ID·관리자 PIN과 모든 기록은 유지한다.

```bash
python -m app.cli rename-club --from-slug sanha --to-slug ypr --name YPR
```

백엔드를 다시 시작하고 `frontend/.env`의 `VITE_DEFAULT_CLUB`도 위와 같이 변경한 뒤 프론트엔드를 다시 빌드한다. 이후 공유 주소는 `/c/ypr`를 사용한다.

`OPENAI_API_KEY`가 없으면 기사는 **기본형 기사**(템플릿, `app/integrations/openai/template_writer.py`)로 만들어진다. 키를 넣으면 자동으로 OpenAI를 쓰고, AI 호출이 실패해도(크레딧 · 한도 초과, 연결 오류, 응답 검증 실패) 기본형으로 대신 쓴다. AI 창의성 · 답변 최대 길이는 관리자 설정 화면 '기사' 묶음.

> 테이블명이 대문자라 MySQL `lower_case_table_names=0`(Linux 기본)을 전제로 한다. Windows/macOS 로컬 MySQL은 이 설정이 달라 대소문자가 섞일 수 있으니 Docker(Linux) MySQL 사용을 권장.

## 2. 테스트

```bash
mysql -uroot -e "CREATE DATABASE clubwire_test CHARACTER SET utf8mb4;"
pytest -q          # 실제 MySQL(clubwire_test)에 붙어서 전체 시나리오 실행
```

| 테스트 | 내용 |
|---|---|
| `test_e2e_scenario.py::test_full_loop` | §106 완료 기준: 18명 → 3팀 6:6:6 → 경기/골/도움/취소/자책골 → 확정 → 통계·Pair·Rating·이력 → 관리자 대진 지정 → [일정마감] → 마감 기사·자동 타이틀 → 마감 후 수정 409 |
| `..::test_guests_rotation_timer_correction_and_ws` | 게스트(인원 +1, 분산), 지각 추가, WebSocket 수신, 타이머 자동 종료, 확정 해제→정정→재확정 시 Rating 증분 재계산 = 전체 재계산 |
| `..::test_insights_return_player_and_close_order` | 63일 만의 복귀/3연승 Insight, 마감 순서 강제, AUTO 게시, 재생성 버전 관리, 설정 이력 |
| `test_insight_rules.py` | 결승골(종료 10초 전)/역전/해트트릭/이변/타이틀 Insight 판정 |
| `test_insight_rules_v2.py` | 듀오·징크스·천적 후보, 이달 득점 순위, 연속 출전, 팀 하루 전적, 도움→득점 조합, 하루 최다 골 계산 + 마감 시 콤비·무패·철벽·첫 골 Insight |
| `test_concurrency.py` | 동시 골 20건(멱등키 중복 8건 포함) → 점수 = 이벤트 수 |
| `test_regressions.py` | 한쪽 팀이 빈 경기 포함 시 증분=전체 재계산, 설정 버전 연속 증가, 마감 이전 날짜 일정 차단, 득점자 팀 이동 차단, 제외 멤버 참석자 목록 반영 |
| `test_frontend_apis.py` | 홈 LIVE 배너 · 요약 줄(tzdata 없는 환경 포함), 일정 목록 인원수, 일정 요약, 멤버별 수상 이력, 기사 목록 페이지(게시 순서 커서·일정 날짜), 선수 프로필(가입일 · 출생연도 입력 · 지우기) |
| `test_titles_v2.py` | 이달의 득점왕 · 도움왕(월 마감, 동점 공동, MVP 기사 한 줄, MVP만 발표된 달 보충), 연속 참가 10 · 20회(참석 명단 기준, 취소 일정 무시, 결석하면 끊김, 다시 쌓으면 다시 수여), 수상 내역 조회 조건(`titleCode` 정확 · 앞부분, 기간, `limit`)과 선수 상세 `top` |
| `test_article_writer.py` | AI 창의성 · 답변 최대 길이가 요청에 실림, temperature 미지원 모델 재요청, 연결 실패 · 크레딧 초과 · 키 오류 · 답변 잘림 → 기본형 기사(게시 규칙 그대로) + 원인 표시, [다시 쓰기]로 AI 복귀, 키 없음 |
| `test_monthly_mvp.py` | 이달의 MVP: 상승률 계산(DB 이력과 일치) · 자격(일정 2회) · 열린 일정 있으면 대기 · 마지막 일정 마감 시 타이틀 + 기사 바로 게시 · 점수 비노출 · 한 달 한 번 · 후보 1~3위 |
| `test_strategies.py` | 팀 인원 분배, Pair 다양성 > 완전 균형, 허용범위, Confidence 감쇠, Elo, 추천 대진(가장 오래 쉰 두 팀), AI 응답 검증(OpenAI 호출 형태 포함) |

## 3. 운영 흐름 (API)

공통 접두사 `/api/clubs/{slug}` · 🔑 = 관리자 토큰 필요 · 전체 목록은 [docs/API.md](docs/API.md)

```
POST /admin/auth {"password":"7777"}                → accessToken (관리자 모드)
POST /members {"name":"진선호"} 🔑                    (×N)
POST /sessions {"sessionDate":"2026-10-17"} 🔑
POST /sessions/{id}/members {"memberIds":[...]} 🔑    참석자
POST /sessions/{id}/guests {"count":2} 🔑             게스트(인원수만)
POST /sessions/{id}/teams/generate {"teamCount":3} 🔑  미리보기(여러 번 가능)
POST /sessions/{id}/teams/confirm {"generationId":..} 🔑   ★ [일정확정] → PRE_MATCH 기사
POST /sessions/{id}/teams/assignments 🔑              지각 ADD / 이동 MOVE / 제외 REMOVE (이력 저장)

GET  /sessions/{id}/matches/next-suggestion 🔑        팀별 오늘 경기 수 + 추천 대진(가장 오래 쉰 두 팀)
POST /sessions/{id}/matches/next {"teamAId","teamBId"} 🔑   다음 경기 생성 (대진은 매번 관리자가 지정)
POST /matches/{mid}/start | pause | resume | end 🔑
POST /matches/{mid}/goals {"teamId","scorerMemberId","assistMemberId","ownGoal","guestGoal","idempotencyKey"} 🔑
POST /matches/{mid}/events/{eid}/cancel 🔑            골 취소(삭제 X)
POST /matches/{mid}/finalize 🔑                       기록 확정 → Rating/통계/Pair 반영
POST /sessions/{id}/close 🔑                          ★ [일정마감] → 수정 잠금, 자동 타이틀, SESSION_RECAP 기사

GET  /live | /sessions/{id}/summary                                          공개(홈 LIVE 배너, 마감 화면 요약)
GET  /articles | /stats/members | /stats/members/{id} | /titles/awards       공개
WS   /ws/clubs/{slug}                                                         공개 구독
```

## 4. 구조

```
app/
  api/            라우터(HTTP/WS). 얇게 유지
  core/           설정, DB/트랜잭션, 보안(PIN/JWT), 에러, WS 허브, 클럽 설정 키 정의
  models/         ORM(대문자 테이블), enums, comments(DB COMMENT)
  schemas/        Request DTO(camelCase)
  services/       트랜잭션 단위 업무 로직(일정/팀/경기/Rating 재생/통계/타이틀/생명주기)
  strategies/     교체 가능한 순수 알고리즘(DB 모름)
                  rating.py        Confidence / TeamStrength / MatchRating(Elo)
                  team_generation  Randomized Candidate + Scoring, PairPenalty
                  match_order      다음 경기 추천 대진(가장 오래 쉰 두 팀)
                  importance       Insight 중요도
  wire/           Insight 엔진, 기사 서비스, Insight Type 기준 데이터
  integrations/openai/  AI 작성기(OpenAI Structured Output) / 기본형 기사 템플릿(template_writer)
  jobs/           LIVE 타이머 자동 종료 루프
alembic/          마이그레이션(0001 initial)
frontend/         React + TypeScript (화면 ↔ 스토리보드 매핑은 docs/DECISIONS.md 3-2)
  src/api/        백엔드 DTO 타입 + API 함수
  src/lib/        클럽 컨텍스트(관리자 토큰, WebSocket), 타이머, 포맷
  src/components/ 공용 UI(상단 바, 하단 탭, 시트, PIN, 다음 경기 대진)
  src/pages/      공개 화면 / pages/admin 관리자 화면
docs/             ERD.md, TABLES.md(테이블 정의서), API.md, schema.sql(DDL), openapi.json, DECISIONS.md
scripts/gen_docs.py   문서 재생성
```

## 5. 문서

- [docs/DECISIONS.md](docs/DECISIONS.md) — 확정된 결정사항, 원 요구사항 대비 변경점과 이유, 남은 이슈
- [docs/WIRE_RULES.md](docs/WIRE_RULES.md) — 기사거리(Insight) 26종의 조건과 제목 예시
- [docs/ERD.md](docs/ERD.md) — 영역별 ERD(Mermaid)
- [docs/TABLES.md](docs/TABLES.md) — 테이블 정의서(28개)
- [docs/schema.sql](docs/schema.sql) — MySQL DDL(COMMENT 포함)
- [docs/API.md](docs/API.md) — API 목록(공개/관리자 구분)

스키마나 API를 바꾼 뒤에는 `alembic revision --autogenerate -m "..."` → `python scripts/gen_docs.py`.

## 6. 샘플 데이터

`ypr_sample_data.sql`(별도 전달): 2026년 7/4 ~ 10/17 토요일 16회 경기 기록(7 · 8 · 9월 이달의 MVP · 득점왕 · 도움왕, 연속 참가 10회 포함, 10월은 진행 중). 모든 테이블을 비우고 다시 넣는다.

```
# 0) 최신 코드로 테이블 준비
alembic upgrade head
# 1) MySQL Command Line Client
charset utf8mb4
use clubwire
source C:/clubwire/ypr_sample_data.sql
```

다시 만들려면(빈 DB에서): `pip install time-machine` → `alembic upgrade head` → `python -m scripts.gen_sample_data` → `mysqldump`로 데이터만 추출.

## 7. 브라우저 E2E

`frontend` 빌드 후 백엔드를 띄운 상태에서 Playwright로 관리자/관전자 두 브라우저를 동시에 조작해 확인했다:
PIN(오답→정답) → 멤버 18명 → 일정·게스트 → 3팀 편성·[일정확정] → 경기 시작(관전자 화면 실시간 반영) → 골·도움·골 취소·자책골 →
일시정지/재개 → 종료·기록 확정 → 2경기 대진 선택 → [일정마감] → 기사 검토·게시 → 홈/기사/기록실(수상 내역)/선수/설정.

## 일정 관리와 프리뷰 검토

- [일정확정] 후 해당 일정의 프리뷰 기사 검토 화면으로 이동한다. 프리뷰는 `ARTICLE_PUBLISH_MODE=AUTO`여도 자동 게시하지 않는다. 관리자가 제목·요약·본문을 수정하거나 반려·다시 쓰기를 선택하고, [게시]를 눌러 공개한다.
- 관리자 일정 탭은 **예정된 일정 / 완료된 일정 / 삭제한 일정**으로 구분한다. 완료는 날짜 경과가 아니라 [일정마감] 상태를 기준으로 한다.
- [일정 삭제]는 보관함으로 이동하는 방식이다. 삭제한 일정과 기사는 공개 목록에서 숨기고, 관리자는 삭제한 일정 상세를 읽을 수 있다. 삭제 후 수정은 차단한다. 완료된 경기·통계·타이틀은 보존한다. 경기 기록이 있는 미마감 일정은 먼저 마감한 뒤 삭제한다.
- 업데이트 시 `alembic upgrade head`로 `0009` 마이그레이션을 적용한다. 기존 취소 일정도 삭제 보관함으로 분류한다.

## 와이어 기사 문체와 이정표 표

- AI 프롬프트 `wire_prompt_v6`는 가벼운 스포츠 칼럼 문체를 사용한다. 맞대결의 대비, 팀 조합의 이야기, 꾸준한 참가 기록을 섞되 핵심 이야기 하나에 보조 기록 2~4개를 연결한다. 커뮤니티 게시글·댓글·인터넷 말투는 사용하지 않는다. 기존 기사는 자동으로 바뀌지 않으므로 백엔드 재시작 후 관리자 기사 검토에서 [다시 쓰기]를 실행한다.
- 프리뷰 본문 바로 아래 **이번 일정 이정표** 표는 기사 생성 당시 AI에 전달한 `MILESTONE_EXPECTED` 중 제목·요약·본문에 쓰지 않은 기록을 표시한다. 선수·기록·남은 수만 공개하며 중요도와 내부 점수는 표시하지 않는다. 현재 기록으로 재계산하지 않아 지난 기사의 표도 생성 당시 수치를 유지한다.
- 관리자 기사 수정 시 **기사에 쓴 사실** 선택도 함께 맞추면 이정표 표에 반영된다. 미사용 마일스톤이 없거나 예전 기사의 저장된 근거가 없으면 표는 숨겨진다. 공개 기사와 관리자 검토 화면에 같은 표를 제공한다.
- API: 기사 상세 응답에 `unusedMilestones`를 추가한다. 기사 수정 요청의 선택 필드 `usedInsightIds`를 생략하면 기존 사용 사실을 유지하고, 빈 배열이면 선택을 모두 해제한다. 새 의존성이나 DB 마이그레이션은 필요하지 않다.

## 선수단의 운영 수칙 안내

선수단 탭의 이름 검색 위에 **운영 수칙** 버튼을 제공한다. 방문자와 관리자 모두 안내를 열어 읽을 수 있다. 내용은 [YPR 원문](https://hesse429.github.io/YPR/)의 운영 수칙을 읽어 표시한다. 이전 승점제 안내·배지 표는 내용이 변경되어 제거했다.

운영 수칙은 안내를 열 때 공개 Firestore 문서를 읽기 전용으로 조회한다. 배포한 프론트엔드가 `firestore.googleapis.com`에 접근할 수 있어야 하며, 별도 API 키·Firebase 패키지·쓰기 권한은 필요하지 않다. 6초 안에 읽지 못하거나 데이터가 잘못되면 원문 소스의 **2026-06-08 기본 수칙**을 날짜·실패 안내와 함께 표시한다. 기본 수칙을 최신 수칙으로 표시하지 않으며 재시도와 원문 보기 링크를 제공한다. 외부 수칙의 HTML은 실행하지 않고 제목·문단·목록을 텍스트로 렌더링한다.

## YPR 테스트 시작용 로컬 DB 초기화

먼저 백엔드를 종료하고 MySQL은 실행한 상태로 둔다. 프로젝트 루트에서 가상환경을 활성화한 뒤 아래 명령으로 **대상 DB와 삭제 범위만 미리 확인**한다. `.env`의 `DATABASE_URL`을 사용하며 원격/다른 PC의 DB에 자동 연결하지 않는다.

```bash
python -m scripts.reset_ypr_test
python -m scripts.reset_ypr_test --apply
```

`--apply`는 기본 클럽 `ypr`의 선수·일정·경기·통계·레이팅 이력·기사·수상 기록을 지우고, 전달받은 초기 표의 23명을 다시 등록한다. 선수의 초기·현재 레이팅을 같은 원본 값으로 설정하며 경기 수는 0부터 시작한다. 기존 선수 프로필도 초기화되므로 미리보기와 백업 위치를 확인한다. 관리자 PIN·클럽 설정·타이틀 정의와 다른 클럽은 보존한다. 대상 클럽이 다르면 `--club 클럽주소`로 지정한다.

실제 삭제 전에 `.venv/clubwire-reset-backups/`에 복구 SQL을 반드시 저장한다. 백업이 실패하면 초기화하지 않으며, 적용 중 오류는 트랜잭션을 롤백한다. 백업에는 초기화 전 선수·경기·기사 데이터가 포함되므로 Git에 올리지 않는다. 다른 위치를 쓰려면 `--backup-dir 경로`를 지정한다. 복구는 백엔드를 종료하고 **같은 스키마·DB·클럽**에서 MySQL 클라이언트를 `--abort-source-on-error` 옵션으로 실행한 뒤 `SOURCE 복구파일경로;`로 수행한다. DB/클럽 식별자가 다르면 복구 SQL은 변경을 건너뛴다.

초기화 후에는 **YPR clubWire 테스트 기간 돌입** 안내 기사 한 건을 바로 게시한다. 일정이 없어도 와이어에 표시되며 운영진 작성 안내로 표기한다. 문구는 `scripts/reset_ypr_test.py`의 `NOTICE_TITLE / NOTICE_SUMMARY / NOTICE_BODY`에서 확인할 수 있다. 새 DB 마이그레이션은 필요 없으며, 코드 적용 후 프론트엔드를 빌드하고 백엔드를 재시작한다.

## 로컬 .env 파일 생성

`.env`는 키를 담는 로컬 파일이므로 Git에서 제외한다. 저장소에 `.env.example`만 있는 경우 프로젝트 루트에서 다음 명령으로 생성한다. 기존 `.env`의 설정값은 유지하며, 서명 키가 비어 있거나 없을 때만 생성한다. 새 파일에는 임의의 토큰 서명 키를 넣고 OpenAI 키는 비워 둔다.

```bash
python -m scripts.init_local_env
```

생성한 `.env`의 `OPENAI_API_KEY=`에 발급받은 키를 넣고 `AI_PROVIDER=auto`를 유지한다. `DATABASE_URL`의 DB명·계정이 로컬 MySQL과 일치하는지 확인한 뒤 백엔드를 완전히 다시 시작한다. `.env`는 프로젝트 루트(`.env.example`과 같은 위치)에 두며 `frontend` 폴더에는 넣지 않는다.
