from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import APP_VERSION, settings
from app.core.logging import configure_logging
from app.schemas.health import HealthResponse

configure_logging()

app = FastAPI(title="Bijoux API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db="unknown", version=APP_VERSION)
