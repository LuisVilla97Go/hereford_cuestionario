#!/bin/sh
set -eu
# Las migraciones y cargas se ejecutan explícitamente antes del despliegue.
exec python -m uvicorn hereford.asgi:application --app-dir hereford \
  --host 0.0.0.0 --port "${PORT:-10000}" --no-proxy-headers --no-access-log