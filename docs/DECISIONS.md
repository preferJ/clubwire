# Clubwire 설계 결정 기록

원 요구사항 문서(이하 "원문")와 2026-10-14 Q&A 결과를 코드에 반영하면서 정한 내용이다.
형식: **무엇이 → 어떻게 바뀌었나 → 이유**.

---

## 1. Q&A 확정 사항

| # | 항목 | 결정 | 코드 위치 |
|---|---|---|---|
| 2.1 | 테이블/컬럼 명명 | 대문자 SNAKE_CASE (`MEMBER_ID`) | `app/models/*` |
| 2.2 | PK | `BIGINT AUTO_INCREMENT` | `app/models/base.py` |
| 2.3 | YN 컬럼 | BOOLEAN(TINYINT(1)). 컬럼명은 원문대로 `…_YN` 유지 | 전 모델 |
| 2.4 | 상태값 | VARCHAR + 앱 Enum(가장 대중적인 방식) | `app/models/enums.py` |
| 2.5 | FK | 물리 FK 전부 적용 | `docs/schema.sql` |
| 2.6 | DB | MySQL 8.0 (JSON, 튜플 비교 사용) | |
| 3.1 | 대진 | ~~밀어내기 규칙~~ → **매 경기 관리자가 두 팀을 지정**(10-14 스토리보드 메모로 변경). 시스템은 '가장 오래 쉰 두 팀'을 미리 채워 줄 뿐 | `strategies/match_order.py`, `NextMatchSheet` |
| 3.2 | 경기 수 | 미리 정하지 않음. 다음 경기를 1건씩 생성, GAME_NO + 시작 시각만 기록 | `match_service.create_next_match` |
| 3.3 | 종료 | 자동 종료(`MATCH_AUTO_END_YN`) + 관리자 END 둘 다. 조기 종료(`MATCH_EARLY_END_GOALS`) 설정 | `jobs/timer.py`, `match_service` |
| 3.4 | MVP | MVP를 포함한 **타이틀** 체계(TITLE_TYPE + MEMBER_TITLE), 주 단위. ※ 2026-10-22 MVP 제거(3-7), 타이틀은 득점왕·도움왕 | `title_service.py` |
| 3.5 | 게스트/자책골 | 게스트 = 인원 +1(Rating/통계 없음), 자책골 기록 | `SESSION_GUEST`, `OWN_GOAL_YN` |
| 3.6 | 확정 후 변경 | 지각 추가/이동/제외 허용 + 이력 | `TEAM_ASSIGNMENT_LOG` |
| 3.7 | A/B 평가 | 이번 개발 범위에서 **전부 제외** | (테이블 없음) |
| 3.8 | 신규 가입자 | Rating 1000 + Confidence 0(낮음)에서 시작 | `member_service.create_member` |
| 3.9 | Rating 반영 순서 | 경기별 Finalize 즉시 반영, GAME_NO 순서 강제, 시작 시점 전력 Snapshot | `finalize_match`, `start_match` |
| 3.10 | 확정 기록 수정 | **[일정마감]** 이후 수정 불가, 마감 시 마감 기사 | `lifecycle_service.close_session` |
| 3.11 | 기사 시점 | **[일정확정]** 때 1건, 이후 [일정마감]까지 없음. 게시 자동/수동 설정 | `ARTICLE_PUBLISH_MODE` |
| 3.12 | 공개 범위 | URL(slug)로 접근, 기사·통계 비로그인 공개. 카카오 로그인은 추후 | `/api/clubs/{slug}` |
| 3.13 | 실시간 | 처음부터 WebSocket. 관리자 모드(PIN) 진입한 사람만 경기 조작 | `api/ws.py`, `admin_dep` |

---

## 2. 원문 대비 변경점과 이유

### 2-1. 일정(SESSION) 상태
- **원문**: `DRAFT / OPEN / TEAM_ASSIGNED / IN_PROGRESS / COMPLETED / CANCELLED`
- **변경**: `OPEN → CONFIRMED → IN_PROGRESS → CLOSED` (+ `CANCELLED`)
- **이유**: Q&A의 [일정확정]/[일정마감]이 상태 전이의 핵심 이벤트가 됨. `TEAM_ASSIGNED`=[일정확정], `COMPLETED`=[일정마감](잠금 의미 포함)으로 이름을 맞춤. DRAFT는 쓰임이 없어 제거.

### 2-2. 확정 경기 수정 (원문 §55~56, Open Issue)
- **원문**: UNFINALIZE → Rollback/Rebuild → 수정 → FINALIZE, 전체 Rebuild vs 증분 미정
- **변경**:
  - [일정마감] 전: 경기 확정 해제(`/unfinalize`) → 수정 → 재확정 가능
  - [일정마감] 후: 해당 일정의 팀/경기/골 변경 전부 409 (`SESSION_CLOSED`)
  - 마감은 **날짜 순서대로만** 가능 (앞 일정이 열려 있으면 `PREVIOUS_SESSION_OPEN`)
  - Rating은 "바뀐 경기부터" 재생(replay). 기존 이력은 지우지 않고 `VOIDED_YN=true` 후 새로 쌓음
  - 마감된 일정보다 **앞선 날짜**의 일정 생성/날짜 변경/경기 확정은 거부 (`BEFORE_CLOSED_SESSION`). 같은 날짜는 허용
- **이유**: 마감 순서를 강제하고 마감 이전 날짜에 새 기록이 끼어들지 못하게 하면, 마감된 구간의 Rating은 다시 바뀌지 않는다. 그래서 "증분 재계산"이 "전체 재계산"과 같은 결과가 되고(테스트로 검증), 이력은 감사용으로 남는다.
- **주의**: 설정(K, scale 등)을 바꾸면 이미 쌓인 이력은 당시 설정 그대로 두고 이후 경기부터 새 설정을 쓴다. 과거까지 새 설정으로 다시 계산하려면 관리자 `POST /admin/rebuild`(전 구간 재생, `ADMIN_RECALC`).

### 2-3. 경기 일정 생성 · 대진 (원문 §43 Match Order)
- **원문**: 팀 생성 후 Match Schedule 일괄 생성(LEAGUE/ROTATION Strategy)
- **1차 변경(Q&A 3.1/3.2)**: `matches/next`로 1건씩 생성 + 밀어내기(남을 팀 선택/승자 잔류) 자동 규칙
- **2차 변경(스토리보드 S03 메모 → "항상 관리자가 설정")**:
  - 밀어내기 자동 규칙 제거. `POST /sessions/{id}/matches/next`에 `teamAId`, `teamBId` **필수**
  - `GET .../next-suggestion`은 팀별 오늘 경기 수·연속 경기 수와 **추천 대진(가장 오래 쉰 두 팀)**만 돌려줌 → 화면에서 미리 선택된 상태로 보여 주고 관리자가 바꿀 수 있음
  - 3팀이면 추천만 따라가도 A-B → C-A → B-C → A-B 순서로 돈다
  - DB: `MATCH_GAME.STAY_TEAM_ID / STAY_DECIDED_YN` 삭제, 설정 `ROTATION_*` 삭제 (마이그레이션 0002)
