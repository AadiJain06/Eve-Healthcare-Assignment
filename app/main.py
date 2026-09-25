"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import Base, engine
from app.logging_config import configure_logging
from app.routers import auth, bookings, centres, payments

configure_logging()
logger = logging.getLogger("eve")


def create_app() -> FastAPI:
    # Create tables on startup. In production this would be Alembic migrations.
    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Backend service for diagnostic test bookings and simulated "
            "payments. Interactive docs at /docs."
        ),
    )

    app.include_router(auth.router)
    app.include_router(centres.router)
    app.include_router(bookings.router)
    app.include_router(payments.router)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    return app


app = create_app()
