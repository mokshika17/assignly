from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import get_settings
from app.routers import auth, projects, tasks, pages
from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.limiter import limiter
from app.logger import setup_logging, get_logger
import uuid
from starlette.middleware.base import BaseHTTPMiddleware


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

# Pages router last — catches all UI routes
app.include_router(pages.router)

@app.on_event("startup")
async def on_startup():
    logger.info("app_started", name=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG)

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

from sqlalchemy import text
from app.database import engine
from app.cache import get_redis

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

    # Check Redis
    try:
        get_redis().ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"

    status["status"] = "ok" if status["db"] == "ok" and status["redis"] == "ok" else "degraded"
    return status