- **이유**: 현장 상황(체력, 인원, 시간)에 따라 대진이 매번 달라서 규칙으로 고정하기보다 관리자가 정하는 편이 맞다는 판단.

### 2-4. 기사 종류 (원문 §76)
- **원문**: PRE_MATCH / POST_MATCH / SESSION_RECAP
- **변경**: PRE_MATCH([일정확정]) + SESSION_RECAP([일정마감])만 생성. POST_MATCH는 Enum만 예약
- **이유**: 3.11 답변. 경기별 Insight(결승골/역전/이변/해트트릭)는 마감 기사의 재료로 사용.

### 2-5. MVP → 타이틀 (원문 §57)
- **원문**: MVP 통계만 있고 저장 구조 없음
- **추가**: `TITLE_TYPE`(클럽별 정의) + `MEMBER_TITLE`(수여 이력)
  - 기본 3종: 이주의 MVP(수동), 이주의 득점왕/도움왕(마감 시 자동, 동점 공동 수여)
  - `MVP_COUNT` = `COUNTS_AS_MVP_YN` 타이틀 수
  - ※ 2026-10-22 **MVP 제거**(3-7): 기본 타이틀은 득점왕/도움왕 2종. `MVP_COUNT` · `COUNTS_AS_MVP_YN` 컬럼은 남겨 두지만 화면·API에서 쓰지 않음
- **이유**: 3.4 답변(주간 타이틀 관리). 자동 타이틀은 같은 주에 일정이 여러 번이면 마감 때마다 다시 계산.

### 2-6. 게스트 / 자책골 (신규)
- `SESSION_GUEST`: 팀 인원 분배에는 포함(13명 → 7:6), 팀 편성 시 팀마다 고르게 분산. Team Strength 평균에는 제외, 인원수 인자(headcount)에는 포함
- 게스트 득점: `GUEST_GOAL_YN=true`, 득점자 NULL → 팀 점수만 오르고 개인 기록 없음
- 자책골: `OWN_GOAL_YN=true`, `TEAM_ID`=점수를 얻은 팀, `SCORER_MEMBER_ID`=자책한 선수 → 통계 `OWN_GOALS`

### 2-7. 팀 편성 Snapshot (원문 §42)
- **원문**: Snapshot 항목은 있으나 저장 위치 없음(SESSION_TEAM에 일부만)
- **추가**: `TEAM_GENERATION` — 알고리즘 버전, 설정 버전 + 설정 전체 JSON, 난수 시드, 후보 수, 허용범위 만족 후보 수, Spread, Pair Penalty, 입력값 전체
- **이유**: 같은 시드 + 같은 입력이면 같은 결과가 나와 "왜 그날 이런 팀이 나왔는가"를 재현 가능. 미리보기를 여러 번 돌릴 수 있고(PREVIEW), 확정본만 CONFIRMED.
- 편성 이후 참석자가 바뀌면 확정을 거부(`ATTENDEES_CHANGED`) → 재생성 유도.

### 2-8. Pair 집계 (원문 §33~36)
- **추가 컬럼**: `SAME_TEAM_MATCH_COUNT`, `SAME_TEAM_DRAW_COUNT`, `CO_ATTENDANCE_SINCE_SAME_TEAM`, `OPPONENT_LOW/HIGH_WIN_COUNT`
- **이유**:
  - `SAME_TEAM_COUNT`(일정 단위)만으로는 "같이 뛸 때 승률"(경기 단위)의 분모가 없음
  - RARE_PAIR의 "마지막 같은 팀 = 8 Session 전"을 계산하려면 그 뒤로 함께 출전한 일정 수가 필요
  - 원문 `OPPONENT_WIN_COUNT`는 누구 승인지 모호 → LOW/HIGH로 분리
- 집계 기준은 **실제 출전(MATCH_MEMBER) + 확정 경기**. 3팀일 때 대기 팀은 상대가 아님(원문 §34 그대로).

### 2-9. Insight 다인 대상 (원문 §62)
- **원문**: `INSIGHT.MEMBER_ID` 단일 컬럼
- **추가**: `INSIGHT_MEMBER(INSIGHT_ID, MEMBER_ID, ROLE)`
- **이유**: RARE_PAIR(2명), 역전승 득점자들 등 여러 명이 나오는 Insight와 "특정 선수 관련 기사" 조회(원문 §96)를 위해.
- Insight 재생성 시 기존 행은 `ACTIVE_YN=false`(삭제 안 함) → 이미 나간 기사의 근거가 끊기지 않음.

### 2-10. Confidence 저장 (원문 §17~19)
- `PLAYER_RATING`에 Confidence 컬럼을 두지 않음. `MATCH_SAMPLE_COUNT`, `LAST_PLAYED_DATE`로 매번 계산
- A/B 제외로 `AB_SAMPLE_COUNT` 제거
- `LAST_PLAYED_AT`(DATETIME) → `LAST_PLAYED_DATE`(DATE): 미출전 일수는 일정 날짜 기준이 자연스러움

### 2-10-1. 멤버별 시작 Rating (2026-10-14 추가)
- 기존 기록(다른 곳에서 쓰던 Rating 표)을 가져올 수 있도록 `MEMBER.INITIAL_RATING`(NULL 허용) 추가. 마이그레이션 `0003`
- 이유: 시작값을 `PLAYER_RATING.CURRENT_RATING`에만 넣으면, 확정 해제·전체 재계산 때 모두 설정값(1000)에서 다시 출발해 값이 틀어진다.
  재계산의 출발점을 멤버별 시작값으로 바꿔 증분 계산과 전체 재계산 결과가 항상 같게 했다(`tests/test_regressions.py`)
- NULL이면 기존처럼 설정 `INITIAL_RATING`. 시작값이 있어도 Confidence는 0(경기 기록 기준)에서 시작
- 등록: `POST /members {name, initialRating}`(관리자). 멤버 관리 화면에서 `이영희 1081`처럼 이름 뒤 숫자로 입력, 순위표를 붙여 넣어도 됨
- 등록 후 시작값 변경은 아직 없음(바꾸려면 재계산이 함께 필요)

### 2-11. 설정 (원문 §87~88)
- `SYSTEM_CONFIG`를 **클럽별**(PK: CLUB_ID + CONFIG_KEY)로. 키 정의(타입/기본값/허용값)는 코드(`core/club_config.py`), 값은 DB
- `CLUB.CONFIG_VERSION`을 변경마다 +1, 이력에 버전 기록. Rating 이력/팀 편성에는 사용한 버전 저장
- `INSIGHT_TYPE_CONFIG / PARAM`은 전역(클럽별 튜닝이 필요해지면 CLUB_ID 추가)
- AI 모델명은 클럽 설정이 아니라 서버 환경변수(`AI_ARTICLE_MODEL`, `AI_RECAP_MODEL`) — 비용/키와 같은 배포 단위라서

