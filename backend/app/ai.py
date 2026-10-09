from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy.orm import Session

from . import models, retrieval
from .schemas import InvestigationResult, SourceReference


class InvestigationProvider:
    name = "provider"

    def investigate(self, db: Session, asset: models.Asset, anomaly: models.Anomaly | None) -> InvestigationResult:
        raise NotImplementedError


class DemoInvestigationProvider(InvestigationProvider):
    name = "demo-fallback"

    def investigate(self, db: Session, asset: models.Asset, anomaly: models.Anomaly | None) -> InvestigationResult:
        recent = db.query(models.Telemetry).filter_by(asset_id=asset.id).order_by(models.Telemetry.timestamp.desc()).limit(12).all()
        maintenance = db.query(models.MaintenanceEvent).filter_by(asset_id=asset.id).order_by(models.MaintenanceEvent.timestamp.desc()).limit(3).all()
        query = f"{asset.kind} {anomaly.signal if anomaly else ''} vibration temperature safety maintenance"
        passages = retrieval.search_documents(db, query, limit=3)
        signal = anomaly.signal if anomaly else "telemetry"
        summary = (
            f"{asset.name} shows an evidence-backed {signal} anomaly with risk score {anomaly.risk_score}."
            if anomaly
            else f"{asset.name} investigation found no selected anomaly; review current telemetry before action."
        )
        symptoms = []
        if anomaly:
            symptoms.append(
                f"{signal.title()} averaged {anomaly.observed} versus expected baseline {anomaly.expected}; deviation {anomaly.deviation}."
            )
            symptoms.append(f"Persistence from {anomaly.start_time.isoformat()} to {anomaly.end_time.isoformat()} with {anomaly.severity} severity.")
        missing = sum(1 for r in recent if r.temperature is None or r.vibration is None or r.pressure is None)
        if missing:
            symptoms.append(f"{missing} recent readings contain missing sensor values.")
        evidence = symptoms + [f"Maintenance: {m.event_type} - {m.notes}" for m in maintenance]
        sources = [
            SourceReference(title=item["filename"], section=item["section"], chunk_id=item["chunk_id"], excerpt=item["excerpt"])
            for item in passages
        ]
        root_causes = ["Bearing wear or lubrication degradation", "Shaft/coupling misalignment"]
        if anomaly and anomaly.signal == "pressure":
            root_causes = ["Process pressure instability", "Control valve hunting", "Sensor calibration drift"]
        return InvestigationResult(
            executive_summary=summary,
            observed_symptoms=symptoms,
            evidence=evidence,
            plausible_root_causes=root_causes,
            alternative_explanations=["Temporary process load change", "Sensor calibration or mounting error"],
            diagnostic_checks=["Inspect bearing housing and coupling alignment", "Verify sensor mounting and calibration", "Review load and operating mode during the anomaly window"],
            recommended_maintenance_action="Create a maintenance work order for inspection, lubrication check, alignment verification, and controlled follow-up readings.",
            priority="critical" if anomaly and anomaly.risk_score >= 75 else "high" if anomaly and anomaly.risk_score >= 55 else "medium",
            priority_justification="Priority is based on severity, persistence, multi-signal escalation, and uncertainty from available evidence.",
            safety_precautions=["Use lockout-tagout", "Verify zero energy", "Keep guards installed until isolation is confirmed"],
            source_references=sources,
            uncertainty="Hypotheses are not confirmed root causes; physical inspection is required before repair decisions.",
            demo_mode=True,
        )


class GeminiInvestigationProvider(InvestigationProvider):
    name = "gemini-vertex"

    def investigate(self, db: Session, asset: models.Asset, anomaly: models.Anomaly | None) -> InvestigationResult:
        from google import genai
        from google.genai import types

        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is not configured.")
        evidence = build_evidence_packet(db, asset, anomaly)
        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=(
                "You are an industrial maintenance investigation assistant. Use only the provided evidence. "
                "Do not invent sensor values, maintenance history, or citations. Return valid JSON matching the requested schema.\n\n"
                f"Evidence:\n{json.dumps(evidence, default=str)}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InvestigationResult,
                temperature=0.2,
            ),
        )
        payload: Any = json.loads(response.text or "{}")
        payload["demo_mode"] = False
        return InvestigationResult.model_validate(payload)


def build_evidence_packet(db: Session, asset: models.Asset, anomaly: models.Anomaly | None) -> dict[str, Any]:
    telemetry = db.query(models.Telemetry).filter_by(asset_id=asset.id).order_by(models.Telemetry.timestamp.desc()).limit(18).all()
    maintenance = db.query(models.MaintenanceEvent).filter_by(asset_id=asset.id).order_by(models.MaintenanceEvent.timestamp.desc()).all()
    docs = retrieval.search_documents(db, f"{asset.kind} {anomaly.signal if anomaly else ''} vibration temperature pressure safety", limit=5)
    return {
        "asset": {"id": asset.id, "name": asset.name, "kind": asset.kind, "location": asset.location, "status": asset.status},
        "anomaly": None
        if anomaly is None
        else {
            "id": anomaly.id,
            "signal": anomaly.signal,
            "observed": anomaly.observed,
            "expected": anomaly.expected,
            "deviation": anomaly.deviation,
            "severity": anomaly.severity,
            "risk_score": anomaly.risk_score,
            "window": [anomaly.start_time, anomaly.end_time],
        },
        "telemetry": [
            {"timestamp": t.timestamp, "temperature": t.temperature, "vibration": t.vibration, "pressure": t.pressure, "scenario": t.scenario}
            for t in telemetry
        ],
        "maintenance": [{"timestamp": m.timestamp, "event_type": m.event_type, "notes": m.notes} for m in maintenance],
        "documents": docs,
    }


def get_provider() -> InvestigationProvider:
    if os.getenv("USE_GEMINI", "").lower() in {"1", "true", "yes"}:
        return GeminiInvestigationProvider()
    return DemoInvestigationProvider()
