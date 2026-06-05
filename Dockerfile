# CNR eCourts scraper — Render (Docker) image.
# python:slim + playwright install --with-deps chromium guarantees the Chromium
# build matches the pip-installed Playwright version AND pulls the apt system
# libraries Chromium needs (the native render.yaml build often misses those).
FROM python:3.11-slim

WORKDIR /app

# System basics that some wheels / Chromium need
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium

COPY . .

ENV HEADLESS_MODE=true \
    BACKEND_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

# Render injects $PORT. Bind 0.0.0.0 so the platform can reach it.
CMD ["sh", "-c", "cd backend && uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
