# Google Cloud Setup

Implemented:

- Optional Gemini investigation provider through the official Google Gen AI SDK with Vertex AI configuration.
- Cloud Run-ready backend `Dockerfile`.
- Environment-based configuration and local fallback mode.

Required before live Gemini:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com run.googleapis.com artifactregistry.googleapis.com
```

Environment:

```bash
USE_GEMINI=true
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
CORS_ORIGINS=https://YOUR_FRONTEND_DOMAIN
```

Deploy API:

```bash
gcloud run deploy plantguard-ai-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars USE_GEMINI=true,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=us-central1
```

Not yet configured:

- BigQuery analytics.
- Vertex AI Search.
- Cloud Storage document persistence.
- Managed production database.
