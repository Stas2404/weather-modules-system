import asyncio
import json
from fastapi import HTTPException, status
from google import genai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.domain import AIDiagnosticReport, Anomaly, Module, TestSession


async def generate_diagnostic_report(
    db: AsyncSession, session_id: int, user_id: int, anomaly_id: int | None = None
) -> AIDiagnosticReport:
    session = await db.get(TestSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Серію випробувань з ID={session_id} не знайдено.",
        )

    mod_stmt = (
        select(Module)
        .options(selectinload(Module.passport))
        .where(Module.id == session.module_id)
    )
    module = (await db.execute(mod_stmt)).scalar_one()

    anom_stmt = select(Anomaly).where(Anomaly.session_id == session_id)
    if anomaly_id is not None:
        anom_stmt = anom_stmt.where(Anomaly.id == anomaly_id)
    anomalies = (await db.execute(anom_stmt)).scalars().all()

    if not anomalies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для формування AI-висновку потрібна хоча б одна зафіксована аномалія у сесії.",
        )

    passport_info = (
        {
            "min_temp": float(module.passport.min_temp),
            "max_temp": float(module.passport.max_temp),
            "min_humidity": float(module.passport.min_humidity),
            "max_humidity": float(module.passport.max_humidity),
            "min_pressure_hpa": float(module.passport.min_pressure_hpa),
            "max_pressure_hpa": float(module.passport.max_pressure_hpa),
            "ip_protection_class": module.passport.ip_protection_class,
        }
        if module.passport
        else {"note": "Технічний паспорт не заповнено"}
    )

    anomalies_list = [
        {
            "id": a.id,
            "parameter": a.parameter_name,
            "limit_type": a.limit_type,
            "recorded_value": float(a.recorded_value),
            "passport_limit": float(a.passport_limit),
            "severity": a.severity,
            "description": a.description,
        }
        for a in anomalies
    ]

    context_snapshot = {
        "module": {"serial_number": module.serial_number, "name": module.name},
        "passport": passport_info,
        "anomalies": anomalies_list,
    }

    prompt = (
        "Ти — інженер-діагност польових вимірювальних модулів. Проаналізуй технічний паспорт "
        "пристрою та зафіксовані кліматичні аномалії. Надай відповідь суворо у форматі JSON "
        "з двома ключами українською мовою: 'root_cause_analysis' (детальне пояснення фізичних "
        "причин збою або деградації сенсорів) та 'recommendations' (конкретні кроки з техобслуговування).\n\n"
        f"Контекст випробувань:\n{json.dumps(context_snapshot, ensure_ascii=False, indent=2)}"
    )

    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here":
        report = AIDiagnosticReport(
            session_id=session_id,
            anomaly_id=anomaly_id,
            requested_by=user_id,
            status="error",
            context_snapshot=context_snapshot,
            error_message="API-ключ GEMINI_API_KEY не налаштовано в середовищі сервера.",
            model_name=settings.GEMINI_MODEL,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            ),
            timeout=10.0,
        )
        parsed = json.loads(response.text)
        report = AIDiagnosticReport(
            session_id=session_id,
            anomaly_id=anomaly_id,
            requested_by=user_id,
            status="success",
            context_snapshot=context_snapshot,
            root_cause_analysis=parsed.get("root_cause_analysis", response.text),
            recommendations=parsed.get("recommendations", "Рекомендації не сформовано."),
            model_name=settings.GEMINI_MODEL,
        )
    except Exception as exc:
        # Graceful degradation: фіксуємо збій у БД без падіння сервера
        report = AIDiagnosticReport(
            session_id=session_id,
            anomaly_id=anomaly_id,
            requested_by=user_id,
            status="error",
            context_snapshot=context_snapshot,
            error_message=f"Помилка або таймаут звернення до LLM: {str(exc)}",
            model_name=settings.GEMINI_MODEL,
        )

    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report