# syntax=docker/dockerfile:1
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --require-hashes -r requirements.txt

FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=hereford.settings_production PORT=10000
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
RUN groupadd --gid 10001 hereford && useradd --uid 10001 --gid hereford --no-create-home hereford
COPY --chown=10001:10001 hereford/ hereford/
COPY --chown=10001:10001 docker/ docker/
RUN DJANGO_SETTINGS_MODULE=hereford.settings_container \
    DJANGO_SECRET_KEY=solo-build-sin-credenciales-ni-conexiones \
    DJANGO_DEBUG=false DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_NAME=build DATABASE_USER=build DATABASE_PASSWORD=build \
    DATABASE_HOST=localhost DATABASE_PORT=5432 \
    python hereford/manage.py collectstatic --noinput --verbosity 0
USER 10001:10001
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "docker/healthcheck.py"]
CMD ["sh", "docker/start.sh"]
