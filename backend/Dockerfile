FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
WORKDIR /srv

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runtime
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=deps /opt/venv /opt/venv
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/opt/venv/bin:$PATH"
# Only Caddy can reach this container (no published port), so its X-Forwarded-For is trusted.
ENV FORWARDED_ALLOW_IPS="*"
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]

# Background worker: the same code plus LibreOffice (DOCX/PPTX -> PDF so page numbers match what
# users see) and fonts with Arabic coverage. Heavier than the API image on purpose; only the
# worker pays for it, and it never serves HTTP.
FROM runtime AS worker
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer libreoffice-impress \
    fonts-noto-core fonts-noto-ui-core fonts-dejavu-core fontconfig \
 && apt-get clean \
 && fc-cache -f
USER 10001
CMD ["celery", "-A", "app.worker.celery_app", "worker", "-Q", "ingest", "--concurrency=2", "--loglevel=INFO"]
