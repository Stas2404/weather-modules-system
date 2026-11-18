from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.domain import AuditLog, IoTApiKey, Module, User

bearer_scheme = HTTPBearer(auto_error=False)


async def log_audit(
    db: AsyncSession,
    action: str,
    success: bool,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip_address: str | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        success=success,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        ip_address=ip_address,
        details=details,
    )
    db.add(entry)
    await db.commit()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не надано токен автентифікації (Bearer token).",
        )
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недійсний або прострочений токен доступу.",
        )

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Обліковий запис користувача не знайдено або заблоковано.",
        )
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ заборонено: потрібні права адміністратора.",
        )
    return current_user


async def get_current_iot_module(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Module:
    client_ip = request.client.host if request.client else None
    if not x_api_key:
        await log_audit(
            db, "IOT_AUTH_FAILED", False, ip_address=client_ip, details={"reason": "Missing X-API-Key"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Відсутній заголовок X-API-Key для IoT-пристрою.",
        )

    key_hash = hash_api_key(x_api_key)
    stmt = select(IoTApiKey).where(
        IoTApiKey.key_hash == key_hash, IoTApiKey.revoked_at.is_(None)
    )
    result = await db.execute(stmt)
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj:
        await log_audit(
            db,
            "IOT_AUTH_FAILED",
            False,
            ip_address=client_ip,
            details={"key_prefix": x_api_key[:12], "reason": "Invalid or revoked API key"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недійсний або відкликаний API-ключ вимірювального модуля.",
        )

    module = await db.get(Module, api_key_obj.module_id)
    if not module or module.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вимірювальний модуль неактивний або перебуває на техобслуговуванні.",
        )
    return module