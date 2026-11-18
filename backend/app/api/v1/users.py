from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, log_audit
from app.core.security import hash_password
from app.db.session import get_db
from app.models.domain import User
from app.schemas.dto import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Користувачі (Адміністрування)"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    exists = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Користувач із таким email вже існує.")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await log_audit(db, "USER_CREATED", True, user_id=admin.id, entity_type="user", entity_id=str(user.id))
    return user


@router.get("", response_model=list[UserOut])
async def list_users(_: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(User).order_by(User.id))).scalars().all()


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено.")
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await db.commit()
    await db.refresh(user)
    await log_audit(db, "USER_UPDATED", True, user_id=admin.id, entity_type="user", entity_id=str(user.id))
    return user