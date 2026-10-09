from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="healthy")
    baseline_temp: Mapped[float] = mapped_column(Float)
    baseline_vibration: Mapped[float] = mapped_column(Float)
    baseline_pressure: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    telemetry = relationship("Telemetry", back_populates="asset", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="asset", cascade="all, delete-orphan")


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    vibration: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_ground_truth_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    scenario: Mapped[str] = mapped_column(String, default="normal")

    asset = relationship("Asset", back_populates="telemetry")


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    event_type: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chunks = relationship("DocumentChunk", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    section: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    signal: Mapped[str] = mapped_column(String)
    observed: Mapped[float] = mapped_column(Float)
    expected: Mapped[float] = mapped_column(Float)
    deviation: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String)
    risk_score: Mapped[int] = mapped_column(Integer)
    contributing_signals: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="open")

    asset = relationship("Asset", back_populates="anomalies")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomalies.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result_json: Mapped[str] = mapped_column(Text)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomalies.id"), nullable=True)
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String)
    assigned_role: Mapped[str] = mapped_column(String)
    recommended_action: Mapped[str] = mapped_column(Text)
    safety_checks: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="draft")
    approval_by: Mapped[str | None] = mapped_column(String, nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String, default="system")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
