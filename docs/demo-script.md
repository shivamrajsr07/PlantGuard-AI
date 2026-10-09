# Three-Minute Demo Script

1. From the project root, run `npm run dev`. The backend starts, then the website opens at `http://127.0.0.1:5173`.
2. Point out the simulated-data indicator and the current anomaly queue.
3. Go to Guided Demo. The scenario uses `MTR-204`, a feedwater motor with rising vibration followed by rising temperature.
4. Click Detect. Explain that the backend compares observed telemetry to the stored baseline and persists anomaly windows.
5. Click Investigate. Show observed symptoms, hypotheses, uncertainty, and source references from stored maintenance knowledge.
6. Click Create Work Order. Explain that consequential maintenance is not automatic; it is routed to a human.
7. Click Approve. Show status moving from pending approval to approved.
8. Click Complete. Mention completion notes and append-only audit events.
9. Open Work Orders and Evaluation to show persistent state, work-order statistics, and risk exposure.
10. Click Reset in Guided Demo to restore the deterministic scenario without duplicate telemetry.
