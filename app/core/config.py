"""애플리케이션(프로세스) 레벨 설정.

- 운영 중 관리자가 바꾸는 값(Rating K, 경기 시간 등)은 DB의 SYSTEM_CONFIG(클럽별)에 둔다.
- 여기에는 배포 환경마다 달라지는 값(DB 접속, 비밀키, OpenAI Key, 모델명)만 둔다.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Clubwire"
    DATABASE_URL: str = "mysql+pymysql://clubwire:clubwire@localhost:3306/clubwire?charset=utf8mb4"
    SQL_ECHO: bool = False

    # 관리자 토큰
    SECRET_KEY: str = "change-me-in-production"
    ADMIN_TOKEN_TTL_MIN: int = 720
    ADMIN_LOGIN_MAX_FAIL: int = 5
    ADMIN_LOGIN_LOCK_SEC: int = 300

    # OpenAI (키는 서버 환경변수로만 주입한다. 브라우저/레포 금지)
    OPENAI_API_KEY: str | None = None
    AI_PROVIDER: str = "auto"  # auto | openai | template(=stub)  (auto: 키가 있으면 openai, 없으면 기본형 기사)
    AI_ARTICLE_MODEL: str = "gpt-4.1-mini"
    AI_RECAP_MODEL: str = "gpt-4.1-mini"
    AI_TIMEOUT_SEC: float = 60.0
    AI_MAX_RETRY: int = 1

    # 백그라운드
    ENABLE_BACKGROUND_JOBS: bool = True  # LIVE 타이머 자동 종료 + 이달의 MVP 월 마감 감시 루프
    TIMER_TICK_SEC: float = 1.0
    MONTHLY_CHECK_SEC: float = 600.0  # 이달의 MVP 월 마감 확인 주기(초). 서버 시작 때 한 번 바로 확인
    ARTICLE_GENERATION_SYNC: bool = False  # True면 요청 안에서 기사를 바로 생성(테스트용)

    CORS_ORIGINS: str = "*"

    # React 빌드 결과(frontend/dist)가 있으면 같은 서버에서 정적 파일로 서빙(배포 단순화)
    FRONTEND_DIST: str | None = "frontend/dist"

    @property
    def ai_provider_resolved(self) -> str:
        if self.AI_PROVIDER == "auto":
            return "openai" if self.OPENAI_API_KEY else "template"
        return "template" if self.AI_PROVIDER == "stub" else self.AI_PROVIDER


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
