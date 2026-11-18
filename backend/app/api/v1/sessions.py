from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.domain import Module, ObservationProfile, TestSession, User
from app.schemas.dto import SessionCreate, SessionOut
from app.services.analytics_service import compare_two_sessions, get_session_metrics

router = APIRouter(prefix="/sessions", tags=["Серії випробувань та аналітика"])


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Module, data.module_id):
        raise HTTPException(status_code=404, detail="Вимірювальний модуль не знайдено.")
    if not await db.get(ObservationProfile, data.profile_id):
        raise HTTPException(status_code=404, detail="Профіль спостереження не знайдено.")

    session = TestSession(
        module_id=data.module_id,
        profile_id=data.profile_id,
        operator_id=user.id,
        title=data.title,
        location=data.location,
        status="active",
    )
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Для цього модуля вже існує активна серія випробувань. Завершіть її перед початком нової.",
        )
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    module_id: int | None = None,
    status_filter: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TestSession).order_by(TestSession.id.desc())
    if module_id is not None:
        stmt = stmt.where(TestSession.module_id == module_id)
    if status_filter:
        stmt = stmt.where(TestSession.status == status_filter)
    return (await db.execute(stmt)).scalars().all()


@router.get("/compare")
async def compare_sessions(
    session_a: int = Query(..., description="ID першої серії випробувань"),
    session_b: int = Query(..., description="ID другої серії випробувань"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await compare_two_sessions(db, session_a, session_b)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    session = await db.get(TestSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Серію випробувань не знайдено.")
    return session


@router.post("/{session_id}/complete", response_model=SessionOut)
async def complete_session(
    session_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    session = await db.get(TestSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Серію випробувань не знайдено.")
    if session.status != "active":
        raise HTTPException(status_code=400, detail="Серія випробувань уже завершена або скасована.")
    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}/summary")
async def session_summary(
    session_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await get_session_metrics(db, session_id)