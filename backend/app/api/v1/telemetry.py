import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_iot_module, get_current_user
from app.db.session import get_db
from app.models.domain import Module, TelemetryRecord, TestSession, User
from app.schemas.dto import TelemetryBatchIn, TelemetryIngestResponse, TelemetryOut
from app.services.telemetry_service import process_telemetry_batch

router = APIRouter(tags=["Телеметрія"])


@router.post("/telemetry", response_model=TelemetryIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_telemetry(
    batch: TelemetryBatchIn,
    module: Module = Depends(get_current_iot_module),
    db: AsyncSession = Depends(get_db),
):
    session_id, accepted, skipped, anomalies = await process_telemetry_batch(db, module, batch.packets)
    return TelemetryIngestResponse(
        session_id=session_id,
        accepted_count=accepted,
        duplicates_skipped=skipped,
        anomalies_detected=anomalies,
    )


@router.get("/sessions/{session_id}/telemetry", response_model=list[TelemetryOut])
async def get_session_telemetry(
    session_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(TestSession, session_id):
        raise HTTPException(status_code=404, detail="Серію випробувань не знайдено.")
    stmt = (
        select(TelemetryRecord)
        .where(TelemetryRecord.session_id == session_id)
        .order_by(TelemetryRecord.recorded_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/sessions/{session_id}/telemetry/export")
async def export_session_telemetry(
    session_id: int,
    export_format: str = Query(default="csv", alias="format", pattern="^(csv|json)$"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(TestSession, session_id):
        raise HTTPException(status_code=404, detail="Серію випробувань не знайдено.")

    stmt = (
        select(TelemetryRecord)
        .where(TelemetryRecord.session_id == session_id)
        .order_by(TelemetryRecord.recorded_at.asc())
    )
    records = (await db.execute(stmt)).scalars().all()

    if export_format == "json":
        return [TelemetryOut.model_validate(r) for r in records]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "packet_id", "recorded_at", "received_at", "temperature", "humidity", "pressure_hpa", "is_valid"])
    for r in records:
        writer.writerow([r.id, r.packet_id, r.recorded_at.isoformat(), r.received_at.isoformat(), r.temperature, r.humidity, r.pressure_hpa, r.is_valid])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=session_{session_id}_telemetry.csv"},
    )