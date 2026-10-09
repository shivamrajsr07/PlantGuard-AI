from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import ai, detector, models, retrieval, seed
from .database import SessionLocal, get_db, init_db
from .schemas import (
    AnomalyOut,
    ApprovalRequest,
    AssetOut,
    AuditOut,
    CompletionRequest,
    DashboardSummary,
    DocumentSearchResult,
    InvestigationCreate,
    InvestigationOut,
    StatusUpdate,
    TelemetryOut,
    WorkOrderCreate,
    WorkOrderOut,
)


logger = logging.getLogger("plantguard")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed.seed_if_empty(db)
    yield


app = FastAPI(title="PlantGuard AI", version="0.1.0", lifespan=lifespan)
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def anomaly_out(row: models.Anomaly) -> AnomalyOut:
    return AnomalyOut(
        id=row.id,
        asset_id=row.asset_id,
        start_time=row.start_time,
        end_time=row.end_time,
        signal=row.signal,
        observed=row.observed,
        expected=row.expected,
        deviation=row.deviation,
        severity=row.severity,
        risk_score=row.risk_score,
        contributing_signals=json.loads(row.contributing_signals or "[]"),
        status=row.status,
    )


def work_order_out(row: models.WorkOrder) -> WorkOrderOut:
    return WorkOrderOut(
        id=row.id,
        asset_id=row.asset_id,
        anomaly_id=row.anomaly_id,
        investigation_id=row.investigation_id,
        priority=row.priority,
        assigned_role=row.assigned_role,
        recommended_action=row.recommended_action,
        safety_checks=json.loads(row.safety_checks or "[]"),
        status=row.status,
        approval_by=row.approval_by,
        completion_notes=row.completion_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def audit(db: Session, entity_type: str, entity_id: str, action: str, actor: str = "system", details: str = "") -> None:
    db.add(models.AuditEvent(entity_type=entity_type, entity_id=entity_id, action=action, actor=actor, details=details))


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    return {"status": "ok", "assets": db.query(models.Asset).count(), "mode": "local-demo" if not os.getenv("USE_GEMINI") else "gemini"}


@app.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db)) -> DashboardSummary:
    assets = db.query(models.Asset).all()
    status_counts = {status: 0 for status in ("healthy", "warning", "critical")}
    for asset in assets:
        status_counts[asset.status] = status_counts.get(asset.status, 0) + 1
    anomalies = db.query(models.Anomaly).filter_by(status="open").order_by(models.Anomaly.risk_score.desc()).all()
    telemetry = db.query(models.Telemetry).order_by(models.Telemetry.timestamp.desc()).limit(24).all()
    trends = [
        {"timestamp": t.timestamp.isoformat(), "temperature": t.temperature, "vibration": t.vibration, "pressure": t.pressure}
        for t in reversed(telemetry)
    ]
    investigations = db.query(models.Investigation).order_by(models.Investigation.created_at.desc()).limit(5).all()
    return DashboardSummary(
        assets={"total": len(assets), **status_counts},
        open_work_orders=db.query(models.WorkOrder).filter(models.WorkOrder.status.notin_(["completed", "cancelled", "rejected"])).count(),
        current_anomalies=len(anomalies),
        risk_distribution={"low": sum(a.risk_score < 35 for a in anomalies), "medium": sum(35 <= a.risk_score < 55 for a in anomalies), "high": sum(55 <= a.risk_score < 75 for a in anomalies), "critical": sum(a.risk_score >= 75 for a in anomalies)},
        trends=trends,
        recent_investigations=[{"id": i.id, "asset_id": i.asset_id, "provider": i.provider, "created_at": i.created_at.isoformat()} for i in investigations],
        alert_queue=[{"id": a.id, "asset_id": a.asset_id, "signal": a.signal, "severity": a.severity, "risk_score": a.risk_score} for a in anomalies[:8]],
    )


@app.get("/assets", response_model=list[AssetOut])
def assets(q: str = "", status: str = "", db: Session = Depends(get_db)) -> list[models.Asset]:
    query = db.query(models.Asset)
    if q:
        query = query.filter(models.Asset.name.ilike(f"%{q}%") | models.Asset.id.ilike(f"%{q}%"))
    if status:
        query = query.filter_by(status=status)
    return query.order_by(models.Asset.id).all()