### 2-12. 동시성 (원문 §94)
- DB 격리수준 `READ COMMITTED` + 경기 행 `SELECT … FOR UPDATE` + 골 멱등키 UNIQUE(MATCH_ID, IDEMPOTENCY_KEY)
- 같은 멱등키 재요청은 에러가 아니라 기존 이벤트를 그대로 반환(`duplicate: true`)
- 파생 데이터 재계산은 CLUB 행 잠금으로 클럽 단위 직렬화
- 잠금 조회(`FOR UPDATE`)는 항상 DB 최신값으로 객체를 덮어씀(`populate_existing`) — 같은 요청에서 먼저 읽어 둔 옛 값으로 이중 종료/버전 역행이 생기지 않게
- 골/도움 기록이 있는 선수는 출전 명단에서 빼거나 상대 팀으로 옮길 수 없음(통계 오염 방지)

### 2-13. AI 안전장치 (원문 §79~80)
- JSON Schema Structured Output(strict) + Pydantic 재검증
- 본문에 내부 점수 용어(Rating/Confidence/중요도 점수/기대승률)가 있으면 재시도 후 실패 처리
- `usedInsightIds`는 실제로 넘긴 Insight ID만 인정
- Insight FACTS에는 Rating·기대승률 숫자를 아예 넣지 않음(이변은 `underdogWin: true`만)
- AI 입력 DTO 전체를 `AI_ARTICLE.REQUEST_JSON`에 저장 → 재생성 시 같은 사실로 새 버전 생성

---

## 3. 기본 설정값 (관리자 `PATCH /admin/config`로 변경)

| 키 | 기본 | 비고 |
|---|---|---|
| INITIAL_RATING | 1000 | |
| MATCH_RATING_K | 20 | 팀 단위 변화량 |
| RATING_EXPECTATION_SCALE | 400 | Elo |
| HEADCOUNT_ADVANTAGE_FACTOR | 0 | 데이터 쌓인 뒤 보정 |
| CONFIDENCE_MATCH_SCALE | 10 | 10경기 ≈ 0.63, 30경기 ≈ 0.95 |
| CONFIDENCE_DECAY_GRACE_DAYS / DECAY_DAYS | 30 / 90 | 30일까지 감소 없음 |
| CONFIDENCE_MULT_MAX / MIN | 2.0 / 0.5 | 신규 2배, 안정 0.5배 |
| TEAM_RATING_TOLERANCE_PERCENT | 1.0 | (최고−최저)/평균 |
| TEAM_CANDIDATE_COUNT | 3000 | 18명 기준 수십 ms |
| PAIR_ALPHA / PAIR_PENALTY_EPSILON | 2.0 / 0.01 | |
| MATCH_DURATION_SEC | 600 | |
| MATCH_AUTO_END_YN | true | |
| MATCH_EARLY_END_GOALS | 0 | 0=미사용 |
| ARTICLE_PUBLISH_MODE | MANUAL | AUTO면 생성 즉시 게시 |
| WIRE_MAX_INSIGHTS | 15 | AI에 넘기는 최대 개수 |

---

## 3-1. 스토리보드 메모 반영 (2026-10-14)

| 메모 위치 | 메모 | 반영 |
|---|---|---|
| S03 일정 상세 | 경기는 자동세팅(순차)과 관리자 설정 게임 → **항상 관리자가 설정** | 2-3 참고. 프론트 `NextMatchSheet`(팀 1/팀 2 선택, 추천 미리 선택) |
| S06 기록실 | 기록에 수상내역도 추가 | 기록실에 **[수상 내역] 탭**(주차별 전체 이력 + 타이틀 많이 받은 선수), 선수 화면에 **수상 이력** 섹션 |
| S05 선수 기록 | 도움은 표시 안됨 | 확인 결과 **현행 유지**(도움 표시 그대로) |

## 3-2. 프론트엔드(React + TypeScript)

- Vite + React 18 + TypeScript + react-router. UI 라이브러리 없이 스토리보드 토큰을 CSS 변수로 옮김(`frontend/src/styles/global.css`)
- URL: `/c/{클럽주소}` 아래 공개 화면, `/c/{클럽주소}/admin/...` 관리자 화면. 관리자 토큰은 클럽별로 브라우저에 저장, 만료/거부 시 자동 해제
- 실시간: 클럽 단위 WebSocket 1개를 앱 전체가 공유(끊기면 재접속). 타이머는 서버 시각 기준으로 화면에서 계산
- 골 등록은 시트를 열 때마다 멱등키를 새로 만들어 연타해도 1번만 기록
- 배포: `npm run build` 결과(`frontend/dist`)를 FastAPI가 같이 서빙(설정 `FRONTEND_DIST`). 개발 중에는 Vite 서버가 `/api`, `/ws`를 백엔드로 프록시
- 화면 ↔ 스토리보드: S01 `HomePage`, S02 `ArticlePage`, S03 `SessionPage`, S04/A04/A05/A06 `MatchPage`, S05 `PlayerPage`, S06 `RecordsPage`, A01 `PinSheet`, A02 `SessionFormPage`, A03 `TeamsPage`, A07 `ClosePage`, A08 `ArticlesAdminPage` (+ 일정 목록, 멤버 목록, 관리자 메뉴, 멤버 관리, 운영 설정)

## 3-3. 샘플 데이터 (2026-10-14)

- `scripts/gen_sample_data.py`: 2026-07-04 ~ 10-17 토요일 16회(2026-10-23 변경, 이전: 07-05 ~ 09-27 일요일 13회)를 **실제 API로 시뮬레이션**(시계만 과거로 이동)해서 DB를 채운다. 월이 바뀌는 시각(1일 00:10)에 월 마감 → 이달의 MVP
  INSERT문을 손으로 만들면 기록·통계·Rating 이력·Pair·타이틀·Insight·기사가 서로 어긋나기 때문
- 선수 23명(시작 Rating = 전달받은 표), 3팀·15~21명·하루 7~9경기, 밀어내기 대진, 득점/도움/자책골/게스트 골/입력 정정(골 취소), 휴가 복귀, 지각 합류
- 기사는 OpenAI 대신 스크립트 안의 템플릿 작성기가 Insight 사실로 작성(`MODEL_NAME='sample-template'`). 마지막 주 마감 기사는 검토 대기로 남김
- 결과를 `mysqldump`로 데이터만 뽑아 INSERT문(.sql) 제공. 검증: 빈 DB에 적재 후 28개 테이블 CHECKSUM 일치, 전체 재계산 전후 Rating·통계 동일

## 3-4. 기사거리 12종 추가 + 하단 탭 메뉴 (2026-10-20)

새 Insight 유형(기준 숫자는 `INSIGHT_CONFIG_PARAM`, 켜고 끄기·태그·중요도는 `INSIGHT_TYPE_CONFIG`). 기존 DB에는 기사 생성 시 자동으로 추가된다(`ensure_insight_types`), 스키마 변경 없음.

