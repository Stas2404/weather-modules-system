from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.domain import AIDiagnosticReport, Anomaly, AuditLog, TestSession, User
from app.schemas.dto import AnomalyOut, AuditLogOut, DiagnosticReportOut, DiagnosticRequest
from app.services.llm_service import generate_diagnostic_report

router = APIRouter(tags=["Аномалії, AI-діагностика та Аудит"])


@router.get("/sessions/{session_id}/anomalies", response_model=list[AnomalyOut])
async def list_session_anomalies(
    session_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if not await db.get(TestSession, session_id):
        raise HTTPException(status_code=404, detail="Серію випробувань не знайдено.")
    stmt = select(Anomaly).where(Anomaly.session_id == session_id).order_by(Anomaly.id.asc())
    return (await db.execute(stmt)).scalars().all()


@router.post("/sessions/{session_id}/diagnostics", response_model=DiagnosticReportOut, status_code=status.HTTP_201_CREATED)
async def request_ai_diagnostic(
    session_id: int,
    data: DiagnosticRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_diagnostic_report(db, session_id, user.id, data.anomaly_id)


@router.get("/sessions/{session_id}/diagnostics", response_model=list[DiagnosticReportOut])
async def list_ai_diagnostics(
    session_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(AIDiagnosticReport)
        .where(AIDiagnosticReport.session_id == session_id)
        .order_by(AIDiagnosticReport.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    limit: int = 100, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    return (await db.execute(stmt)).scalars().all()