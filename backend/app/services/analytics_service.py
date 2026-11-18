from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Anomaly, TelemetryRecord, TestSession


async def get_session_metrics(db: AsyncSession, session_id: int) -> dict:
    session = await db.get(TestSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Серію випробувань з ID={session_id} не знайдено.",
        )

    agg_stmt = select(
        func.count(TelemetryRecord.id).label("cnt"),
        func.min(TelemetryRecord.temperature).label("min_t"),
        func.max(TelemetryRecord.temperature).label("max_t"),
        func.avg(TelemetryRecord.temperature).label("avg_t"),
        func.min(TelemetryRecord.humidity).label("min_h"),
        func.max(TelemetryRecord.humidity).label("max_h"),
        func.avg(TelemetryRecord.humidity).label("avg_h"),
        func.min(TelemetryRecord.pressure_hpa).label("min_p"),
        func.max(TelemetryRecord.pressure_hpa).label("max_p"),
        func.avg(TelemetryRecord.pressure_hpa).label("avg_p"),
    ).where(TelemetryRecord.session_id == session_id)

    row = (await db.execute(agg_stmt)).one()

    anom_stmt = select(func.count(Anomaly.id)).where(Anomaly.session_id == session_id)
    anomalies_count = (await db.execute(anom_stmt)).scalar_one()

    def _r(val):
        return round(float(val), 2) if val is not None else None

    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "records_count": row.cnt,
        "temperature": {"min": _r(row.min_t), "max": _r(row.max_t), "avg": _r(row.avg_t)},
        "humidity": {"min": _r(row.min_h), "max": _r(row.max_h), "avg": _r(row.avg_h)},
        "pressure_hpa": {"min": _r(row.min_p), "max": _r(row.max_p), "avg": _r(row.avg_p)},
        "anomalies_count": anomalies_count,
    }


async def compare_two_sessions(db: AsyncSession, session_a_id: int, session_b_id: int) -> dict:
    a = await get_session_metrics(db, session_a_id)
    b = await get_session_metrics(db, session_b_id)

    def _diff(val_a, val_b):
        if val_a is None or val_b is None:
            return None
        return round(val_b - val_a, 2)

    return {
        "session_a": a,
        "session_b": b,
        "delta": {
            "avg_temp_diff": _diff(a["temperature"]["avg"], b["temperature"]["avg"]),
            "avg_humidity_diff": _diff(a["humidity"]["avg"], b["humidity"]["avg"]),
            "avg_pressure_diff": _diff(a["pressure_hpa"]["avg"], b["pressure_hpa"]["avg"]),
            "anomalies_diff": b["anomalies_count"] - a["anomalies_count"],
        },
    }