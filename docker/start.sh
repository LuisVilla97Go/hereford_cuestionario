#!/bin/sh
set -eu
if [ "${MIGRAR_AL_INICIAR:-0}" = "1" ]; then
  python hereford/manage.py migrate --noinput
  python hereford/manage.py migrate --check
fi
exec python -m uvicorn hereford.asgi:application --app-dir hereford \
  --host 0.0.0.0 --port "${PORT:-10000}" --no-proxy-headers --no-access-log
