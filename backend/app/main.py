import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import APP_VERSION, settings
from app.core.deps import get_db
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.schemas.health import HealthResponse

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="Bijoux API", version=APP_VERSION)

register_error_handlers(app)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Health check could not reach the database", extra={"error": str(exc)})
        return HealthResponse(status="ok", db="error", version=APP_VERSION)

    return HealthResponse(status="ok", db="ok", version=APP_VERSION)