@app.get("/assets/{asset_id}", response_model=AssetOut)
def asset_detail(asset_id: str, db: Session = Depends(get_db)) -> models.Asset:
    asset = db.get(models.Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return asset


@app.get("/assets/{asset_id}/telemetry", response_model=list[TelemetryOut])
def asset_telemetry(asset_id: str, limit: int = 72, db: Session = Depends(get_db)) -> list[models.Telemetry]:
    if not db.get(models.Asset, asset_id):
        raise HTTPException(status_code=404, detail="Asset not found.")
    return list(reversed(db.query(models.Telemetry).filter_by(asset_id=asset_id).order_by(models.Telemetry.timestamp.desc()).limit(min(limit, 500)).all()))


@app.post("/anomalies/detect", response_model=list[AnomalyOut])
def run_detection(db: Session = Depends(get_db)) -> list[AnomalyOut]:
    rows = detector.detect_anomalies(db)
    audit(db, "anomaly", "bulk", "detection_run", details=f"{len(rows)} anomalies detected")
    db.commit()
    return [anomaly_out(a) for a in rows]


@app.get("/anomalies", response_model=list[AnomalyOut])
def anomalies(asset_id: str = "", db: Session = Depends(get_db)) -> list[AnomalyOut]:
    query = db.query(models.Anomaly)
    if asset_id:
        query = query.filter_by(asset_id=asset_id)
    return [anomaly_out(a) for a in query.order_by(models.Anomaly.risk_score.desc()).all()]


@app.post("/investigations", response_model=InvestigationOut)
def create_investigation(payload: InvestigationCreate, db: Session = Depends(get_db)) -> InvestigationOut:
    asset = db.get(models.Asset, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    anomaly = db.get(models.Anomaly, payload.anomaly_id) if payload.anomaly_id else None
    if payload.anomaly_id and not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found.")
    provider = ai.get_provider()
    try:
        result = provider.investigate(db, asset, anomaly)
    except Exception as exc:
        logger.warning("Investigation provider failed; using deterministic fallback: %s", exc.__class__.__name__)
        provider = ai.DemoInvestigationProvider()
        result = provider.investigate(db, asset, anomaly)
    inv = models.Investigation(asset_id=asset.id, anomaly_id=anomaly.id if anomaly else None, provider=provider.name, result_json=result.model_dump_json())
    db.add(inv)
    db.flush()
    audit(db, "investigation", str(inv.id), "created", details=f"provider={provider.name}")
    db.commit()
    return InvestigationOut(id=inv.id, asset_id=inv.asset_id, anomaly_id=inv.anomaly_id, provider=inv.provider, created_at=inv.created_at, result=result)


@app.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(db: Session = Depends(get_db)) -> list[InvestigationOut]:
    rows = db.query(models.Investigation).order_by(models.Investigation.created_at.desc()).all()
    return [InvestigationOut(id=r.id, asset_id=r.asset_id, anomaly_id=r.anomaly_id, provider=r.provider, created_at=r.created_at, result=json.loads(r.result_json)) for r in rows]


@app.post("/work-orders", response_model=WorkOrderOut)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db)) -> WorkOrderOut:
    if not db.get(models.Asset, payload.asset_id):
        raise HTTPException(status_code=404, detail="Asset not found.")
    if payload.anomaly_id:
        anomaly = db.get(models.Anomaly, payload.anomaly_id)
        if not anomaly:
            raise HTTPException(status_code=404, detail="Anomaly not found.")
        if anomaly.asset_id != payload.asset_id:
            raise HTTPException(status_code=409, detail="Anomaly does not belong to the selected asset.")
    if payload.investigation_id:
        investigation = db.get(models.Investigation, payload.investigation_id)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found.")
        if investigation.asset_id != payload.asset_id:
            raise HTTPException(status_code=409, detail="Investigation does not belong to the selected asset.")
    existing = (
        db.query(models.WorkOrder)
        .filter_by(asset_id=payload.asset_id, anomaly_id=payload.anomaly_id, investigation_id=payload.investigation_id)
        .filter(models.WorkOrder.status.notin_(["completed", "cancelled", "rejected"]))
        .order_by(models.WorkOrder.created_at.desc())
        .first()
    )
    if existing:
        return work_order_out(existing)
    wo = models.WorkOrder(
        id=f"WO-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}",
        asset_id=payload.asset_id,
        anomaly_id=payload.anomaly_id,
        investigation_id=payload.investigation_id,
        priority=payload.priority,
        assigned_role=payload.assigned_role,
        recommended_action=payload.recommended_action,
        safety_checks=json.dumps(payload.safety_checks),
        status="pending_approval",
    )
    db.add(wo)
    audit(db, "work_order", wo.id, "created", details="Consequential maintenance recommendation requires human approval.")
    db.commit()
    return work_order_out(wo)


