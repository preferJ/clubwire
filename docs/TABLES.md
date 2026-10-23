# Clubwire 테이블 정의서

> 자동 생성: `python scripts/gen_docs.py` (원본: app/models, 설명: app/models/comments.py)  
> MySQL 8.0 / utf8mb4 / InnoDB · 대문자 SNAKE_CASE · BOOLEAN=TINYINT(1) · DATETIME(3)=UTC

## 1. Club / Member / Config

### CLUB

클럽(최상위 tenant). 대부분의 데이터는 CLUB_ID에 귀속  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `CLUB_ID` | BIGINT | N | PK | 클럽 ID |
| 2 | `CLUB_SLUG` | VARCHAR(50) | N |  | 클럽 URL 주소(공개 조회/관리자 진입 경로) |
| 3 | `CLUB_NAME` | VARCHAR(100) | N |  | 클럽명 |
| 4 | `SPORT_TYPE` | VARCHAR(20) | N |  | 종목(현재 FUTSAL만 업무 규칙 구현) |
| 5 | `TIMEZONE` | VARCHAR(50) | N |  | 표시용 시간대(기본 Asia/Seoul) |
| 6 | `CONFIG_VERSION` | INTEGER | N |  | 운영 설정 버전(SYSTEM_CONFIG 변경마다 +1) |
| 7 | `ACTIVE_YN` | BOOL | N |  | 사용 여부(false=비활성, 삭제 대신 사용) |
| 8 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 9 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_CLUB_CLUB_SLUG` (CLUB_SLUG)
- UNIQUE (CLUB_SLUG)

### CLUB_ADMIN

클럽 관리자 PIN(Argon2 해시). 회원 로그인은 추후 확장  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `ADMIN_ID` | BIGINT | N | PK | 관리자 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `ADMIN_NAME` | VARCHAR(50) | Y |  | 관리자 표시명 |
| 4 | `PASSWORD_HASH` | VARCHAR(255) | N |  | 관리자 PIN 해시(Argon2, 평문 저장 금지) |
| 5 | `ACTIVE_YN` | BOOL | N |  | 사용 여부(false=비활성, 삭제 대신 사용) |
| 6 | `LAST_LOGIN_AT` | DATETIME(3) | Y |  | 마지막 관리자 모드 진입 일시 |
| 7 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 8 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_CLUB_ADMIN_CLUB_ID` (CLUB_ID)

### MEMBER

클럽 구성원(경기하는 사람). 삭제 대신 ACTIVE_YN=false  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MEMBER_ID` | BIGINT | N | PK | 멤버 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `NAME` | VARCHAR(50) | N |  | 이름 |
| 4 | `PROFILE_IMAGE_URL` | VARCHAR(500) | Y |  | 프로필 이미지 URL |
| 5 | `DISPLAY_ORDER` | INTEGER | Y |  | 표시 순서 |
| 6 | `ACTIVE_YN` | BOOL | N |  | 사용 여부(false=비활성, 삭제 대신 사용) |
| 7 | `JOINED_AT` | DATE | Y |  | 가입일 |
| 8 | `BIRTH_YEAR` | SMALLINT | Y |  | 출생연도(예: 1992). 선수 프로필에 'n년생'으로 표시 |
| 9 | `INITIAL_RATING` | DOUBLE | Y |  | 시작 Rating(이관·수동 지정, 관리자 전용). NULL이면 설정 INITIAL_RATING. 재계산도 이 값에서 시작 |
| 10 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 11 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_MEMBER_CLUB_ID_ACTIVE_YN` (CLUB_ID, ACTIVE_YN)

### SYSTEM_CONFIG

클럽별 운영 설정값(Rating K, 경기 시간, 밀어내기 규칙 등)  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `CLUB_ID` | BIGINT | N | PK FK→CLUB | 클럽 ID |
| 2 | `CONFIG_KEY` | VARCHAR(60) | N | PK | 설정 키(app/core/club_config.py 정의) |
| 3 | `CONFIG_VALUE` | VARCHAR(200) | N |  | 설정 값(문자열 저장, VALUE_TYPE으로 변환) |
| 4 | `VALUE_TYPE` | VARCHAR(10) | N |  | INT/FLOAT/BOOL/STRING |
| 5 | `DESCRIPTION` | VARCHAR(300) | Y |  | 설명 |
| 6 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |

### SYSTEM_CONFIG_HISTORY

