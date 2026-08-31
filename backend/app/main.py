import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

# ── Serve the built Angular SPA when it is packaged with the backend ─────
# The Docker image copies the production bundle to /app/static; when this
# process is a local `uvicorn --reload` from backend/ without any build
# beside it, the directory is absent and the block is a no-op — the API
# stays reachable and the Angular dev server is unaffected.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if _STATIC_DIR.is_dir():

    @app.get("/{spa_path:path}", include_in_schema=False)
    def _serve_spa(spa_path: str) -> FileResponse:
        # /api/... and /health are registered above and win by order.
        # The catch-all would otherwise turn a missed API call into an HTML
        # page instead of the JSON error CONVENTIONS.md promises the client.
        if spa_path.startswith("api/") or spa_path == "health":
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = _STATIC_DIR / spa_path
        if candidate.is_file():
            return FileResponse(candidate)
        # SPA fallback: hand index.html to the Angular router for any
        # deep link the user refreshes on (/wardrobe, /trip/42, …).
        return FileResponse(_STATIC_DIR / "index.html")

