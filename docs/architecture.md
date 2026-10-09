# Architecture

PlantGuard AI uses a local-first architecture so judges can run the complete workflow without paid APIs, while preserving a clean path to Google Cloud.

```mermaid
sequenceDiagram
  participant UI as React UI
  participant API as FastAPI
  participant DB as SQLite
  participant DET as Detector
  participant AI as Investigation Provider
  participant G as Gemini on Vertex AI

  UI->>API: Request dashboard/assets
  API->>DB: Load seeded telemetry
  UI->>API: Run detection
  API->>DET: Detect persistent deviations
  DET->>DB: Persist anomalies and asset status
  UI->>API: Create investigation
  API->>DB: Fetch telemetry, anomaly, maintenance, docs
  alt USE_GEMINI=true
    API->>G: Structured evidence packet
    G-->>API: Validated JSON
  else local demo
    API->>AI: Deterministic evidence fallback
  end
  API->>DB: Store investigation
  UI->>API: Create/approve/complete work order
  API->>DB: Persist status and audit events
```

Core modules:

- `backend/app/seed.py`: deterministic industrial asset data and equipment knowledge.
- `backend/app/detector.py`: anomaly windows and risk scoring.
- `backend/app/ai.py`: provider interface, Gemini provider, and local fallback.
- `backend/app/retrieval.py`: upload validation, text extraction, chunking, and retrieval.
- `backend/app/main.py`: typed FastAPI endpoints.
- `frontend/src/main.tsx`: React operations console.
