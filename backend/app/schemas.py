from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TelemetryOut(BaseModel):
    timestamp: datetime
    temperature: float | None
    vibration: float | None
    pressure: float | None
    is_ground_truth_anomaly: bool
    scenario: str


class AssetOut(BaseModel):
    id: str
    name: str
    kind: str
    location: str
    status: str
    baseline_temp: float
    baseline_vibration: float
    baseline_pressure: float


class AnomalyOut(BaseModel):
    id: int
    asset_id: str
    start_time: datetime
    end_time: datetime
    signal: str
    observed: float
    expected: float
    deviation: float
    severity: str
    risk_score: int
    contributing_signals: list[str]
    status: str


class SourceReference(BaseModel):
    title: str
    section: str
    chunk_id: int | None = None
    excerpt: str


class InvestigationResult(BaseModel):
    executive_summary: str
    observed_symptoms: list[str]
    evidence: list[str]
    plausible_root_causes: list[str]
    alternative_explanations: list[str]
    diagnostic_checks: list[str]
    recommended_maintenance_action: str
    priority: Literal["low", "medium", "high", "critical"]
    priority_justification: str
    safety_precautions: list[str]
    source_references: list[SourceReference]
    uncertainty: str
    demo_mode: bool


class InvestigationCreate(BaseModel):
    asset_id: str
    anomaly_id: int | None = None


class InvestigationOut(BaseModel):
    id: int
    asset_id: str
    anomaly_id: int | None
    provider: str
    created_at: datetime
    result: InvestigationResult


class WorkOrderCreate(BaseModel):
    asset_id: str
    anomaly_id: int | None = None
    investigation_id: int | None = None
    priority: Literal["low", "medium", "high", "critical"]
    assigned_role: str = Field(min_length=2)
    recommended_action: str = Field(min_length=10)
    safety_checks: list[str]


class WorkOrderOut(BaseModel):
    id: str
    asset_id: str
    anomaly_id: int | None
    investigation_id: int | None
    priority: str
    assigned_role: str
    recommended_action: str
    safety_checks: list[str]
    status: str
    approval_by: str | None
    completion_notes: str | None
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    status: Literal["pending_approval", "in_progress", "completed", "cancelled"]
    actor: str = "operator"
    notes: str = ""


class ApprovalRequest(BaseModel):
    actor: str = Field(default="maintenance-lead", min_length=2)
    notes: str = ""


class CompletionRequest(BaseModel):
    actor: str = "technician"
    notes: str = Field(min_length=5)


class AuditOut(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    actor: str
    details: str
    created_at: datetime


class DashboardSummary(BaseModel):
    assets: dict[str, int]
    open_work_orders: int
    current_anomalies: int
    risk_distribution: dict[str, int]
    trends: list[dict[str, Any]]
    recent_investigations: list[dict[str, Any]]
    alert_queue: list[dict[str, Any]]


class DocumentSearchResult(BaseModel):
    chunk_id: int
    filename: str
    section: str
    excerpt: str
    score: int
