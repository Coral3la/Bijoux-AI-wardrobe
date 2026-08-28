import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from app.core.request_id import HEADER_NAME, RequestIdMiddleware
from app.schemas.health import HealthResponse
from app.services.tagging import run_startup_sweep

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # A BackgroundTask dies with its process, so a row still tagging when
    # this one starts belongs to nobody. run_startup_sweep decides which
    # are old enough to say so about, and never raises.
    run_startup_sweep()
    yield


app = FastAPI(title="Bijoux API", version=APP_VERSION, lifespan=lifespan)
register_error_handlers(app)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    # `allow_headers` governs what a browser may *send*. Reading a response
    # header back is a separate permission, and without this one the frontend
    # is served the id and cannot see it — the failure would be silent, because
    # the header is on the wire either way and only the browser withholds it.
    expose_headers=[HEADER_NAME],
)

# After CORS, therefore outside it: `add_middleware` makes the last one added
# the outermost, and the id is stamped on the way out regardless of what CORS
# put on the response. `Access-Control-Expose-Headers` is a fixed string, so it
# does not care that `X-Request-ID` is set after it.
app.add_middleware(RequestIdMiddleware)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Health check could not reach the database", extra={"error": str(exc)})
        return HealthResponse(status="ok", db="error", version=APP_VERSION)

    return HealthResponse(status="ok", db="ok", version=APP_VERSION)