운영 설정 변경 이력  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `HISTORY_ID` | BIGINT | N | PK | 이력 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `CONFIG_KEY` | VARCHAR(60) | N |  | 설정 키 |
| 4 | `BEFORE_VALUE` | VARCHAR(200) | Y |  | 변경 전 값 |
| 5 | `AFTER_VALUE` | VARCHAR(200) | N |  | 변경 후 값 |
| 6 | `CONFIG_VERSION` | INTEGER | N |  | 변경 후 설정 버전 |
| 7 | `CHANGED_BY_ADMIN_ID` | BIGINT | Y | FK→CLUB_ADMIN | 변경 관리자 ID |
| 8 | `CHANGED_AT` | DATETIME(3) | N |  | 변경 일시(UTC) |

제약/인덱스

- INDEX `IX_SYSTEM_CONFIG_HISTORY_CLUB_ID_CHANGED_AT` (CLUB_ID, CHANGED_AT)

## 2. Session / Team

### SESSION

일정(한 번의 모임/경기 날짜). 여러 경기를 포함  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `SESSION_ID` | BIGINT | N | PK | 일정 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `SESSION_DATE` | DATE | N |  | 일정 날짜(현지 날짜) |
| 4 | `TITLE` | VARCHAR(100) | N |  | 일정 제목 |
| 5 | `LOCATION` | VARCHAR(200) | Y |  | 장소 |
| 6 | `STATUS` | VARCHAR(20) | N |  | OPEN/CONFIRMED(일정확정)/IN_PROGRESS/CLOSED(일정마감)/CANCELLED |
| 7 | `TEAM_COUNT` | INTEGER | Y |  | 확정된 팀 수 |
| 8 | `CONFIRMED_AT` | DATETIME(3) | Y |  | [일정확정] 일시 |
| 9 | `CLOSED_AT` | DATETIME(3) | Y |  | [일정마감] 일시(이후 수정 불가) |
| 10 | `CANCELLED_AT` | DATETIME(3) | Y |  | 취소 일시 |
| 11 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 12 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_SESSION_CLUB_ID_SESSION_DATE` (CLUB_ID, SESSION_DATE)

### SESSION_MEMBER

일정 참석자  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `SESSION_MEMBER_ID` | BIGINT | N | PK | 참석 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `MEMBER_ID` | BIGINT | N | FK→MEMBER | 멤버 ID |
| 4 | `ATTENDANCE_STATUS` | VARCHAR(20) | N |  | ATTENDING/ABSENT/PENDING |
| 5 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 6 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_SESSION_MEMBER_SESSION_ID_MEMBER_ID` (SESSION_ID, MEMBER_ID)
- INDEX `IX_SESSION_MEMBER_MEMBER_ID` (MEMBER_ID)

### SESSION_GUEST

게스트(용병). 인원수에만 포함, Rating/통계 없음  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `GUEST_ID` | BIGINT | N | PK | 게스트 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `GUEST_NAME` | VARCHAR(50) | N |  | 게스트 표시명(게스트1 등) |
| 4 | `SESSION_TEAM_ID` | BIGINT | Y | FK→SESSION_TEAM | 배정 팀 |
| 5 | `ACTIVE_YN` | BOOL | N |  | 사용 여부(false=비활성, 삭제 대신 사용) |
| 6 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 7 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_SESSION_GUEST_SESSION_ID` (SESSION_ID)

### SESSION_TEAM

일정 안에서 만든 임시 팀(TEAM A/B/C)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `SESSION_TEAM_ID` | BIGINT | N | PK | 세션 팀 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `GENERATION_ID` | BIGINT | Y | FK→TEAM_GENERATION | 생성 근거 팀 편성 ID |
| 4 | `TEAM_CODE` | VARCHAR(5) | N |  | 팀 코드(A, B, C …) |
| 5 | `DISPLAY_NAME` | VARCHAR(50) | N |  | 표시명 |
| 6 | `DISPLAY_ORDER` | INTEGER | N |  | 팀 표시 순서 |
| 7 | `AVG_RATING_SNAPSHOT` | DOUBLE | Y |  | 확정 당시 평균 Rating |
| 8 | `TEAM_STRENGTH_SNAPSHOT` | DOUBLE | Y |  | 확정 당시 Team Strength |
| 9 | `HEADCOUNT_SNAPSHOT` | INTEGER | Y |  | 확정 당시 인원(게스트 포함) |
| 10 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_SESSION_TEAM_SESSION_ID_TEAM_CODE` (SESSION_ID, TEAM_CODE)

### SESSION_TEAM_MEMBER

