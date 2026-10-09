from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from . import models


LIMITS = {
    "temperature": {"warn": 8.0, "critical": 14.0},
    "vibration": {"warn": 1.2, "critical": 2.4},
    "pressure": {"warn": 7.0, "critical": 12.0},
}


def _baseline(asset: models.Asset, signal: str) -> float:
    return {
        "temperature": asset.baseline_temp,
        "vibration": asset.baseline_vibration,
        "pressure": asset.baseline_pressure,
    }[signal]


def severity_for(signal: str, deviation: float, missing: bool = False) -> str:
    if missing:
        return "warning"
    limits = LIMITS[signal]
    if abs(deviation) >= limits["critical"]:
        return "critical"
    if abs(deviation) >= limits["warn"]:
        return "warning"
    return "normal"


def risk_score(asset: models.Asset, readings: list[models.Telemetry], signal_scores: dict[str, float], missing_count: int) -> int:
    severity_points = sum(signal_scores.values())
    persistence = min(20, max(0, len([r for r in readings if r.is_ground_truth_anomaly]) * 2))
    age_factor = 6 if any("bearing" in m.notes.lower() for m in []) else 0
    missing_penalty = min(15, missing_count * 3)
    return max(0, min(100, round(18 + severity_points + persistence + age_factor + missing_penalty)))


def detect_anomalies(db: Session, replace: bool = True) -> list[models.Anomaly]:
    if replace:
        db.query(models.Anomaly).delete()
        db.flush()

    created: list[models.Anomaly] = []
    for asset in db.query(models.Asset).all():
        readings = db.query(models.Telemetry).filter_by(asset_id=asset.id).order_by(models.Telemetry.timestamp).all()
        current_groups: dict[str, list[tuple[models.Telemetry, float, str]]] = defaultdict(list)
        missing_count = 0
        signal_scores: dict[str, float] = {}
        for reading in readings:
            for signal in ("temperature", "vibration", "pressure"):
                value = getattr(reading, signal)
                if value is None:
                    missing_count += 1
                    current_groups[signal].append((reading, 0.0, "warning"))
                    continue
                expected = _baseline(asset, signal)
                deviation = value - expected
                severity = severity_for(signal, deviation)
                if severity == "normal":
                    if len(current_groups[signal]) >= 2:
                        created.append(_persist_group(db, asset, signal, current_groups[signal], signal_scores, missing_count))
                    current_groups[signal] = []
                else:
                    current_groups[signal].append((reading, deviation, severity))
                    signal_scores[signal] = max(signal_scores.get(signal, 0), min(30, abs(deviation) * (8 if signal == "vibration" else 1.8)))
        for signal, group in current_groups.items():
            if len(group) >= 2:
                created.append(_persist_group(db, asset, signal, group, signal_scores, missing_count))

    _update_asset_statuses(db)
    db.commit()
    return created


def _persist_group(db: Session, asset: models.Asset, signal: str, group: list[tuple[models.Telemetry, float, str]], signal_scores: dict[str, float], missing_count: int) -> models.Anomaly:
    values = [getattr(item[0], signal) for item in group if getattr(item[0], signal) is not None]
    observed = mean(values) if values else _baseline(asset, signal)
    expected = _baseline(asset, signal)
    max_severity = "critical" if any(item[2] == "critical" for item in group) else "warning"
    anomaly = models.Anomaly(
        asset_id=asset.id,
        start_time=group[0][0].timestamp,
        end_time=group[-1][0].timestamp,
        signal=signal,
        observed=round(observed, 3),
        expected=round(expected, 3),
        deviation=round(observed - expected, 3),
        severity=max_severity,
        risk_score=risk_score(asset, [item[0] for item in group], signal_scores, missing_count),
        contributing_signals=json.dumps(sorted(signal_scores.keys() | {signal})),
    )
    db.add(anomaly)
    db.flush()
    return anomaly


def _update_asset_statuses(db: Session) -> None:
    for asset in db.query(models.Asset).all():
        anomalies = db.query(models.Anomaly).filter_by(asset_id=asset.id, status="open").all()
        if any(a.severity == "critical" for a in anomalies):
            asset.status = "critical"
        elif anomalies:
            asset.status = "warning"
        else:
            asset.status = "healthy"
