FROM python:3.11-slim AS backend
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY .env.example /app/.env.example
ENV PORT=8080
ENV DATABASE_URL=sqlite:////app/data/plantguard.db
RUN mkdir -p /app/data
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
