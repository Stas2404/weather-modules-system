from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.domain import ObservationProfile, TestConditionType, User
from app.schemas.dto import ConditionTypeCreate, ConditionTypeOut, ProfileCreate, ProfileOut

router = APIRouter(tags=["Типи умов та профілі спостереження"])


@router.post("/condition-types", response_model=ConditionTypeOut, status_code=status.HTTP_201_CREATED)
async def create_condition_type(
    data: ConditionTypeCreate, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    obj = TestConditionType(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/condition-types", response_model=list[ConditionTypeOut])
async def list_condition_types(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(TestConditionType).order_by(TestConditionType.id))).scalars().all()


@router.put("/condition-types/{type_id}", response_model=ConditionTypeOut)
async def update_condition_type(
    type_id: int,
    data: ConditionTypeCreate,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(TestConditionType, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Тип умов випробувань не знайдено.")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/condition-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_condition_type(
    type_id: int, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    obj = await db.get(TestConditionType, type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Тип умов випробувань не знайдено.")
    await db.delete(obj)
    await db.commit()


@router.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreate, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    cond = await db.get(TestConditionType, data.condition_type_id)
    if not cond:
        raise HTTPException(status_code=404, detail="Вказаний тип умов випробувань не існує.")
    obj = ObservationProfile(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(ObservationProfile).order_by(ObservationProfile.id))).scalars().all()


@router.put("/profiles/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int,
    data: ProfileCreate,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ObservationProfile, profile_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Профіль спостереження не знайдено.")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    obj = await db.get(ObservationProfile, profile_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Профіль спостереження не знайдено.")
    await db.delete(obj)
    await db.commit()