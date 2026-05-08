from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging
import uuid

from app.config import get_settings
from app.routers import auth, projects, tasks, pages
from app.limiter import limiter
from app.logger import setup_logging, get_logger
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from app.routers import analytics
from app.database import engine, SessionLocal
from app.cache import get_redis
from app.dependencies import require_admin
from app.models import User
from app.routers import analytics


logger = logging.getLogger(__name__)
settings = get_settings()
setup_logging(debug=settings.DEBUG)
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Request ID Middleware
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIDMiddleware)

# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
            "path": request.url.path,
        },
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "The requested resource does not exist.",
            "path": request.url.path,
        },
    )

# ---------------------------------------------------------------------------
# Static + Templates
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Routers
# API routers are prefixed with /api to avoid conflicts with page routes
# ---------------------------------------------------------------------------

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(analytics.router)

# Pages router last — catches all UI routes
app.include_router(pages.router)

@app.on_event("startup")
async def on_startup():
    logger.info("app_started", name=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG)
    # Seed the default admin user on every startup (idempotent — skips if already present).
    try:
        from scripts.seed_admin import seed_admin
        db = SessionLocal()
        try:
            seed_admin(db)
        finally:
            db.close()
    except Exception as exc:
        logger.error("seed_admin_failed", error=str(exc), exc_info=True)

# ---------------------------------------------------------------------------
# Admin Seed Endpoint
# ---------------------------------------------------------------------------

@app.post("/admin/seed", tags=["Admin"], summary="Bootstrap the default admin user")
def admin_seed(current_user: User = Depends(require_admin)):
    """
    Idempotent endpoint that creates the default admin user (admin@assignly.com).
    Requires an existing admin JWT — intended for use after the first manual seed
    or in environments where the startup seed is unavailable.
    """
    from scripts.seed_admin import seed_admin
    db = SessionLocal()
    try:
        created = seed_admin(db)
    finally:
        db.close()
    if created:
        return {"status": "created", "email": "admin@assignly.com"}
    return {"status": "already_exists", "email": "admin@assignly.com"}

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health():
    status = {"app": settings.APP_NAME, "version": settings.APP_VERSION}

    # Check DB
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception as e:
        status["db"] = f"error: {str(e)}"

    status["status"] = "ok" if status["db"] == "ok" else "degraded"
    return status