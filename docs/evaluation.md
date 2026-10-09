# Evaluation

The prototype includes labeled synthetic telemetry so anomaly behavior can be tested repeatably.

Measured locally:

- Normal assets should remain healthy or warning unless sustained deviation exists.
- `MTR-204` contains a rising vibration scenario followed by increasing temperature.
- `CMP-072` contains pressure instability.
- `PMP-118` contains missing sensor readings.
- Risk scores are bounded from 0 to 100.

The `/evaluation` endpoint exposes:

- Ground-truth anomaly reading count.
- Detected anomaly windows.
- Detection latency estimate.
- Current risk exposure.
- Work-order statistics.
- Estimated cost exposure.

Important limitation: the risk score is a transparent heuristic for demo triage. It is not a calibrated probability of equipment failure.