| 시점 | 유형 (태그) | 조건(기본값) | 계산 근거 |
|---|---|---|---|
| 프리뷰 | DUO_REUNITED (듀오) | 같은 팀 배정 + 같은 팀 10경기 이상 + 승률 65% 이상, 하루 최대 3쌍 | Pair 집계(같은 팀 경기·승·무) |
| 프리뷰 | NEMESIS_MATCH (천적) | 다른 팀 배정 + 맞대결 6경기 이상 + 한쪽 승률 70% 이상, 열세 쪽이 주인공, 최대 3쌍 | Pair 집계(맞대결 각자 승) + 최근 연패 |
| 프리뷰 | JINX_PAIR (징크스) | 같은 팀 배정 + 같은 팀 10경기 이상 + 승률 30% 이하, 최대 2쌍 | Pair 집계 |
| 프리뷰 | SCORING_RACE (레이스) | 이달 득점 1·2위 2골 차 이내 + 1위 3골 이상 + 둘 다 출전 | 이달 경기 기록 |
| 프리뷰 | ATTENDANCE_STREAK (개근) | 오늘 포함 6일정 이상 연속 출전 | 경기 기록 |
| 마감 | REVENGE_RESULT (천적) | 오늘 프리뷰의 천적 매치 두 사람이 실제로 맞붙은 경우의 결과(설욕/천적 계속/무승부) | 오늘 경기 + 프리뷰 Insight |
| 마감 | ASSIST_COMBO (콤비) | 같은 도움→득점 조합이 오늘 2번 이상 | 오늘 골 기록 |
| 마감 | UNBEATEN_TEAM (무패) | 오늘 3경기 이상 + 패배 0(전승이면 중요도 ↑) | 오늘 팀 전적 |
| 마감 | CLEAN_SHEET (철벽) | 오늘 3경기 이상 무실점 | 오늘 팀 전적 |
| 마감 | FIRST_GOAL / FIRST_ASSIST (데뷔) | 통산 첫 골·첫 도움. 클럽 첫 기록일은 제외(전원이 첫 골이 되므로) | 이전 누적 |
| 마감 | PERSONAL_BEST_GOALS (신기록) | 오늘 3골 이상 + 본인 하루 최다 초과 + 이전 출전 3일정 이상 | 일정별 득점 |

- 팀 단위 사실(무패·철벽)은 대표 선수(`INSIGHT.MEMBER_ID`)를 두지 않고 팀원 전원을 `INSIGHT_MEMBER`(TEAM)로 연결: 한 사람의 공으로 기사화되는 것을 막고, 선수 화면에서는 관련 기사로 보이게
- AI 프롬프트 v2: 천적·징크스·복수는 "설욕할까/징크스 깰까"처럼 도전 관점으로만, 팀 단위 사실은 특정 선수 공으로 돌리지 않음
- 순수 계산은 `insight_engine`의 함수(`same_team_rate_candidates`, `nemesis_candidates`, `monthly_goal_ranking`, `attendance_streak`, `team_day_records`, `assist_combos` 등)로 분리해 단위 테스트(`tests/test_insight_rules_v2.py`)
- 홈 태그 칩에 새 태그 추가, 관리자 기사 검토 화면에 새 사실 설명 추가
- **하단 탭 메뉴**: 상세(기사·일정·경기·선수)와 관리자 화면에서도 항상 표시. 기사 → 와이어, 일정·경기 → 일정, 선수 → 멤버 탭을 강조. 화면 하단 실행 버튼(`.bar-actions`)은 탭 메뉴 위에 붙는다
- 샘플 데이터(`ypr_sample_data.sql`)를 새 기사거리 포함으로 다시 생성

## 3-5. 와이어는 최근 일정만, 지난 기사는 기록 탭 (2026-10-22)

| 화면 | 변경 | 이유 |
|---|---|---|
| 와이어(홈) | 일정 카드 2개: **이번 일정**(예정·진행 중 중 가장 가까운 것) + **지난 일정**(그 직전). 예정이 없으면 최근 일정 2개(지난 일정 · 그 전 일정) | 홈은 "이번 주에 무슨 일이 있나"만. 주(週) 경계가 아니라 일정 순서로 골라 한 주를 쉬어도 비지 않음 |
| 와이어(홈) | 마감된 일정 카드에 결과 한 줄(팀별 승·무·패, 득점 1위). 기존 `GET /sessions/{id}/summary` 사용 | 기사를 열지 않아도 지난 결과 확인 |
| 와이어(홈) | 기사는 위 두 일정의 게시 기사만, 최신 3개 + 작은 [기사 더보기] → 기록 탭 [기사] | 오래된 기사가 홈을 채우지 않게 |
| 와이어(홈) | 태그 칩 제거(기록 탭으로 이동) | 두 일정 기사는 많아야 4건이라 거를 필요가 없음 |
| 기록 탭 | [개인 기록 · 수상 내역 · **기사**]. 태그 칩 + 일정 날짜별 묶음 + 20개씩 [더 불러오기] | 지난 기사는 기록실에서 찾아봄 |
| 기록 탭 | 탭·태그를 주소에 둠(`/records?tab=articles&tag=천적`). 기사 상세의 [뒤로]는 그 주소로, 하단 탭은 '기록' 강조(Link state `from`) | 기사를 읽고 돌아와도 보던 탭·태그 유지 |

- API: 기사 응답에 `sessionDate`(일정 날짜) 추가. 화면이 일정별로 묶을 때 사용
- API 수정: `GET /articles?beforeId=` 페이지 커서를 게시 순서와 맞춤. 게시본은 `PUBLISHED_AT` 순으로 정렬하는데 커서는 `ARTICLE_ID`로 잘라서, 검토 대기였던 옛 기사를 나중에 게시하면 그 뒤 기사들이 다음 페이지에서 빠졌다 → 게시본은 `(PUBLISHED_AT, ARTICLE_ID) < 커서` 로 비교(관리자 전체 목록은 기존대로 ID). 테스트 `test_article_pages_follow_publish_order`
- 프론트: 기사 카드를 `components/ArticleCard.tsx`로 분리(와이어·기록 탭 공용)

## 3-6. 레이팅은 DB에서만 + 설정 화면 설명 (2026-10-22)

**레이팅 비공개(관리자 포함)**: 선수별 실력 점수는 화면·API 어디에서도 보여 주지 않고 DB에서만 확인한다.

| 위치 | 변경 |
|---|---|
| `GET /admin/ratings`, `GET /admin/ratings/{memberId}/history` | 삭제(404) |
| 설정 화면 "Hidden Rating 보기" 표 | 삭제 |
| 일정 상세(관리자) 팀원 `ratingSnapshot` · `confidenceSnapshot` | 응답에서 제외. 팀 단위 `avgRatingSnapshot` · `strengthSnapshot`은 유지 |
| 팀 편성 미리보기 팀원 `rating` | 응답에서 제외. 팀 평균·편차·후보 수·seed 등 편성 정보는 유지(팀 편성 화면 "관리자 상세") |
| 시작 레이팅 입력(멤버 추가 `이름 숫자`) | 그대로(입력만 가능, 조회 불가) |

