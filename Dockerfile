# Optional build_ca_bundle is a trusted CA bundle for proxied build environments; it is never copied into the image.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -s /run/secrets/build_ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -s /run/secrets/build_ca_bundle ]; then export PIP_CERT=/run/secrets/build_ca_bundle; fi; \
    pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin clubwire
COPY --chown=clubwire:clubwire app/ ./app/
COPY --chown=clubwire:clubwire alembic/ ./alembic/
COPY --chown=clubwire:clubwire alembic.ini ./
COPY --chown=clubwire:clubwire scripts/ ./scripts/
COPY --from=frontend-build --chown=clubwire:clubwire /build/frontend/dist/ ./frontend/dist/
USER clubwire
EXPOSE 8000
CMD ["sh", "-c", "python -c 'import os; assert len(os.environ.get(\"SECRET_KEY\", \"\")) >= 32, \"SECRET_KEY must contain at least 32 characters\"' && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
