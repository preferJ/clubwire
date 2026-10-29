import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import appearance, clubs, matches, members, sessions, stats, superadmin_auth, superadmin_teams, titles, wire, ws
from app.core.config import settings
from app.core.errors import DomainError
from app.core.ws import hub
from app.jobs.monthly import monthly_loop
from app.jobs.timer import timer_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SECRET_KEY == "change-me-in-production" or len(settings.SECRET_KEY) < 32:
        logging.getLogger("clubwire").warning("SECRET_KEY를 32자 이상의 임의 값으로 설정하세요(.env).")
    hub.bind_loop(asyncio.get_running_loop())
    tasks = [asyncio.create_task(timer_loop()), asyncio.create_task(monthly_loop())] if settings.ENABLE_BACKGROUND_JOBS else []
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Clubwire API",
    version="0.1.0",
    description="아마추어 스포츠팀 운영 + The Wire. 조회는 공개, 쓰기는 관리자 모드(PIN → Bearer 토큰).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "요청 값이 올바르지 않습니다.",
                                                            "details": exc.errors()}})


CLUB_PREFIX = "/api/clubs/{club_slug}"  # 클럽(tenant)은 URL로 구분
for r in (clubs.router, appearance.router, members.router, sessions.router, matches.router, stats.router, titles.router, wire.router):
    app.include_router(r, prefix=CLUB_PREFIX)
app.include_router(ws.router)
app.include_router(superadmin_auth.router)
app.include_router(superadmin_teams.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- React 빌드 서빙(SPA)
_dist = Path(settings.FRONTEND_DIST).resolve() if settings.FRONTEND_DIST else None
if _dist and (_dist / "index.html").is_file():
    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404)
        target = (_dist / full_path).resolve()
        if full_path and target.is_file() and _dist in target.parents:
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