- 테스트는 `conftest.Api.ratings_db()` / `rating_history_db()`로 DB에서 직접 확인. `rating_service.rating_rows`·`rating_history`는 API 없이 점검용으로만 남김
- DB 확인 SQL

```sql
-- 현재 레이팅(높은 순)
SELECT M.NAME, ROUND(R.CURRENT_RATING, 1) AS RATING, R.MATCH_SAMPLE_COUNT AS GAMES, R.LAST_PLAYED_DATE, M.INITIAL_RATING
  FROM PLAYER_RATING R JOIN MEMBER M ON M.MEMBER_ID = R.MEMBER_ID
 WHERE R.CLUB_ID = (SELECT CLUB_ID FROM CLUB WHERE CLUB_SLUG = 'sanha')
 ORDER BY R.CURRENT_RATING DESC;

-- 한 선수의 경기별 변동(재계산으로 무효 처리된 이력 제외)
SELECT H.CREATED_AT, ROUND(H.BEFORE_RATING, 1) AS BEFORE_R, ROUND(H.AFTER_RATING, 1) AS AFTER_R,
       ROUND(H.CHANGE_AMOUNT, 2) AS CHANGE_R, ROUND(H.AFTER_CONFIDENCE, 2) AS CONFIDENCE, H.CHANGE_REASON, H.REFERENCE_ID AS MATCH_ID
  FROM PLAYER_RATING_HISTORY H JOIN MEMBER M ON M.MEMBER_ID = H.MEMBER_ID
 WHERE M.NAME = '홍길동' AND H.VOIDED_YN = 0
 ORDER BY H.RATING_HISTORY_ID;
```

**설정 화면**: 설정 키(영문 변수명)를 화면에서 모두 지우고, 항목마다 이름 · 한 줄 설명 · 기본값 + **(?) 버튼**. (?)를 누르면 항목 바로 아래에 "이렇게 동작해요 / 올리면 / 내리면 / 참고"가 펼쳐진다. 문구는 `frontend/src/pages/admin/settingsHelp.ts` 한 곳에서 관리(새 설정이 생기면 여기에 추가, 없으면 서버 설명을 이름으로 쓰고 고급 묶음에 붙음). 묶음: 경기 / 기사 / 팀 자동 편성 / 실력 점수 계산(고급).

## 3-7. 디자인 E(매니저 게임형) + MVP 제거 (2026-10-22)

**디자인**: 시안 E(축구 매니저 게임 느낌)를 앱 전체에 적용. 어두운 바탕 + 클럽 빨강 + 숫자는 좁은 글꼴(Barlow Condensed).

| 위치 | 변경 | 이유 |
|---|---|---|
| 색 · 글꼴 (`styles/global.css`, `index.html`) | 색 변수(`--bg` `--card` `--accent` …)를 다크로 바꾸고 화면은 변수만 쓰게 정리. 글꼴: 숫자·영문 머리 Barlow Condensed, 본문 Noto Sans KR, 시계 IBM Plex Mono | 화면마다 색을 따로 고치지 않고 변수 한 곳에서 테마 관리 |
| 탭 첫 화면 머리 (`ClubBar`, `Crest`) | 빨강 세로 줄무늬 띠 + 방패 엠블럼(클럽 이름) + 제목 + 관리자 버튼. 와이어 · 일정 · 기록실 · 선수단 공통 | 흰/빨 줄무늬 유니폼을 앱에 맞게 띠로만 사용 |
| 와이어(홈) | 클럽 바(오늘 날짜 · [다음 일정 D-n]) → 요약 줄(멤버 · 올해 일정 · 올해 기사) → LIVE → **NEXT FIXTURE**(상태 · 팀 편성 · 장소 · 참석 막대) → **LAST MATCHDAY**(팀별 경 · 승 · 무 · 패 · 득실 · 흐름, 득점 1위 · 도움 1위 · 총 골) → **INBOX**(최신 3건, 안 읽은 기사 점 + "새 소식 N", [소식 전체 보기] → 기록 탭 기사) | 3-5의 "이번·지난 일정만" 원칙은 유지하고 화면 구성만 매니저 게임처럼 |
| 하단 탭 | '멤버' → **'선수단'** | 축구팀 용어 |
| 팀 색 (`lib/format.ts`) | 어두운 바탕에서 구분되게 A 파랑 · B 주황 · C 보라 · D 청록 · E 분홍 · F 올리브 | 다크 대비 |

- API 추가: `GET /summary` → `{year, activeMembers, sessions, articles}`(클럽 시간대 기준 올해, 취소 일정 제외, 게시 기사만). 와이어 요약 줄용
- 읽음 표시: 기사 상세를 열면 브라우저 `localStorage`(`clubwire.read.{slug}`, 최근 300건)에 기록. 서버 저장 없음 → 기기마다 따로, 저장소가 막힌 브라우저는 새로고침 전까지만 기억
- `app/core/timeutil.local_today(tz)`: 클럽 시간대 기준 오늘 날짜

**MVP 제거**: 일정마감 화면의 MVP 선정을 없애고 MVP 자체를 쓰지 않는다.

| 위치 | 변경 |
|---|---|
| 일정마감 화면 | MVP · 수동 타이틀 선택 삭제. [일정마감]은 `POST /sessions/{id}/close`만 호출 |
| `alembic 0004` | 기존 클럽의 `TITLE_TYPE` 'MVP'를 `ACTIVE_YN = 0`으로(데이터만, 구조 변경 없음). 새 클럽 기본 타이틀에서도 제외 |
| 지난 MVP 이력 | `MEMBER_TITLE`에서 지우지 않음. `GET /titles/awards`는 활성 타이틀만 보여 주므로 수상 내역 · 선수 화면에서 사라짐 |
| 기록 | 개인 기록 표의 MVP 열 · 정렬, 선수단 MVP 배지, 응답의 `mvpCount` 삭제(DB 컬럼 `MVP_COUNT`는 유지) |
| 샘플 데이터 | `scripts/gen_sample_data.py`에서 MVP 수여를 빼고 `ypr_sample_data.sql` 다시 생성 |

- 되돌리기: `alembic downgrade 0003`이면 'MVP' 타이틀이 다시 활성화되고 지난 이력도 다시 보인다(화면의 선택 UI는 코드 되돌림 필요)
- DB 확인

```sql
SELECT TITLE_CODE, TITLE_NAME, ACTIVE_YN FROM TITLE_TYPE
 WHERE CLUB_ID = (SELECT CLUB_ID FROM CLUB WHERE CLUB_SLUG = 'sanha');
```

