import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import auth
import processing
import analytics
import models
from config import settings
from database import engine

# Structured logging
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {
        "level": "DEBUG" if settings.DEBUG else "INFO",
        "handlers": ["console"],
    },
}
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist (Alembic handles migrations in production)
    models.Base.metadata.create_all(bind=engine)
    logger.info("UPI Tracker API started")
    yield
    logger.info("UPI Tracker API shutting down")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="UPI Tracker API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(processing.router)
app.include_router(analytics.router)


@app.get("/")
def root():
    return {"message": "UPI Tracker API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    """Liveness probe for load balancers and monitoring."""
    from cache import get_redis
    redis_ok = False
    try:
        client = get_redis()
        redis_ok = client is not None and client.ping()
    except Exception:
        pass

    db_ok = False
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "db": "ok" if db_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
