from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="researcher")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'researcher')", name="ck_users_role"),
    )


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    passport: Mapped["ModulePassport | None"] = relationship(
        back_populates="module", uselist=False, cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["IoTApiKey"]] = relationship(back_populates="module", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'maintenance', 'inactive')", name="ck_modules_status"),
    )


class ModulePassport(Base):
    __tablename__ = "module_passports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    min_temp: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_temp: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    min_humidity: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_humidity: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    min_pressure_hpa: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    max_pressure_hpa: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    ip_protection_class: Mapped[str] = mapped_column(String(20), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    module: Mapped["Module"] = relationship(back_populates="passport")

    __table_args__ = (
        CheckConstraint("min_temp < max_temp", name="ck_passport_temp_range"),
        CheckConstraint("min_humidity >= 0 AND min_humidity < max_humidity AND max_humidity <= 100", name="ck_passport_humidity_range"),
        CheckConstraint("min_pressure_hpa < max_pressure_hpa", name="ck_passport_pressure_range"),
    )


class IoTApiKey(Base):
    __tablename__ = "iot_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    module: Mapped["Module"] = relationship(back_populates="api_keys")


class TestConditionType(Base):
    __tablename__ = "test_condition_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ObservationProfile(Base):
    __tablename__ = "observation_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_type_id: Mapped[int] = mapped_column(ForeignKey("test_condition_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    sampling_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_margin_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("sampling_interval_sec > 0", name="ck_profile_sampling_interval"),
    )


class TestSession(Base):
    __tablename__ = "test_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(ForeignKey("observation_profiles.id"), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'aborted')", name="ck_sessions_status"),
        Index(
            "uq_active_session_per_module",
            "module_id",
            unique=True,
            postgresql_where=text("status = 'active'")
        ),
    )


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False)
    packet_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    humidity: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    pressure_hpa: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("module_id", "packet_id", name="uq_telemetry_module_packet"),
        UniqueConstraint("module_id", "recorded_at", name="uq_telemetry_module_recorded_at"),
        Index("idx_telemetry_module_recorded_desc", "module_id", recorded_at.desc()),
    )


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False)
    telemetry_id: Mapped[int] = mapped_column(ForeignKey("telemetry_records.id", ondelete="CASCADE"), nullable=False)
    parameter_name: Mapped[str] = mapped_column(String(30), nullable=False)
    limit_type: Mapped[str] = mapped_column(String(10), nullable=False)
    recorded_value: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    passport_limit: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("parameter_name IN ('temperature', 'humidity', 'pressure_hpa')", name="ck_anomaly_param"),
        CheckConstraint("limit_type IN ('min', 'max')", name="ck_anomaly_limit_type"),
        CheckConstraint("severity IN ('warning', 'critical')", name="ck_anomaly_severity"),
    )


class AIDiagnosticReport(Base):
    __tablename__ = "ai_diagnostic_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False)
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomalies.id"), nullable=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('success', 'error')", name="ck_ai_report_status"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)