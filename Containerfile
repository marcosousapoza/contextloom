# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.11.31 AS uv

FROM python:3.12.11-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/contextloom
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
RUN DJANGO_SETTINGS_MODULE=contextloom.config.settings \
    CONTEXTLOOM_SECRET_KEY=collect-static \
    CONTEXTLOOM_DATABASE_URL=postgresql://unused:unused@localhost/unused \
    .venv/bin/django-admin collectstatic --noinput

FROM python:3.12.11-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="ContextLoom" \
      org.opencontainers.image.description="Self-hosted categorized knowledge retrieval" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/contextloom/contextloom" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
RUN groupadd --gid 10001 contextloom \
    && useradd --uid 10001 --gid contextloom --home-dir /opt/contextloom --no-create-home contextloom
WORKDIR /opt/contextloom
COPY --from=builder --chown=contextloom:contextloom /opt/contextloom/.venv .venv
COPY --from=builder --chown=contextloom:contextloom /opt/contextloom/var/static var/static
ENV PATH="/opt/contextloom/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTEXTLOOM_HOST=0.0.0.0 \
    CONTEXTLOOM_PORT=8000
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["contextloom"]
CMD ["serve"]
