from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field


# --- Auth & Users ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=150)
    role: str = Field(default="researcher", pattern="^(admin|researcher)$")


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|researcher)$")
    is_active: bool | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Modules & Passports ---
class PassportUpsert(BaseModel):
    min_temp: Decimal
    max_temp: Decimal
    min_humidity: Decimal = Field(ge=0, le=100)
    max_humidity: Decimal = Field(ge=0, le=100)
    min_pressure_hpa: Decimal
    max_pressure_hpa: Decimal
    ip_protection_class: str = Field(max_length=20)
    firmware_version: str | None = None


class PassportOut(PassportUpsert):
    id: int
    module_id: int

    class Config:
        from_attributes = True


class ModuleCreate(BaseModel):
    serial_number: str = Field(max_length=100)
    name: str = Field(max_length=150)
    status: str = Field(default="active", pattern="^(active|maintenance|inactive)$")
    passport: PassportUpsert | None = None


class ModuleOut(BaseModel):
    id: int
    serial_number: str
    name: str
    status: str
    created_at: datetime
    passport: PassportOut | None = None

    class Config:
        from_attributes = True


class ApiKeyCreatedOut(BaseModel):
    id: int
    module_id: int
    key_prefix: str
    raw_api_key: str
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: int
    module_id: int
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None

    class Config:
        from_attributes = True


# --- Condition Types & Observation Profiles ---
class ConditionTypeCreate(BaseModel):
    code: str = Field(max_length=50)
    name: str = Field(max_length=150)
    description: str | None = None


class ConditionTypeOut(ConditionTypeCreate):
    id: int

    class Config:
        from_attributes = True


class ProfileCreate(BaseModel):
    condition_type_id: int
    name: str = Field(max_length=150)
    sampling_interval_sec: int = Field(gt=0)
    alert_margin_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=50)
    description: str | None = None


class ProfileOut(ProfileCreate):
    id: int

    class Config:
        from_attributes = True


# --- Test Sessions ---
class SessionCreate(BaseModel):
    module_id: int
    profile_id: int
    title: str = Field(max_length=200)
    location: str | None = None


class SessionOut(BaseModel):
    id: int
    module_id: int
    profile_id: int
    operator_id: int
    title: str
    location: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None

    class Config:
        from_attributes = True


# --- Telemetry & Anomalies ---
class TelemetryPacketIn(BaseModel):
    packet_id: str = Field(max_length=64)
    recorded_at: datetime
    temperature: Decimal
    humidity: Decimal
    pressure_hpa: Decimal


class TelemetryBatchIn(BaseModel):
    packets: list[TelemetryPacketIn] = Field(min_length=1, max_length=500)


class AnomalyOut(BaseModel):
    id: int
    session_id: int
    telemetry_id: int
    parameter_name: str
    limit_type: str
    recorded_value: Decimal
    passport_limit: Decimal
    severity: str
    description: str
    detected_at: datetime

    class Config:
        from_attributes = True


class TelemetryIngestResponse(BaseModel):
    session_id: int
    accepted_count: int
    duplicates_skipped: int
    anomalies_detected: list[AnomalyOut]


class TelemetryOut(BaseModel):
    id: int
    session_id: int
    module_id: int
    packet_id: str
    recorded_at: datetime
    received_at: datetime
    temperature: Decimal
    humidity: Decimal
    pressure_hpa: Decimal
    is_valid: bool

    class Config:
        from_attributes = True


# --- LLM Diagnostics & Audit ---
class DiagnosticRequest(BaseModel):
    anomaly_id: int | None = None


class DiagnosticReportOut(BaseModel):
    id: int
    session_id: int
    anomaly_id: int | None
    requested_by: int
    status: str
    context_snapshot: dict
    root_cause_analysis: str | None
    recommendations: str | None
    error_message: str | None
    model_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    success: bool
    entity_type: str | None
    entity_id: str | None
    ip_address: str | None
    details: dict | None
    created_at: datetime

    class Config:
        from_attributes = True