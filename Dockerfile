# Multi-stage build for the FPI Reasoning Engine + API.
# Edge demo target: Jetson Orin Nano / Raspberry Pi 5 (arm64) or plain x86_64.
# The dashboard is built and served separately (see dashboard/Dockerfile, docker-compose.yml).

# --- Stage 1: build wheels for dependencies ---------------------------------
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# --- Stage 2: slim runtime --------------------------------------------------
FROM python:3.11-slim AS runtime
LABEL org.opencontainers.image.title="FPI Reasoning Engine + API"
LABEL org.opencontainers.image.description="Failure Propagation Intelligence — research/hackathon MVP"

# Non-root user for the edge runtime
RUN useradd --create-home --uid 1000 fpi
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels

COPY fpi/ ./fpi/
COPY api/ ./api/
COPY scripts/ ./scripts/

USER fpi
EXPOSE 8000
# Health: the API exposes /health (see api/main.py)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