팀 배정 멤버(+ 확정 당시 Rating/Confidence Snapshot)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `SESSION_TEAM_MEMBER_ID` | BIGINT | N | PK | 팀 배정 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `SESSION_TEAM_ID` | BIGINT | N | FK→SESSION_TEAM | 세션 팀 ID |
| 4 | `MEMBER_ID` | BIGINT | N | FK→MEMBER | 멤버 ID |
| 5 | `RATING_SNAPSHOT` | DOUBLE | N |  | 배정 당시 Rating |
| 6 | `CONFIDENCE_SNAPSHOT` | DOUBLE | N |  | 배정 당시 Confidence(0~1) |
| 7 | `ASSIGN_TYPE` | VARCHAR(10) | N |  | AUTO(자동 편성)/MANUAL(수동 변경) |
| 8 | `ACTIVE_YN` | BOOL | N |  | 현재 팀 소속 여부(제외 시 false) |
| 9 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 10 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_SESSION_TEAM_MEMBER_SESSION_ID_MEMBER_ID` (SESSION_ID, MEMBER_ID)
- INDEX `IX_SESSION_TEAM_MEMBER_MEMBER_ID` (MEMBER_ID)
- INDEX `IX_SESSION_TEAM_MEMBER_SESSION_TEAM_ID` (SESSION_TEAM_ID)

### TEAM_GENERATION

자동 팀 편성 실행 이력(재현용 Snapshot)  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `GENERATION_ID` | BIGINT | N | PK | 편성 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `STATUS` | VARCHAR(20) | N |  | PREVIEW/CONFIRMED/DISCARDED |
| 4 | `TEAM_COUNT` | INTEGER | N |  | 팀 수 |
| 5 | `ATTENDEE_COUNT` | INTEGER | N |  | 참석 멤버 수 |
| 6 | `GUEST_COUNT` | INTEGER | N |  | 게스트 수 |
| 7 | `ALGORITHM_VERSION` | VARCHAR(50) | N |  | 편성 알고리즘 버전 |
| 8 | `CONFIG_VERSION` | INTEGER | N |  | 사용한 설정 버전 |
| 9 | `CONFIG_SNAPSHOT_JSON` | JSON | N |  | 사용한 설정 전체 Snapshot |
| 10 | `RANDOM_SEED` | BIGINT | N |  | 난수 시드(동일 입력이면 같은 결과) |
| 11 | `CANDIDATE_COUNT` | INTEGER | N |  | 생성한 후보 수 |
| 12 | `VALID_CANDIDATE_COUNT` | INTEGER | N |  | Rating 허용 범위 만족 후보 수 |
| 13 | `TOLERANCE_FALLBACK_YN` | BOOL | N |  | 허용 범위 만족 후보가 없어 최소 차이 후보를 쓴 경우 |
| 14 | `SPREAD_PERCENT` | DOUBLE | N |  | 선택 후보 팀 Strength 차이(%) |
| 15 | `PAIR_PENALTY` | DOUBLE | N |  | 선택 후보 Pair Penalty 합 |
| 16 | `RESULT_JSON` | JSON | N |  | 입력(Rating/Confidence)과 팀별 결과 |
| 17 | `CONFIRMED_AT` | DATETIME(3) | Y |  | 확정 일시 |
| 18 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_TEAM_GENERATION_SESSION_ID` (SESSION_ID)

### TEAM_ASSIGNMENT_LOG

