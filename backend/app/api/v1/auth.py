from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, log_audit
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.domain import User
from app.schemas.dto import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Автентифікація"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else None
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        await log_audit(db, "USER_LOGIN", False, ip_address=ip, details={"email": data.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірний email або пароль.",
        )

    if not user.is_active:
        await log_audit(db, "USER_LOGIN", False, user_id=user.id, ip_address=ip, details={"reason": "inactive"})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Обліковий запис заблоковано.")

    token = create_access_token(subject=user.id, role=user.role)
    await log_audit(db, "USER_LOGIN", True, user_id=user.id, ip_address=ip)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user