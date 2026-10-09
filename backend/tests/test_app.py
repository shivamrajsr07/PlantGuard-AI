from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = f"sqlite:///{ROOT / 'data' / 'test.db'}"

from backend.app.database import Base, engine  # noqa: E402
from backend.app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.post("/simulator/reset")


def test_health_and_assets_startup() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["assets"] == 4
    assets = client.get("/assets").json()
    assert any(asset["id"] == "MTR-204" for asset in assets)


def test_dashboard_uses_seeded_data() -> None:
    data = client.get("/dashboard").json()
    assert data["assets"]["total"] == 4
    assert data["current_anomalies"] > 0
    assert data["alert_queue"]


def test_normal_and_abnormal_detection_and_risk_bounds() -> None:
    anomalies = client.get("/anomalies").json()
    assert any(a["asset_id"] == "MTR-204" and a["signal"] in {"vibration", "temperature"} for a in anomalies)
    assert all(0 <= a["risk_score"] <= 100 for a in anomalies)
    healthy = [asset for asset in client.get("/assets").json() if asset["id"] == "CNV-310"][0]
    assert healthy["status"] in {"healthy", "warning"}


def test_missing_telemetry_detected() -> None:
    telemetry = client.get("/assets/PMP-118/telemetry").json()
    assert any(row["temperature"] is None for row in telemetry)
    anomalies = client.get("/anomalies?asset_id=PMP-118").json()
    assert anomalies


def test_investigation_evidence_and_validated_output() -> None:
    anomaly = client.get("/anomalies?asset_id=MTR-204").json()[0]
    response = client.post("/investigations", json={"asset_id": "MTR-204", "anomaly_id": anomaly["id"]})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["demo_mode"] is True
    assert result["source_references"]
    assert "not confirmed" in result["uncertainty"].lower()


def test_work_order_approval_rejection_completion_and_audit() -> None:
    anomaly = client.get("/anomalies?asset_id=MTR-204").json()[0]
    inv = client.post("/investigations", json={"asset_id": "MTR-204", "anomaly_id": anomaly["id"]}).json()
    wo = client.post(
        "/work-orders",
        json={
            "asset_id": "MTR-204",
            "anomaly_id": anomaly["id"],
            "investigation_id": inv["id"],
            "priority": inv["result"]["priority"],
            "assigned_role": "Maintenance lead",
            "recommended_action": inv["result"]["recommended_maintenance_action"],
            "safety_checks": inv["result"]["safety_precautions"],
        },
    ).json()
    assert wo["status"] == "pending_approval"
    bad = client.post(f"/work-orders/{wo['id']}/status", json={"status": "completed"})
    assert bad.status_code == 409
    approved = client.post(f"/work-orders/{wo['id']}/approve", json={"actor": "Judge Demo"}).json()
    assert approved["status"] == "approved"
    complete = client.post(f"/work-orders/{wo['id']}/complete", json={"actor": "Tech", "notes": "Inspected safely and scheduled bearing replacement."}).json()
    assert complete["status"] == "completed"
    audit = client.get("/audit").json()
    assert any(event["action"] == "completed" and event["entity_id"] == wo["id"] for event in audit)


def test_rejection_path() -> None:
    anomaly = client.get("/anomalies?asset_id=MTR-204").json()[0]
    wo = client.post(
        "/work-orders",
        json={
            "asset_id": "MTR-204",
            "anomaly_id": anomaly["id"],
            "priority": "high",
            "assigned_role": "Reliability engineer",
            "recommended_action": "Inspect equipment before continuing production.",
            "safety_checks": ["Use lockout-tagout"],
        },
    ).json()
    rejected = client.post(f"/work-orders/{wo['id']}/reject", json={"actor": "Lead", "notes": "Duplicate request"}).json()
    assert rejected["status"] == "rejected"


def test_reset_prevents_duplicate_seed_events() -> None:
    first = client.get("/assets/MTR-204/telemetry").json()
    client.post("/simulator/reset")
    second = client.get("/assets/MTR-204/telemetry").json()
    assert len(first) == len(second) == 72


def test_invalid_document_upload_and_validation() -> None:
    response = client.post("/documents", files={"file": ("bad.bin", b"not allowed", "application/octet-stream")})
    assert response.status_code == 415
    response = client.post("/documents", files={"file": ("empty.txt", b"   ", "text/plain")})
    assert response.status_code == 422
    response = client.post("/documents", files={"file": ("guide.txt", b"Section\nbearing vibration alignment safety", "text/plain")})
    assert response.status_code == 200
    hits = client.get("/documents/search?q=bearing").json()
    assert any(hit["filename"] == "guide.txt" for hit in hits)
    response = client.post("/work-orders", json={"asset_id": "missing"})
    assert response.status_code == 422


def test_work_order_reference_validation_and_idempotency() -> None:
    mtr_anomaly = client.get("/anomalies?asset_id=MTR-204").json()[0]
    cmp_anomaly = client.get("/anomalies?asset_id=CMP-072").json()[0]
    inv = client.post("/investigations", json={"asset_id": "MTR-204", "anomaly_id": mtr_anomaly["id"]}).json()
    payload = {
        "asset_id": "MTR-204",
        "anomaly_id": mtr_anomaly["id"],
        "investigation_id": inv["id"],
        "priority": "high",
        "assigned_role": "Reliability engineer",
        "recommended_action": "Inspect equipment before continuing production.",
        "safety_checks": ["Use lockout-tagout"],
    }
    first = client.post("/work-orders", json=payload).json()
    second = client.post("/work-orders", json=payload).json()
    assert first["id"] == second["id"]
    bad = client.post("/work-orders", json={**payload, "anomaly_id": cmp_anomaly["id"]})
    assert bad.status_code == 409


def test_complete_workflow_to_approved_order() -> None:
    anomaly = client.get("/anomalies?asset_id=MTR-204").json()[0]
    inv = client.post("/investigations", json={"asset_id": "MTR-204", "anomaly_id": anomaly["id"]}).json()
    wo = client.post(
        "/work-orders",
        json={
            "asset_id": "MTR-204",
            "anomaly_id": anomaly["id"],
            "investigation_id": inv["id"],
            "priority": "critical",
            "assigned_role": "Maintenance supervisor",
            "recommended_action": "Perform vibration inspection and bearing maintenance after human approval.",
            "safety_checks": ["Use lockout-tagout", "Verify zero energy"],
        },
    ).json()
    approved = client.post(f"/work-orders/{wo['id']}/approve", json={"actor": "Supervisor"}).json()
    assert approved["status"] == "approved"
