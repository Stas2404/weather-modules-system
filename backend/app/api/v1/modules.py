from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_current_user, log_audit
from app.core.security import generate_iot_api_key
from app.db.session import get_db
from app.models.domain import IoTApiKey, Module, ModulePassport, User
from app.schemas.dto import (
    ApiKeyCreatedOut, ApiKeyOut, ModuleCreate, ModuleOut, PassportOut, PassportUpsert
)

router = APIRouter(prefix="/modules", tags=["Вимірювальні модулі та паспорти"])


@router.post("", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
async def create_module(
    data: ModuleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(select(Module).where(Module.serial_number == data.serial_number))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Модуль із таким серійним номером вже зареєстровано.")

    module = Module(serial_number=data.serial_number, name=data.name, status=data.status)
    db.add(module)
    await db.flush()

    if data.passport:
        passport = ModulePassport(module_id=module.id, **data.passport.model_dump())
        db.add(passport)

    await db.commit()
    stmt = select(Module).options(selectinload(Module.passport)).where(Module.id == module.id)
    return (await db.execute(stmt)).scalar_one()


@router.get("", response_model=list[ModuleOut])
async def list_modules(
    status_filter: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Module).options(selectinload(Module.passport)).order_by(Module.id)
    if status_filter:
        stmt = stmt.where(Module.status == status_filter)
    return (await db.execute(stmt)).scalars().all()


@router.get("/{module_id}", response_model=ModuleOut)
async def get_module(
    module_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    stmt = select(Module).options(selectinload(Module.passport)).where(Module.id == module_id)
    module = (await db.execute(stmt)).scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Вимірювальний модуль не знайдено.")
    return module


@router.put("/{module_id}/passport", response_model=PassportOut)
async def upsert_passport(
    module_id: int,
    data: PassportUpsert,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Вимірювальний модуль не знайдено.")

    stmt = select(ModulePassport).where(ModulePassport.module_id == module_id)
    passport = (await db.execute(stmt)).scalar_one_or_none()
    if passport:
        for k, v in data.model_dump().items():
            setattr(passport, k, v)
    else:
        passport = ModulePassport(module_id=module_id, **data.model_dump())
        db.add(passport)

    await db.commit()
    await db.refresh(passport)
    return passport


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: int, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Вимірювальний модуль не знайдено.")
    await db.delete(module)
    await db.commit()


@router.post("/{module_id}/api-keys", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_module_api_key(
    module_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Вимірювальний модуль не знайдено.")

    raw_key, prefix, key_hash = generate_iot_api_key()
    key_obj = IoTApiKey(module_id=module_id, key_prefix=prefix, key_hash=key_hash)
    db.add(key_obj)
    await db.commit()
    await db.refresh(key_obj)
    await log_audit(db, "API_KEY_CREATED", True, user_id=admin.id, entity_type="module", entity_id=str(module_id))

    return ApiKeyCreatedOut(
        id=key_obj.id,
        module_id=module_id,
        key_prefix=prefix,
        raw_api_key=raw_key,
        created_at=key_obj.created_at,
    )


@router.get("/{module_id}/api-keys", response_model=list[ApiKeyOut])
async def list_module_api_keys(
    module_id: int, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    stmt = select(IoTApiKey).where(IoTApiKey.module_id == module_id).order_by(IoTApiKey.id.desc())
    return (await db.execute(stmt)).scalars().all()


@router.delete("/{module_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_module_api_key(
    module_id: int,
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    key_obj = await db.get(IoTApiKey, key_id)
    if not key_obj or key_obj.module_id != module_id:
        raise HTTPException(status_code=404, detail="API-ключ не знайдено.")
    key_obj.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await log_audit(db, "API_KEY_REVOKED", True, user_id=admin.id, entity_type="api_key", entity_id=str(key_id))