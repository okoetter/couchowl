# syntax=docker/dockerfile:1.7
# watchit production image: Debian slim, multi-stage, runs as non-root.

ARG PYTHON_VERSION=3.15

# --- supercronic (cron for containers), verified by checksum per architecture -----
FROM python:${PYTHON_VERSION}-slim AS supercronic
RUN python - <<'EOF'
import hashlib, os, platform, urllib.request

VERSION = "v0.2.51"
CHECKSUMS = {
    "amd64": "cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123",
    "arm64": "4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94",
}
arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
url = f"https://github.com/aptible/supercronic/releases/download/{VERSION}/supercronic-linux-{arch}"
data = urllib.request.urlopen(url, timeout=60).read()
digest = hashlib.sha256(data).hexdigest()
if digest != CHECKSUMS[arch]:
    raise SystemExit(f"supercronic checksum mismatch for {arch}: {digest}")
with open("/supercronic", "wb") as f:
    f.write(data)
os.chmod("/supercronic", 0o755)
EOF

# --- Builder: install dependencies into a virtualenv with uv ----------------------
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .
# Collect static files at build time (image stays immutable; app runs read-only on /app)
RUN SECRET_KEY=build-only DATA_DIR=/tmp/build-data \
    /app/.venv/bin/python manage.py collectstatic --noinput -v 0

# --- Final image ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

# tini runs as PID 1: forwards signals and reaps zombie processes
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 watchit \
    && useradd --system --uid 1000 --gid 1000 --home-dir /app --no-create-home watchit \
    && mkdir -p /data \
    && chown watchit:watchit /data

COPY --from=supercronic /supercronic /usr/local/bin/supercronic
COPY --from=builder --chown=root:root /app /app

WORKDIR /app
USER watchit
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4)"]

ENTRYPOINT ["tini", "--", "/app/docker/entrypoint.sh"]
CMD ["honcho", "start", "--procfile", "/app/docker/Procfile"]