팀 확정 후 수동 변경 이력(지각 추가/이동/제외)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `LOG_ID` | BIGINT | N | PK | 이력 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `ACTION` | VARCHAR(10) | N |  | ADD/MOVE/REMOVE |
| 4 | `MEMBER_ID` | BIGINT | Y | FK→MEMBER | 멤버 ID |
| 5 | `GUEST_ID` | BIGINT | Y | FK→SESSION_GUEST | 대상 게스트 ID |
| 6 | `FROM_TEAM_ID` | BIGINT | Y | FK→SESSION_TEAM | 이전 팀 |
| 7 | `TO_TEAM_ID` | BIGINT | Y | FK→SESSION_TEAM | 이후 팀 |
| 8 | `REASON` | VARCHAR(200) | Y |  | 사유 |
| 9 | `ADMIN_ID` | BIGINT | Y | FK→CLUB_ADMIN | 처리 관리자 ID |
| 10 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_TEAM_ASSIGNMENT_LOG_SESSION_ID` (SESSION_ID)

## 3. Match

### MATCH_GAME

경기 1건. 일정은 미리 만들지 않고 다음 경기를 1건씩 생성(대진은 관리자 지정)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MATCH_ID` | BIGINT | N | PK | 경기 ID |
| 2 | `SESSION_ID` | BIGINT | N | FK→SESSION | 일정 ID |
| 3 | `GAME_NO` | INTEGER | N |  | 일정 내 경기 번호 |
| 4 | `TEAM_A_ID` | BIGINT | N | FK→SESSION_TEAM | A측 팀 |
| 5 | `TEAM_B_ID` | BIGINT | N | FK→SESSION_TEAM | B측 팀 |
| 6 | `SCORE_A` | INTEGER | N |  | A측 점수(GOAL 이벤트와 같은 트랜잭션에서만 변경) |
| 7 | `SCORE_B` | INTEGER | N |  | B측 점수 |
| 8 | `GAME_STATUS` | VARCHAR(20) | N |  | READY/RUNNING/PAUSED/FINISHED/CANCELLED |
| 9 | `GAME_DURATION_SEC` | INTEGER | N |  | 경기 시간(초, 생성 시 설정 Snapshot) |
| 10 | `AUTO_END_YN` | BOOL | N |  | 시간 종료 시 자동 종료 여부 |
| 11 | `EARLY_END_GOALS` | INTEGER | Y |  | N골 도달 시 조기 종료(NULL=미사용) |
| 12 | `STARTED_AT` | DATETIME(3) | Y |  | 시작 일시(타이머 원본) |
| 13 | `PAUSED_AT` | DATETIME(3) | Y |  | 일시정지 시작 일시 |
| 14 | `PAUSED_SECONDS` | DOUBLE | N |  | 누적 일시정지 초 |
| 15 | `FINISHED_AT` | DATETIME(3) | Y |  | 종료 일시 |
| 16 | `END_REASON` | VARCHAR(20) | Y |  | ADMIN/TIME_UP/EARLY_GOAL |
| 17 | `FINALIZED_AT` | DATETIME(3) | Y |  | 기록 확정 일시(NULL=미확정). 확정 시 파생 데이터 반영 |
| 18 | `WIN_TEAM_ID` | BIGINT | Y | FK→SESSION_TEAM | 승리 팀(NULL=무승부, 확정 시 기록) |
| 19 | `TEAM_A_HEADCOUNT` | INTEGER | Y |  | 시작 시 A측 인원(게스트 포함) |
| 20 | `TEAM_B_HEADCOUNT` | INTEGER | Y |  | 시작 시 B측 인원(게스트 포함) |
| 21 | `TEAM_A_STRENGTH` | DOUBLE | Y |  | 시작 시 A측 Strength(비공개) |
| 22 | `TEAM_B_STRENGTH` | DOUBLE | Y |  | 시작 시 B측 Strength(비공개) |
| 23 | `EXPECTED_A` | DOUBLE | Y |  | 시작 시 A측 기대 승률(비공개, 이변 판단) |
| 24 | `VERSION` | INTEGER | N |  | 변경 버전(낙관적 확인용) |
| 25 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 26 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_MATCH_GAME_SESSION_ID_GAME_NO` (SESSION_ID, GAME_NO)

### MATCH_MEMBER

경기 실제 출전자(시작 시 팀 명단으로 생성, 결장/교체 수정 가능)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MATCH_MEMBER_ID` | BIGINT | N | PK | 출전 ID |
| 2 | `MATCH_ID` | BIGINT | N | FK→MATCH_GAME | 경기 ID |
| 3 | `MEMBER_ID` | BIGINT | N | FK→MEMBER | 멤버 ID |
| 4 | `SESSION_TEAM_ID` | BIGINT | N | FK→SESSION_TEAM | 출전 팀 |
| 5 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_MATCH_MEMBER_MATCH_ID_MEMBER_ID` (MATCH_ID, MEMBER_ID)
- INDEX `IX_MATCH_MEMBER_MEMBER_ID` (MEMBER_ID)

### MATCH_EVENT

경기 이벤트 타임라인(삭제 없음, 골 취소는 CANCELLED_YN + GOAL_CANCEL)  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `EVENT_ID` | BIGINT | N | PK | 이벤트 ID |
| 2 | `MATCH_ID` | BIGINT | N | FK→MATCH_GAME | 경기 ID |
| 3 | `EVENT_TYPE` | VARCHAR(20) | N |  | START/PAUSE/RESUME/GOAL/GOAL_CANCEL/END/FINALIZE/UNFINALIZE/CANCEL/MEMBER_ADD/MEMBER_REMOVE |
| 4 | `TEAM_ID` | BIGINT | Y | FK→SESSION_TEAM | 득점 팀(GOAL) / 대상 팀 |
| 5 | `SCORER_MEMBER_ID` | BIGINT | Y | FK→MEMBER | 득점자(자책골이면 자책 선수, 게스트 득점이면 NULL) |
| 6 | `ASSIST_MEMBER_ID` | BIGINT | Y | FK→MEMBER | 도움(선택) |
| 7 | `MEMBER_ID` | BIGINT | Y | FK→MEMBER | 출전 명단 변경 대상 |
| 8 | `OWN_GOAL_YN` | BOOL | N |  | 자책골 여부 |
| 9 | `GUEST_GOAL_YN` | BOOL | N |  | 게스트 득점 여부 |
| 10 | `ELAPSED_SEC` | INTEGER | Y |  | 경기 경과 초 |
| 11 | `REMAINING_SEC` | INTEGER | Y |  | 남은 초(음수=추가 시간) |
| 12 | `REF_EVENT_ID` | BIGINT | Y | FK→MATCH_EVENT | 취소 대상 이벤트 |
| 13 | `CANCELLED_YN` | BOOL | N |  | 취소된 골 여부 |
| 14 | `IDEMPOTENCY_KEY` | VARCHAR(64) | Y |  | 중복 요청 방지 키(MATCH_ID와 UNIQUE) |
| 15 | `MEMO` | VARCHAR(200) | Y |  | 메모 |
| 16 | `ADMIN_ID` | BIGINT | Y | FK→CLUB_ADMIN | 처리 관리자 ID |
| 17 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_MATCH_EVENT_MATCH_ID_IDEMPOTENCY_KEY` (MATCH_ID, IDEMPOTENCY_KEY)
- INDEX `IX_MATCH_EVENT_ASSIST_MEMBER_ID` (ASSIST_MEMBER_ID)
- INDEX `IX_MATCH_EVENT_MATCH_ID_CREATED_AT` (MATCH_ID, CREATED_AT)
- INDEX `IX_MATCH_EVENT_SCORER_MEMBER_ID` (SCORER_MEMBER_ID)