**버그 수정 – 바텀시트(팝업) 스크롤**: 일정 상세의 [다음 경기 만들기] 시트가 하단 버튼 영역(`.bar-actions`, sticky + z-index) 안에서 그려져 하단 탭 메뉴보다 아래 층이 됨 → 시트 아래쪽 [경기 만들기]가 탭 메뉴에 가려지고 휠·드래그가 뒤 화면으로 넘어감.
- `components/ui.tsx` `Sheet`: `createPortal`로 `document.body`에 바로 그림(어느 화면에서 열어도 탭 메뉴까지 덮음), 열려 있는 동안 `body` 스크롤 잠금
- `global.css` `.sheet`: `overscroll-behavior: contain`(시트 끝에서 뒤 화면으로 스크롤이 넘어가지 않음), `max-height: 92dvh`(모바일 주소창 높이 반영), 내용은 줄어들지 않고 시트가 스크롤
- 같은 컴포넌트를 쓰는 시트 5개(다음 경기 · 관리자 PIN · 골 기록 · 출전 명단 · 팀 이동)에 함께 적용

## 3-8. 요약 줄 링크 + 선수 프로필(가입일 · 출생연도) (2026-10-23)

| 위치 | 변경 | 이유 |
|---|---|---|
| 와이어 요약 줄 | 숫자가 `–`로만 보이던 버그 수정. 칸을 누르면 이동: 멤버 → 선수단, 올해 일정 → 일정, 올해 기사 → 기록 탭 [기사] | 원인: `/summary`가 `ZoneInfo('Asia/Seoul')`을 쓰는데 Windows Python에는 시간대 DB가 없어 500 |
| `app/core/timeutil.py` | `club_tz()`: ZoneInfo를 못 찾으면 고정 오프셋(Asia/Seoul = UTC+9, 서머타임 없음), 그것도 없으면 UTC | tzdata 설치 전에도 동작 |
| `requirements.txt` | `tzdata` 추가 | Windows에서도 정식 시간대 DB 사용 |
| 와이어 요약 줄 | 불러오기 실패 시 줄 아래 [다시 시도] | 실패를 `–`로만 숨기지 않음 |
| `MEMBER.BIRTH_YEAR`(alembic 0005) | 출생연도 SMALLINT(NULL 허용). 가입일은 기존 `JOINED_AT` 사용 | 나이 대신 연도만 저장(해가 바뀌어도 그대로) |
| `PATCH /members/{id}` | `joinedAt` · `birthYear` 추가. 보낸 항목만 반영, `null`을 보내면 지움(이름 등 다른 항목은 기존처럼 null = 변경 없음). 출생연도 1900~올해, 가입일은 미래 불가(서버 UTC 차이로 하루 여유) | 이름만 고칠 때 프로필 값이 지워지지 않게 |
| `GET /stats/members/{id}` | `profile: {joinedAt, birthYear}` 추가(공개) | 선수 화면 표시용. 목록 API(`/stats/members`)에는 넣지 않음 |
| 선수 화면 | 이름 아래 `2021.03.14 가입 · 1992년생`(있는 것만). 관리자 모드면 [선수 정보] 칸(가입일 날짜 · 출생연도 숫자 4자리, 비우고 저장하면 지움) | 관리자가 선수 화면에서 바로 입력, 결과는 모두에게 보임 |

- 테스트: `test_member_profile_joined_and_birth_year`, `test_summary_without_tzdata`
- DB 확인

```sql
SELECT NAME, JOINED_AT, BIRTH_YEAR FROM MEMBER
 WHERE CLUB_ID = (SELECT CLUB_ID FROM CLUB WHERE CLUB_SLUG = 'sanha') ORDER BY NAME;
```

## 3-9. 이달의 MVP = 그 달 실력 점수 상승률 1위 (2026-10-23)

운영진이 고르는 MVP는 없다(주간 수동 MVP는 3-7에서 제거). MVP는 **이달의 MVP** 하나이고 자동으로 뽑는다.

| 항목 | 결정 | 이유 |
|---|---|---|
| 기준 | 상승률 = (그 달 마지막 경기 후 점수 − 그 달 첫 경기 전 점수) ÷ 첫 경기 전 점수 × 100. `PLAYER_RATING_HISTORY`(무효 아닌 경기 이력)에서 계산, 확정된 경기만 | 출발 점수가 달라도 비교되게 % 기준(요청). 재계산되면 새 이력 기준으로 다시 계산됨 |
| 후보 자격 | 그 달 출전 일정 **2회 이상**(설정 `MONTHLY_MVP_MIN_SESSIONS`, 설정 화면 '이달의 MVP') + 상승률 > 0 | 한 번 나와 크게 오른 경우를 거름 |
| 순위 · 동률 | 상승률(소수 둘째 자리) 높은 순, 같으면 경기 수 많은 순. 1위가 동률이면 공동 수여 | |
| 월 마감 | 클럽 현지 날짜로 **다음 달 1일**이 되고 그 달 일정이 모두 마감/취소되면. 서버 루프(`jobs/monthly.py`, 시작 때 1번 + 10분마다) + 지난달 일정을 늦게 [일정마감]하면 그 자리에서 | 열린 일정이 있으면 그 일정의 경기가 아직 반영 안 됐으므로 기다림 |
| 한 번만 | 그 달 수여 이력이 있으면(관리자가 취소한 것 포함) 다시 하지 않음 | 서버 재시작 · 여러 대에서 중복 방지(클럽 행 잠금 후 확인) |
| 타이틀 | `TITLE_TYPE` `MONTHLY_MVP`(이달의 MVP, MONTHLY, AUTO, `MONTHLY_RATING_RISE`, `COUNTS_AS_MVP_YN = 1`). 기간 1일~말일, `FACTS_JSON = {metric: risePercent, value, sessions, games}` | 수상 내역 · 선수 화면에 '9월 · +4.4%'. `MVP_COUNT` = 이달의 MVP 수 |
| 기사 | `MONTHLY_MVP`. 상승률 · 성적 · 특히 많이 오른 경기(최대 3) · 가장 크게 오른 날 · 2·3위 · 선정 기준. **게시 설정과 상관없이 바로 게시**, 그 달 마지막 일정에 붙임 | 요청: 마감되면 자동 발행 |
| 홈 | **MVP RACE** 패널: 이번 달 후보 1~3위(이름 · 상승률 · 일정/경기 수), 아래 줄에 지난달 MVP → 발표 기사 | 요청 |
| 공개 범위 | 화면 · API · 기사 · AI 입력 모두 **상승률(%)만**. 점수 자체는 계속 DB에서만. 기사 용어는 '실력 점수' | 3-6(레이팅 DB 전용) 유지 |

- API: `GET /stats/mvp-race` → `{month, minSessions, candidates[{rank, memberId, name, risePercent, sessions, games}], lastMonth{month, articleId, winners[]}}`
- 코드: `app/services/mvp_service.py`(집계 · 월 마감), `app/jobs/monthly.py`(루프), `writer.py` 프롬프트 v3 + 템플릿 작성기, `title_service`(주간 자동 집계에서 MONTHLY 제외 · 기간 계산), `stats_service`(비활성 타이틀은 타이틀 수 · MVP 수에서 제외)
- alembic 0006: 컬럼 설명(COMMENT)만 변경. '이달의 MVP' 타이틀 정의는 새 클럽은 생성 때, 기존 클럽은 첫 월 마감 때 앱이 만든다(샘플 SQL을 다시 넣어도 동작)
- 배포 직후: 서버가 켜지면 바로 지난달(9월)을 마감해 9월 MVP 기사가 올라온다(샘플 데이터 기준)

