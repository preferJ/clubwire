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
python -m app.cli create-club --slug sanha --name "산하 FC" --pin 7777

# 5) 서버
uvicorn app.main:app --reload --port 8000
# API 문서: http://localhost:8000/docs

# 6) 프론트(개발): Vite가 /api, /ws 를 8000으로 프록시
cd frontend && npm install && npm run dev      # http://localhost:5173/c/sanha
```

배포할 때는 `cd frontend && npm run build` 후 백엔드만 띄우면 `frontend/dist`를 같은 서버에서 서빙한다
(`http://서버/c/sanha`). 관리자 모드는 화면 오른쪽 위 자물쇠 → PIN 입력.

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