## 4. Rating / Stats / Pair / Title

### PLAYER_RATING

현재 Hidden Rating(파생, 재계산 가능)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MEMBER_ID` | BIGINT | N | PK FK→MEMBER | 멤버 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `CURRENT_RATING` | DOUBLE | N |  | 현재 Rating(비공개) |
| 4 | `MATCH_SAMPLE_COUNT` | INTEGER | N |  | 확정 경기 출전 수(Confidence 원천값) |
| 5 | `LAST_PLAYED_DATE` | DATE | Y |  | 마지막 출전 일정 날짜(Confidence 원천값) |
| 6 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |

제약/인덱스

- INDEX `IX_PLAYER_RATING_CLUB_ID` (CLUB_ID)

### PLAYER_RATING_HISTORY

Rating 변경 이력(감사 목적 보존, 재계산 시 VOIDED 처리)  
구분: **Derived(이력 보존)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `RATING_HISTORY_ID` | BIGINT | N | PK | 이력 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `MEMBER_ID` | BIGINT | N | FK→MEMBER | 멤버 ID |
| 4 | `BEFORE_RATING` | DOUBLE | N |  | 변경 전 Rating |
| 5 | `AFTER_RATING` | DOUBLE | N |  | 변경 후 Rating |
| 6 | `BEFORE_CONFIDENCE` | DOUBLE | N |  | 변경 전 Confidence |
| 7 | `AFTER_CONFIDENCE` | DOUBLE | N |  | 변경 후 Confidence |
| 8 | `CHANGE_AMOUNT` | DOUBLE | N |  | 변화량 |
| 9 | `CHANGE_REASON` | VARCHAR(30) | N |  | MATCH_RESULT/ADMIN_RECALC |
| 10 | `REFERENCE_TYPE` | VARCHAR(20) | Y |  | 근거 종류(MATCH) |
| 11 | `REFERENCE_ID` | BIGINT | Y |  | 근거 ID(MATCH_ID) |
| 12 | `ALGORITHM_VERSION` | VARCHAR(50) | N |  | 계산 알고리즘 버전 |
| 13 | `CONFIG_VERSION` | INTEGER | N |  | 사용한 설정 버전 |
| 14 | `CALC_DETAIL_JSON` | JSON | Y |  | 계산 상세(Strength, 기대값, K, 배수) |
| 15 | `VOIDED_YN` | BOOL | N |  | 무효 여부(재계산으로 대체됨) |
| 16 | `VOIDED_AT` | DATETIME(3) | Y |  | 무효 처리 일시 |
| 17 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_PLAYER_RATING_HISTORY_CLUB_ID_VOIDED_YN` (CLUB_ID, VOIDED_YN)
- INDEX `IX_PLAYER_RATING_HISTORY_MEMBER_ID_CREATED_AT` (MEMBER_ID, CREATED_AT)
- INDEX `IX_PLAYER_RATING_HISTORY_REF` (REFERENCE_TYPE, REFERENCE_ID)

### MEMBER_STAT_SUMMARY