```sql
-- 이달의 MVP 이력
SELECT MT.PERIOD_START, M.NAME, JSON_EXTRACT(MT.FACTS_JSON, '$.value') AS RISE_PCT, MT.CANCELLED_YN
  FROM MEMBER_TITLE MT JOIN TITLE_TYPE T ON T.TITLE_TYPE_ID = MT.TITLE_TYPE_ID JOIN MEMBER M ON M.MEMBER_ID = MT.MEMBER_ID
 WHERE T.TITLE_CODE = 'MONTHLY_MVP' ORDER BY MT.PERIOD_START DESC;

-- 한 달 다시 뽑기(예: 2026-09). 수여 이력을 지우면 다음 루프(10분 이내) 또는 서버 재시작 때 다시 마감
DELETE MT FROM MEMBER_TITLE MT JOIN TITLE_TYPE T ON T.TITLE_TYPE_ID = MT.TITLE_TYPE_ID
 WHERE T.TITLE_CODE = 'MONTHLY_MVP' AND MT.PERIOD_START = '2026-09-01';
```

## 3-10. 와이어는 기사가 주인공 + 샘플 데이터 10/17까지 (2026-10-23)

| 위치 | 변경 | 이유 |
|---|---|---|
| 와이어 순서 | 클럽 바 → 요약 한 줄 → LIVE → 다음 일정 → **THE WIRE(기사)** → MVP 한 줄 → 지난 경기(LAST MATCHDAY, 맨 아래) | 기사가 첫 화면 위쪽에 오게 |
| 요약 줄 | 숫자 · 이름을 나란히 한 줄(높이 약 34px). 누르면 이동은 그대로 | 작게 |
| THE WIRE | 빨간 윗선 카드. 첫 기사는 헤드라인(24px · 요약 3줄), 나머지 2건은 제목 줄. 안 읽은 점 · '새 소식 N' · [소식 전체 보기] 유지. 개수 3건 그대로 | 기사 돋보이게 |
| MVP | 패널 → 한 줄 띠(MVP · 월 · 1~3위 이름 · 상승률). 이름 누르면 선수 화면. 후보가 없으면 지난달 MVP를 대신 표시. 선정 기준은 띠의 설명(aria · title)으로 | 최대한 작게 |
| 다음 일정 없음 | 머리 없이 한 줄('NEXT FIXTURE 예정된 일정이 없어요') | 기사 자리 확보 |

- 샘플 데이터(`ypr_sample_data.sql`) 다시 생성: **2026-07-04 ~ 10-17 매주 토요일 16회**. 생성기가 시계를 옮기다 1일 00:10을 지나면 월 마감 → 7 · 8 · 9월 이달의 MVP 타이틀 + 발표 기사. 10월은 후보 진행 중(11월이 되면 서버가 자동 마감). 10/17 마감 기사는 검토 대기, 예정 일정 없음
- 생성기 기사 템플릿에 이달의 MVP 문구(조사 처리) 추가, 프리뷰 첫 문장의 요일을 날짜에서 계산(기존: '일요일' 고정)

## 3-11. AI 창의성 · 답변 최대 길이 설정 + 기본형 기사 (2026-10-23)

| 항목 | 결정 | 이유 |
|---|---|---|
| 창의성 | `AI_TEMPERATURE`(기본 0.7, 0~2) → OpenAI `temperature`. 관리자 설정 화면 '기사' 묶음 + (?) 도움말 | 서버 재시작 없이 클럽별로 조절. 추론형 모델처럼 temperature를 안 받는 모델이면 빼고 한 번 더 요청 |
| 답변 최대 길이 | `AI_MAX_OUTPUT_TOKENS`(기본 2000, 300~8000) → `max_completion_tokens` | 비용 상한. 잘리면(`finish_reason = length`) 검증 실패로 보고 재시도 |
| 기본형 기사 | AI 실패(키 없음 · 401 · 429 크레딧/한도 · 연결/시간 초과 · 검증 실패) → 템플릿으로 같은 사실을 써서 `GENERATED`, 평소 게시 규칙 적용 | 기사가 비지 않게. 원인은 `ERROR_MESSAGE`에 남기고 [다시 쓰기]로 AI 재시도 |
| 템플릿 | 샘플 데이터 생성기의 작성기를 `app/integrations/openai/template_writer.py`(`TemplateArticleWriter`)로 옮겨 앱 · 생성기가 같이 씀. 예전 Stub 작성기는 삭제 | 조사 처리 · 같은 종류 사실 묶기 · 제목 고르기가 이미 검증된 문체 |
| 표시 | 기사 응답에 `basic`(기본형 여부). 관리자: '기본형' 배지 + 이유, 공개: 기사 맨 아래 안내 문구 | 독자에게도 AI 기사와 구분 |
| `AI_PROVIDER` | `auto`(키 있으면 openai, 없으면 template) / `openai` / `template`(`stub`도 같은 뜻으로 받음) | 이름 정리 |

- alembic 0007: `AI_ARTICLE.MODEL_NAME` · `ERROR_MESSAGE` 컬럼 설명만 변경. 설정값은 `SYSTEM_CONFIG`(없으면 기본값)
- `requirements.txt`: `openai>=1.55`(`max_completion_tokens`)
- 테스트 `tests/test_article_writer.py`(OpenAI 클라이언트 대역으로 요청 인자 · 실패별 기본형 대체 확인)
- 샘플 데이터는 그대로(생성기가 같은 작성기를 써서 기사 문장이 바뀌지 않음을 다시 생성해 확인)

## 3-12. 이달의 득점왕 · 도움왕 + 연속 참가 + 선수 화면(수상 이력 · 케미 맵) (2026-10-23)

