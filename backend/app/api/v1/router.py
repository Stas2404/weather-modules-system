from fastapi import APIRouter
from app.api.v1 import auth, diagnostics, modules, profiles, sessions, telemetry, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(modules.router)
api_router.include_router(profiles.router)
api_router.include_router(sessions.router)
api_router.include_router(telemetry.router)
api_router.include_router(diagnostics.router)