개인 통계 집계(파생, 언제든 재구성)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MEMBER_ID` | BIGINT | N | PK FK→MEMBER | 멤버 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `GAMES` | INTEGER | N |  | 경기 수 |
| 4 | `WINS` | INTEGER | N |  | 승 |
| 5 | `DRAWS` | INTEGER | N |  | 무 |
| 6 | `LOSSES` | INTEGER | N |  | 패 |
| 7 | `GOALS` | INTEGER | N |  | 골 |
| 8 | `ASSISTS` | INTEGER | N |  | 도움 |
| 9 | `OWN_GOALS` | INTEGER | N |  | 자책골 |
| 10 | `MVP_COUNT` | INTEGER | N |  | 이달의 MVP 수(활성 타이틀 중 COUNTS_AS_MVP_YN = 1) |
| 11 | `TITLE_COUNT` | INTEGER | N |  | 전체 타이틀 수 |
| 12 | `SESSIONS_ATTENDED` | INTEGER | N |  | 출전 일정 수 |
| 13 | `LAST_PLAYED_DATE` | DATE | Y |  | 마지막 출전 날짜 |
| 14 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |

제약/인덱스

- INDEX `IX_MEMBER_STAT_SUMMARY_CLUB_ID` (CLUB_ID)

### MEMBER_PAIR_STAT

두 선수 관계 집계(파생). LOW<HIGH로 순서 중복 방지  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MEMBER_ID_LOW` | BIGINT | N | PK FK→MEMBER | 작은 멤버 ID |
| 2 | `MEMBER_ID_HIGH` | BIGINT | N | PK FK→MEMBER | 큰 멤버 ID |
| 3 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 4 | `CO_ATTENDANCE_COUNT` | INTEGER | N |  | 둘 다 출전한 일정 수(같은 팀이 될 기회) |
| 5 | `SAME_TEAM_COUNT` | INTEGER | N |  | 같은 팀이었던 일정 수 |
| 6 | `CO_ATTENDANCE_SINCE_SAME_TEAM` | INTEGER | N |  | 마지막으로 같은 팀이 된 뒤 함께 출전한 일정 수 |
| 7 | `SAME_TEAM_MATCH_COUNT` | INTEGER | N |  | 같은 편으로 뛴 경기 수 |
| 8 | `SAME_TEAM_WIN_COUNT` | INTEGER | N |  | 같은 편 승리 수 |
| 9 | `SAME_TEAM_DRAW_COUNT` | INTEGER | N |  | 같은 편 무승부 수 |
| 10 | `OPPONENT_MATCH_COUNT` | INTEGER | N |  | 실제 맞대결 경기 수(대기 팀 제외) |
| 11 | `OPPONENT_LOW_WIN_COUNT` | INTEGER | N |  | 맞대결 LOW 승 |
| 12 | `OPPONENT_HIGH_WIN_COUNT` | INTEGER | N |  | 맞대결 HIGH 승 |
| 13 | `LAST_SAME_TEAM_AT` | DATE | Y |  | 마지막 같은 팀 날짜 |
| 14 | `LAST_OPPONENT_AT` | DATE | Y |  | 마지막 맞대결 날짜 |
| 15 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |

제약/인덱스

- INDEX `IX_MEMBER_PAIR_STAT_CLUB_ID` (CLUB_ID)
- INDEX `IX_MEMBER_PAIR_STAT_MEMBER_ID_HIGH` (MEMBER_ID_HIGH)

### TITLE_TYPE

타이틀 정의(이주의 득점왕/도움왕, 이달의 MVP …)  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `TITLE_TYPE_ID` | BIGINT | N | PK | 타이틀 종류 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `TITLE_CODE` | VARCHAR(30) | N |  | 타이틀 코드 |
| 4 | `TITLE_NAME` | VARCHAR(50) | N |  | 타이틀명 |
| 5 | `PERIOD_TYPE` | VARCHAR(10) | N |  | WEEKLY(월~일)/SESSION/MONTHLY(1일~말일) |
| 6 | `AWARD_METHOD` | VARCHAR(10) | N |  | MANUAL(관리자)/AUTO(주간: 일정마감 시, 월간: 월 마감 시 자동 집계) |
| 7 | `AUTO_RULE` | VARCHAR(30) | Y |  | 자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP 전용) |
| 8 | `COUNTS_AS_MVP_YN` | BOOL | N |  | MVP 횟수(MVP_COUNT) 집계 대상 여부. 이달의 MVP = 1 |
| 9 | `ACTIVE_YN` | BOOL | N |  | 사용 여부(false=비활성, 삭제 대신 사용) |
| 10 | `DISPLAY_ORDER` | INTEGER | N |  | 표시 순서 |
| 11 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 12 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- UNIQUE `UQ_TITLE_TYPE_CLUB_ID_TITLE_CODE` (CLUB_ID, TITLE_CODE)

### MEMBER_TITLE

