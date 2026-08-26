from fastapi import APIRouter

from app.api.v1.routes import auth, items, me, weather

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(items.router)
api_router.include_router(me.router)
api_router.include_router(weather.router)