| 항목 | 결정 | 이유 |
|---|---|---|
| 이달의 득점왕 · 도움왕 | `MONTHLY_TOP_SCORER` · `MONTHLY_TOP_ASSIST`(MONTHLY, AUTO). 월 마감(이달의 MVP와 같은 시점)에 그 달 확정 경기 골 · 도움 1위, 동점 공동, 0개면 없음. 이주의 득점왕 · 도움왕은 그대로 | 요청: 주간 + 월간 둘 다 |
| 월 마감 '한 번만' | 타이틀 종류마다 따로 판단(그 달 수여 이력이 있으면 그 종류만 건너뜀) | 배포 전에 MVP만 발표된 9월도 득점왕 · 도움왕은 채워짐. MVP 기사는 MVP가 새로 나온 달만 |
| MVP 기사 | `monthlyMvp.monthlyTitles`(득점왕 · 도움왕) 추가 → 마지막 문단 한 문장. 프롬프트 v4 | 요청 |
| 연속 참가 | `ATTEND_STREAK_10/20/30/40/50`("연속 참가 n회", SESSION, AUTO, `ATTENDANCE_STREAK`). [일정마감] 때 그 일정 참석자 중 연속 횟수가 정확히 10 · 20 · 30 · 40 · 50인 사람에게 | |
| 참가 기준 | 마감된 일정의 **참석 명단**(`SESSION_MEMBER.ATTENDANCE_STATUS = ATTENDING`). 뛴 경기 수와 무관. 취소된 일정은 세지도 끊지도 않음. 빠진 일정이 나오면 끊김 | 요청: 그 날짜 참가 기준 |
| 다시 수여 | 끊겼다가 다시 10회가 되면 또 수여('연속 참가 10회 ×2'). 같은 일정에서는 한 번만 | 요청 |
| 수상 이력 | 선수 화면: 최근(기간 끝 날짜 순) 5개를 카드로 가로 넘김, 더 있으면 마지막 칸 [전체 n개] → 아래 목록. 카드: 타이틀 · 값(3골 / +4.2% / 10회 연속) · 기간(이달의 ~는 'n월') · 공동 | 요청 |
| 케미 맵 | 자주 같은 팀 · 자주 맞붙은 선수 목록 → 방사형 관계도(`components/ChemistryMap.tsx`). 가운데 = 나, 위 반원 = 같은 팀 5명, 아래 반원 = 맞대결 5명. 선 굵기 = 경기 수, 색 = 승률 3단계(50%↑ 파랑 · 30~50% 회색 · 30%↓ 주황), 이름 아래 숫자, 노드 누르면 그 선수. 정확한 값은 [목록으로 보기] | 요청(C안). 파랑/주황은 색약에도 구분되고(빨강/초록은 구분 안 됨), 색만으로 읽지 않게 숫자를 같이 씀 |

- API 변경 없음(기존 `/stats/members/{id}`, `/titles/awards` 값으로 그림). 타이틀 정의 행은 새 클럽은 생성 때, 기존 클럽은 처음 필요할 때 앱이 만든다
- alembic 0008: `TITLE_TYPE` 설명 · `AUTO_RULE` 설명만 변경
- 샘플 데이터 다시 생성: 7 · 8 · 9월 이달의 득점왕 · 도움왕, 연속 참가 10회(4명) 포함
- 테스트 `tests/test_titles_v2.py`
- 방사형 케미 맵은 3-13에서 [풋살 피치 | 궁합 티어표]로 교체

## 3-13. 케미 = 풋살 피치 | 궁합 티어표 + 수상 내역 기간 · 상 별 조회 (2026-10-23)

| 항목 | 결정 | 이유 |
|---|---|---|
| 케미 화면 | 방사형 맵 → `components/Chemistry.tsx`. 위 토글 [풋살 피치 \| 궁합 티어표], 기본 = 풋살 피치. [목록으로 보기] 제거 | 요청(시안 4개 중 피치 · 티어표 채택) |
| 풋살 피치 | 세로 코트, 가운데 원 = 나. 위 진영 = 자주 같은 팀 5명, 아래 진영 = 자주 맞붙은 5명. 경기 수 1 · 2위는 가운데 가까운 공격 자리, 3 · 4위는 수비 자리, 5위는 골키퍼 자리. 원 크기 = 경기 수, 색 = 승률 3단계(3-12와 같은 파랑 · 회색 · 주황), 이름 아래 'n경기 · 승률', 누르면 그 선수 | 많이 함께한 사람이 나와 가까이 보이게. 5명 = 풋살 한 팀 |
| 궁합 티어표 | 같은 팀: 찰떡(같이 뛴 승률 50%↑) · 보통 · 상극(30%↓). 맞대결: 먹잇감(내 승률 50%↑) · 호각 · 천적(30%↓). 칸 안은 경기 수 순 칩, 누르면 그 선수. 없으면 '없음' | 피치는 5명만 보이므로 나머지까지 한 번에. 기준값은 피치 색과 같게 |
| 몇 명까지 | 선수 화면은 `GET /stats/members/{id}?top=10`(기본 5, 1~20). 피치는 상위 5명, 티어표는 받은 10명 전부 | 기존 호출(기본 5)은 그대로 |
| 수상 내역(기록 탭) | 기간 조회가 기본: [◀ n월 ▶] + [올해] [전체], 기본 = 이번 달. 다음 달 버튼은 이번 달에서 막힘 | 요청 |
| 상 별 조회 | 기간 아래 상 칩([전체] + 타이틀 종류). 연속 참가 10~50회는 칩 하나 '연속 참가'로 묶음. 기간과 함께 걸림 | 요청(상 칩 + 기간 함께) |
| 화면 구성 | '{기간} · 수상 n건 · m명' 한 줄, 많이 받은 선수 5명, 아래 수상 목록(기간 묶음). 선수 이름 누르면 그 선수 화면 | 요청 |
| 주소 | `?tab=awards&period=2026-10\|year\|all&title=코드` → 새로고침 · 뒤로가기에도 조건 유지 | |
| 수상 API | `GET /titles/awards`에 `titleCode`(끝이 `_`면 앞부분 일치: `ATTEND_STREAK_` = 연속 참가 전부) · `limit`(기본 100, 최대 1000) 추가. 기존 `memberId` · `from` · `to` 그대로 | 기간 '전체'를 한 번에 받기 위해 limit 상향 허용 |

- DB · alembic 변경 없음(0008 그대로), 샘플 데이터 그대로
- 테스트 `tests/test_titles_v2.py`에 `titleCode`(정확 · 앞부분) · 기간 · `limit` · `top` 확인 추가

## 4. 남은 이슈 / 다음 단계

1. **카카오 로그인**: 현재는 클럽 PIN 1개. USER 테이블 + MEMBER↔USER 연결 + 역할(관리자/회원)로 확장 예정. PIN 실패 제한은 메모리 기반(단일 프로세스)
2. **다중 서버 배포**: WebSocket 허브와 PIN 실패 제한이 프로세스 메모리 기반 → 서버 2대 이상이면 Redis Pub/Sub로 교체
3. **조기 종료 후 골 취소**: N골 조기 종료 뒤 골을 취소해도 경기를 자동으로 다시 열지 않음(관리자 판단)
4. **Insight 파라미터 튜닝**: 임계값(복귀 30일, 연승 3 등)은 실제 데이터로 조정 필요(`INSIGHT_CONFIG_PARAM`)
5. **A/B 평가(밸런스 게임)**: 제외. 다시 넣을 경우 Rating 초기값 보정용 별도 Strategy로 붙이면 됨(DB 영향은 AB_* 테이블 추가뿐)
6. **프론트 폰트**: Google Fonts(Barlow Condensed, Noto Sans KR, IBM Plex Mono)를 외부에서 불러온다. 사내망 등에서 막히면 시스템 글꼴로 대체되므로 필요 시 폰트 파일을 `frontend/public`에 넣어 직접 서빙
7. **스토리보드 캔버스**: 코드에는 메모를 반영했지만 디자인 캔버스(A06 남을 팀 선택, S06 탭)는 아직 초안 그대로