타이틀 수여 이력(이달의 MVP 포함). 비활성 타이틀의 이력은 조회 · 집계에서 제외  
구분: **Source(원본)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `MEMBER_TITLE_ID` | BIGINT | N | PK | 수여 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `TITLE_TYPE_ID` | BIGINT | N | FK→TITLE_TYPE | 타이틀 종류 |
| 4 | `MEMBER_ID` | BIGINT | N | FK→MEMBER | 멤버 ID |
| 5 | `PERIOD_START` | DATE | N |  | 기간 시작 |
| 6 | `PERIOD_END` | DATE | N |  | 기간 끝 |
| 7 | `SESSION_ID` | BIGINT | Y | FK→SESSION | 일정 ID |
| 8 | `AWARD_METHOD` | VARCHAR(10) | N |  | MANUAL/AUTO |
| 9 | `FACTS_JSON` | JSON | Y |  | 자동 집계 근거(지표, 값, 공동 여부) |
| 10 | `NOTE` | VARCHAR(200) | Y |  | 메모 |
| 11 | `CANCELLED_YN` | BOOL | N |  | 취소 여부 |
| 12 | `CANCELLED_AT` | DATETIME(3) | Y |  | 취소 일시 |
| 13 | `ADMIN_ID` | BIGINT | Y | FK→CLUB_ADMIN | 처리 관리자 ID |
| 14 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_MEMBER_TITLE_CLUB_ID_PERIOD_START` (CLUB_ID, PERIOD_START)
- INDEX `IX_MEMBER_TITLE_MEMBER_ID` (MEMBER_ID)
- INDEX `IX_MEMBER_TITLE_TITLE_TYPE_ID_PERIOD_START` (TITLE_TYPE_ID, PERIOD_START)

## 5. The Wire

### INSIGHT_TYPE_CONFIG

Insight 종류별 사용 여부/중요도 범위/태그(전역)  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `INSIGHT_TYPE` | VARCHAR(40) | N | PK | Insight 종류 |
| 2 | `CATEGORY` | VARCHAR(30) | N |  | 분류(PLAYER/STREAK/MILESTONE/PAIR/MATCH/TITLE) |
| 3 | `ENABLED_YN` | BOOL | N |  | 사용 여부 |
| 4 | `BASE_IMPORTANCE` | INTEGER | N |  | 기본 중요도 |
| 5 | `MIN_IMPORTANCE` | INTEGER | N |  | 최소 중요도 |
| 6 | `MAX_IMPORTANCE` | INTEGER | N |  | 최대 중요도 |
| 7 | `PRE_MATCH_YN` | BOOL | N |  | 일정확정(프리뷰) 대상 |
| 8 | `POST_MATCH_YN` | BOOL | N |  | 일정마감(리캡) 대상 |
| 9 | `TAG_NAME` | VARCHAR(30) | Y |  | 기사 태그(Canonical) |
| 10 | `RULE_VERSION` | VARCHAR(40) | N |  | 판정 규칙 버전 |
| 11 | `DESCRIPTION` | VARCHAR(300) | Y |  | 설명 |
| 12 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 13 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

### INSIGHT_CONFIG_PARAM

Insight 종류별 판정 파라미터  
구분: **Config/Reference**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `INSIGHT_TYPE` | VARCHAR(40) | N | PK FK→INSIGHT_TYPE_CONFIG | Insight 종류 |
| 2 | `PARAM_KEY` | VARCHAR(50) | N | PK | 파라미터 키 |
| 3 | `PARAM_VALUE` | VARCHAR(200) | N |  | 파라미터 값 |
| 4 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |

### INSIGHT

Backend가 계산한 구조화된 사건(AI 문장 아님)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `INSIGHT_ID` | BIGINT | N | PK | Insight ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `SESSION_ID` | BIGINT | Y | FK→SESSION | 일정 ID |
| 4 | `MATCH_ID` | BIGINT | Y | FK→MATCH_GAME | 경기 ID |
| 5 | `MEMBER_ID` | BIGINT | Y | FK→MEMBER | 대표 멤버 |
| 6 | `INSIGHT_TYPE` | VARCHAR(40) | N | FK→INSIGHT_TYPE_CONFIG | Insight 종류 |
| 7 | `CATEGORY` | VARCHAR(30) | N |  | 분류 |
| 8 | `PHASE` | VARCHAR(10) | N |  | PRE(일정확정)/POST(일정마감) |
| 9 | `IMPORTANCE` | INTEGER | N |  | 최종 중요도(0~100, 신호 크기에 따라 가변) |
| 10 | `FACTS_JSON` | JSON | N |  | 사실 데이터(내부 점수 미포함) |
| 11 | `RULE_VERSION` | VARCHAR(40) | N |  | 판정 규칙 버전 |
| 12 | `ACTIVE_YN` | BOOL | N |  | 유효 여부(재생성 시 false, 기사 근거 보존) |
| 13 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_INSIGHT_CLUB_ID_CREATED_AT` (CLUB_ID, CREATED_AT)
- INDEX `IX_INSIGHT_SESSION_ID_INSIGHT_TYPE` (SESSION_ID, INSIGHT_TYPE)

