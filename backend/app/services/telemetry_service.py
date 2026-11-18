from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Anomaly, Module, TelemetryRecord, TestSession
from app.schemas.dto import TelemetryPacketIn


async def process_telemetry_batch(
    db: AsyncSession, module: Module, packets: list[TelemetryPacketIn]
) -> tuple[int, int, int, list[Anomaly]]:
    # 1. Пошук єдиної активної сесії для модуля
    session_stmt = select(TestSession).where(
        TestSession.module_id == module.id, TestSession.status == "active"
    )
    session_res = await db.execute(session_stmt)
    active_session = session_res.scalar_one_or_none()

    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Активну серію випробувань для модуля '{module.serial_number}' не знайдено.",
        )

    # 2. Завантаження технічного паспорта модуля
    mod_stmt = (
        select(Module)
        .options(selectinload(Module.passport))
        .where(Module.id == module.id)
    )
    mod_with_passport = (await db.execute(mod_stmt)).scalar_one()
    passport = mod_with_passport.passport

    accepted_count = 0
    duplicates_skipped = 0
    detected_anomalies: list[Anomaly] = []

    for pkt in packets:
        # 3. Перевірка на дублікат (packet_id або recorded_at для цього модуля)
        dup_stmt = select(TelemetryRecord.id).where(
            TelemetryRecord.module_id == module.id,
            (TelemetryRecord.packet_id == pkt.packet_id)
            | (TelemetryRecord.recorded_at == pkt.recorded_at),
        )
        if (await db.execute(dup_stmt)).first():
            duplicates_skipped += 1
            continue

        # 4. Перевірка виходу за межі паспорта
        packet_anomalies_data: list[tuple[str, str, Decimal, Decimal, str]] = []
        if passport:
            checks = [
                ("temperature", "min", pkt.temperature, passport.min_temp, pkt.temperature < passport.min_temp, "°C"),
                ("temperature", "max", pkt.temperature, passport.max_temp, pkt.temperature > passport.max_temp, "°C"),
                ("humidity", "min", pkt.humidity, passport.min_humidity, pkt.humidity < passport.min_humidity, "%"),
                ("humidity", "max", pkt.humidity, passport.max_humidity, pkt.humidity > passport.max_humidity, "%"),
                ("pressure_hpa", "min", pkt.pressure_hpa, passport.min_pressure_hpa, pkt.pressure_hpa < passport.min_pressure_hpa, " гПа"),
                ("pressure_hpa", "max", pkt.pressure_hpa, passport.max_pressure_hpa, pkt.pressure_hpa > passport.max_pressure_hpa, " гПа"),
            ]
            for param, l_type, val, limit_val, is_violated, unit in checks:
                if is_violated:
                    diff = abs(val - limit_val)
                    severity = "critical" if diff > Decimal("5.0") else "warning"
                    direction = "Перевищено максимальний" if l_type == "max" else "Порушено мінімальний"
                    desc = f"{direction} паспортний поріг '{param}': зафіксовано {val}{unit} (межа: {limit_val}{unit})."
                    packet_anomalies_data.append((param, l_type, val, limit_val, severity, desc))

        record = TelemetryRecord(
            session_id=active_session.id,
            module_id=module.id,
            packet_id=pkt.packet_id,
            recorded_at=pkt.recorded_at,
            temperature=pkt.temperature,
            humidity=pkt.humidity,
            pressure_hpa=pkt.pressure_hpa,
            is_valid=len(packet_anomalies_data) == 0,
        )
        db.add(record)
        await db.flush()  # Отримуємо record.id без завершення транзакції
        accepted_count += 1

        for param, l_type, val, limit_val, severity, desc in packet_anomalies_data:
            anomaly = Anomaly(
                session_id=active_session.id,
                telemetry_id=record.id,
                parameter_name=param,
                limit_type=l_type,
                recorded_value=val,
                passport_limit=limit_val,
                severity=severity,
                description=desc,
            )
            db.add(anomaly)
            detected_anomalies.append(anomaly)

    await db.commit()
    for a in detected_anomalies:
        await db.refresh(a)

    return active_session.id, accepted_count, duplicates_skipped, detected_anomalies