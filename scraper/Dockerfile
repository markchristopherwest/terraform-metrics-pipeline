FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMETHEUS_DISABLE_CREATED_SERIES=True \
    REPORTS_DIR=/reports \
    PORT=9464 \
    SCAN_INTERVAL=5 \
    STALE_AFTER_SECONDS=900

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY metrics_scraper.py .

# Runs as root on purpose: the reports bind-mount is written by the Terraform
# container (root) and the scraper appends reports/derived/prisma_changes.jsonl.
EXPOSE 9464
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9464/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["python3", "/app/metrics_scraper.py"]
