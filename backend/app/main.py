from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, Base, engine
from app.models.domain import User


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Створюємо таблиці при старті (якщо міграції ще не застосовані) та початкового адміна
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.email == settings.FIRST_ADMIN_EMAIL)
        admin = (await db.execute(stmt)).scalar_one_or_none()
        if not admin:
            db.add(
                User(
                    email=settings.FIRST_ADMIN_EMAIL,
                    password_hash=hash_password(settings.FIRST_ADMIN_PASSWORD),
                    full_name="Системний Адміністратор",
                    role="admin",
                )
            )
            await db.commit()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="RESTful Web API для обліку впливу погодних умов на переносні вимірювальні модулі.",
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Система"])
async def health_check():
    return {"status": "ok"}