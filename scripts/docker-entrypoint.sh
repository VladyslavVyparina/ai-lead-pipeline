#!/usr/bin/env sh
set -eu

python -m alembic upgrade head

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
