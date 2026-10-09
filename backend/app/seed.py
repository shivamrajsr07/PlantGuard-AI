from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import detector, models


DEMO_ASSET_ID = "MTR-204"
SEED = 2048


DOC_TEXT = """Section: Motor vibration triage
Sustained vibration above the machine baseline can indicate bearing wear, shaft misalignment, coupling looseness, or lubrication breakdown. Compare the vibration trend with temperature and pressure before declaring a root cause.

Section: Thermal escalation
Rising motor temperature after vibration escalation increases maintenance priority. Inspect bearing housing, lubricant condition, cooling airflow, and electrical load. Use lockout-tagout before removing guards.

Section: Safety procedure
For rotating equipment, isolate power, verify zero energy, wear eye protection, and keep hands clear of couplings. Do not restart until guards are installed and a supervisor approves the work order.
"""


def reset_demo_data(db: Session) -> None:
    for table in (
        models.AuditEvent,
        models.WorkOrder,
        models.Investigation,
        models.Anomaly,
        models.DocumentChunk,
        models.Document,
        models.MaintenanceEvent,
        models.Telemetry,
        models.Asset,
    ):
        db.query(table).delete()
    db.commit()
    seed_if_empty(db)


def seed_if_empty(db: Session) -> None:
    if db.query(models.Asset).count():
        return

    rng = random.Random(SEED)
    assets = [
        models.Asset(id=DEMO_ASSET_ID, name="Line 2 Feedwater Motor", kind="Induction motor", location="Plant A / Line 2", baseline_temp=72, baseline_vibration=2.1, baseline_pressure=96),
        models.Asset(id="PMP-118", name="Cooling Loop Pump", kind="Centrifugal pump", location="Plant A / Utilities", baseline_temp=64, baseline_vibration=1.5, baseline_pressure=122),
        models.Asset(id="CMP-072", name="Compressor Stage 1", kind="Air compressor", location="Plant B / Bay 4", baseline_temp=82, baseline_vibration=2.8, baseline_pressure=144),
        models.Asset(id="CNV-310", name="Packaging Conveyor", kind="Conveyor drive", location="Plant A / Packaging", baseline_temp=55, baseline_vibration=1.2, baseline_pressure=40),
    ]
    db.add_all(assets)
    db.flush()

    start = datetime(2026, 10, 7, 0, 0, 0)
    for asset in assets:
        for hour in range(72):
            ts = start + timedelta(hours=hour)
            temp = asset.baseline_temp + rng.uniform(-2.0, 2.0)
            vibration = asset.baseline_vibration + rng.uniform(-0.18, 0.18)
            pressure = asset.baseline_pressure + rng.uniform(-3.0, 3.0)
            truth = False
            scenario = "normal"

            if asset.id == DEMO_ASSET_ID and 47 <= hour <= 61:
                vibration += 0.18 * (hour - 46) + rng.uniform(0.2, 0.45)
                truth = True
                scenario = "rising vibration"
            if asset.id == DEMO_ASSET_ID and 56 <= hour <= 71:
                temp += 0.75 * (hour - 55) + rng.uniform(0.5, 1.8)
                truth = True
                scenario = "vibration followed by rising temperature"
            if asset.id == "CMP-072" and 34 <= hour <= 39:
                pressure += (-1) ** hour * 15 + rng.uniform(-2, 2)
                truth = True
                scenario = "pressure instability"
            if asset.id == "PMP-118" and hour in (31, 32, 33):
                temp = None
                vibration = None
                pressure = None
                truth = True
                scenario = "sensor outage"

            db.add(
                models.Telemetry(
                    asset_id=asset.id,
                    timestamp=ts,
                    temperature=None if temp is None else round(temp, 2),
                    vibration=None if vibration is None else round(vibration, 3),
                    pressure=None if pressure is None else round(pressure, 2),
                    is_ground_truth_anomaly=truth,
                    scenario=scenario,
                )
            )

    db.add_all(
        [
            models.MaintenanceEvent(asset_id=DEMO_ASSET_ID, timestamp=start - timedelta(days=58), event_type="Inspection", notes="Bearing housing inspected after minor vibration; no shutdown performed."),
            models.MaintenanceEvent(asset_id=DEMO_ASSET_ID, timestamp=start - timedelta(days=15), event_type="Lubrication", notes="Lubricant topped up; technician noted audible roughness under load."),
            models.MaintenanceEvent(asset_id="PMP-118", timestamp=start - timedelta(days=30), event_type="Sensor calibration", notes="Temperature probe replaced and calibrated."),
        ]
    )

    doc = models.Document(filename="rotating-equipment-maintenance.txt", content_type="text/plain")
    db.add(doc)
    db.flush()
    for idx, chunk in enumerate([part.strip() for part in DOC_TEXT.split("\n\n") if part.strip()], start=1):
        first, _, rest = chunk.partition("\n")
        db.add(models.DocumentChunk(document_id=doc.id, section=first.replace("Section: ", ""), text=rest.strip()))

    db.commit()
    detector.detect_anomalies(db)
    db.add(models.AuditEvent(entity_type="system", entity_id="seed", action="demo_seeded", actor="system", details="Deterministic PlantGuard AI scenario initialized."))
    db.commit()