### INSIGHT_MEMBER

Insight 등장 멤버(다인 Insight/멤버별 기사 조회)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `INSIGHT_ID` | BIGINT | N | PK FK→INSIGHT | Insight ID |
| 2 | `MEMBER_ID` | BIGINT | N | PK FK→MEMBER | 멤버 ID |
| 3 | `ROLE` | VARCHAR(20) | N |  | SUBJECT/PARTNER/ASSIST/TEAM |

제약/인덱스

- INDEX `IX_INSIGHT_MEMBER_MEMBER_ID` (MEMBER_ID)

### AI_ARTICLE

AI 기사(재생성은 새 행, 기존 보존)  
구분: **Derived(이력 보존)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `ARTICLE_ID` | BIGINT | N | PK | 기사 ID |
| 2 | `CLUB_ID` | BIGINT | N | FK→CLUB | 클럽 ID |
| 3 | `SESSION_ID` | BIGINT | Y | FK→SESSION | 일정 ID |
| 4 | `MATCH_ID` | BIGINT | Y | FK→MATCH_GAME | 경기 ID |
| 5 | `ARTICLE_TYPE` | VARCHAR(20) | N |  | PRE_MATCH/SESSION_RECAP/MONTHLY_MVP(POST_MATCH 예약) |
| 6 | `TITLE` | VARCHAR(200) | Y |  | 제목 |
| 7 | `SUMMARY` | VARCHAR(500) | Y |  | 요약 |
| 8 | `CONTENT` | TEXT | Y |  | 본문 |
| 9 | `MODEL_NAME` | VARCHAR(100) | N |  | 사용 모델(stub=개발용) |
| 10 | `PROMPT_VERSION` | VARCHAR(40) | N |  | 프롬프트 버전 |
| 11 | `INSIGHT_RULE_VERSION` | VARCHAR(1000) | Y |  | 사용 Insight 규칙 버전 목록 |
| 12 | `STATUS` | VARCHAR(20) | N |  | PENDING/GENERATED/PUBLISHED/REJECTED/FAILED/SUPERSEDED |
| 13 | `PUBLISHED_YN` | BOOL | N |  | 게시 여부 |
| 14 | `PUBLISHED_AT` | DATETIME(3) | Y |  | 게시 일시 |
| 15 | `PARENT_ARTICLE_ID` | BIGINT | Y | FK→AI_ARTICLE | 최초 기사 ID(재생성 계보) |
| 16 | `GENERATION_NO` | INTEGER | N |  | 생성 차수 |
| 17 | `REQUEST_JSON` | JSON | Y |  | AI 입력 DTO(사실 근거) |
| 18 | `RESPONSE_JSON` | JSON | Y |  | AI 응답 원문(JSON) |
| 19 | `ERROR_MESSAGE` | TEXT | Y |  | 실패 사유 |
| 20 | `UPDATED_AT` | DATETIME(3) | N |  | 수정 일시(UTC) |
| 21 | `CREATED_AT` | DATETIME(3) | N |  | 생성 일시(UTC) |

제약/인덱스

- INDEX `IX_AI_ARTICLE_CLUB_ID_CREATED_AT` (CLUB_ID, CREATED_AT)
- INDEX `IX_AI_ARTICLE_CLUB_ID_PUBLISHED_YN_PUBLISHED_AT` (CLUB_ID, PUBLISHED_YN, PUBLISHED_AT)
- INDEX `IX_AI_ARTICLE_SESSION_ID` (SESSION_ID)

### AI_ARTICLE_INSIGHT

기사가 실제 사용한 Insight(AI usedInsightIds)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `ARTICLE_ID` | BIGINT | N | PK FK→AI_ARTICLE | 기사 ID |
| 2 | `INSIGHT_ID` | BIGINT | N | PK FK→INSIGHT | Insight ID |

### ARTICLE_TAG

기사 태그(Insight Type → Canonical Tag 매핑)  
구분: **Derived(재계산 가능)**

| No | 컬럼 | 타입 | NULL | 키 | 설명 |
|---:|---|---|:---:|---|---|
| 1 | `ARTICLE_ID` | BIGINT | N | PK FK→AI_ARTICLE | 기사 ID |
| 2 | `TAG_NAME` | VARCHAR(30) | N | PK | 태그 |

제약/인덱스

- INDEX `IX_ARTICLE_TAG_TAG_NAME` (TAG_NAME)