@app.get("/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(db: Session = Depends(get_db)) -> list[WorkOrderOut]:
    return [work_order_out(w) for w in db.query(models.WorkOrder).order_by(models.WorkOrder.created_at.desc()).all()]


@app.post("/work-orders/{work_order_id}/approve", response_model=WorkOrderOut)
def approve_work_order(work_order_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)) -> WorkOrderOut:
    wo = _get_work_order(db, work_order_id)
    if wo.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending approval work orders can be approved.")
    wo.status = "approved"
    wo.approval_by = payload.actor
    wo.updated_at = datetime.utcnow()
    audit(db, "work_order", wo.id, "approved", actor=payload.actor, details=payload.notes)
    db.commit()
    return work_order_out(wo)


@app.post("/work-orders/{work_order_id}/reject", response_model=WorkOrderOut)
def reject_work_order(work_order_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)) -> WorkOrderOut:
    wo = _get_work_order(db, work_order_id)
    if wo.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending approval work orders can be rejected.")
    wo.status = "rejected"
    wo.approval_by = payload.actor
    wo.updated_at = datetime.utcnow()
    audit(db, "work_order", wo.id, "rejected", actor=payload.actor, details=payload.notes)
    db.commit()
    return work_order_out(wo)


@app.post("/work-orders/{work_order_id}/status", response_model=WorkOrderOut)
def update_work_order(work_order_id: str, payload: StatusUpdate, db: Session = Depends(get_db)) -> WorkOrderOut:
    wo = _get_work_order(db, work_order_id)
    allowed = {("approved", "in_progress"), ("in_progress", "completed"), ("pending_approval", "cancelled"), ("approved", "cancelled")}
    if (wo.status, payload.status) not in allowed:
        raise HTTPException(status_code=409, detail=f"Invalid transition from {wo.status} to {payload.status}.")
    wo.status = payload.status
    wo.updated_at = datetime.utcnow()
    audit(db, "work_order", wo.id, f"status_{payload.status}", actor=payload.actor, details=payload.notes)
    db.commit()
    return work_order_out(wo)


@app.post("/work-orders/{work_order_id}/complete", response_model=WorkOrderOut)
def complete_work_order(work_order_id: str, payload: CompletionRequest, db: Session = Depends(get_db)) -> WorkOrderOut:
    wo = _get_work_order(db, work_order_id)
    if wo.status not in {"approved", "in_progress"}:
        raise HTTPException(status_code=409, detail="Work order must be approved or in progress before completion.")
    wo.status = "completed"
    wo.completion_notes = payload.notes
    wo.updated_at = datetime.utcnow()
    audit(db, "work_order", wo.id, "completed", actor=payload.actor, details=payload.notes)
    db.commit()
    return work_order_out(wo)


def _get_work_order(db: Session, work_order_id: str) -> models.WorkOrder:
    wo = db.get(models.WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found.")
    return wo


@app.get("/audit", response_model=list[AuditOut])
def audit_log(db: Session = Depends(get_db)) -> list[models.AuditEvent]:
    return db.query(models.AuditEvent).order_by(models.AuditEvent.created_at.desc()).limit(100).all()


@app.post("/documents")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    doc = await retrieval.ingest_document(db, file)
    audit(db, "document", str(doc.id), "uploaded", details=doc.filename)
    db.commit()
    return {"id": doc.id, "filename": doc.filename, "chunks": len(doc.chunks)}


@app.get("/documents/search", response_model=list[DocumentSearchResult])
def document_search(q: str, db: Session = Depends(get_db)) -> list[dict]:
    return retrieval.search_documents(db, q)


@app.post("/simulator/reset")
def reset_simulator(db: Session = Depends(get_db)) -> dict:
    seed.reset_demo_data(db)
    return {"status": "reset", "asset_id": seed.DEMO_ASSET_ID}


@app.get("/evaluation")
def evaluation(db: Session = Depends(get_db)) -> dict:
    truth_rows = db.query(models.Telemetry).filter_by(is_ground_truth_anomaly=True).count()
    anomaly_rows = db.query(models.Anomaly).count()
    critical_assets = db.query(models.Asset).filter_by(status="critical").count()
    work_orders = db.query(models.WorkOrder).count()
    completed = db.query(models.WorkOrder).filter_by(status="completed").count()
    return {
        "ground_truth_anomaly_readings": truth_rows,
        "detected_anomaly_windows": anomaly_rows,
        "false_alert_rate_note": "Window-level heuristic metric; true negative windows are estimated in tests, not calibrated production ML.",
        "detection_latency_hours": 2,
        "current_risk_exposure": sum(a.risk_score for a in db.query(models.Anomaly).filter_by(status="open").all()),
        "estimated_cost_exposure_usd": critical_assets * 18000 + anomaly_rows * 2500,
        "work_orders": {"total": work_orders, "completed": completed},
        "calibration_warning": "Risk score is a transparent heuristic, not a calibrated failure probability.",
    }
