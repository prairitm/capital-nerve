#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 SERVICE_NAME" >&2
  exit 2
fi

SERVICE_NAME="$1"
V4_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${V4_DIR}/../.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python virtual environment not found at ${PYTHON_BIN}" >&2
  exit 1
fi

case "${SERVICE_NAME}" in
  backend)
    WORKING_DIR="${V4_DIR}/backend"
    APP="main:app"
    PORT=8010
    ;;
  company)
    WORKING_DIR="${V4_DIR}/microservices/company"
    APP="company:app"
    PORT=8020
    ;;
  event)
    WORKING_DIR="${V4_DIR}/microservices/event"
    APP="event:app"
    PORT=8021
    ;;
  event_type)
    WORKING_DIR="${V4_DIR}/microservices/event_type"
    APP="event_type:app"
    PORT=8022
    ;;
  values)
    WORKING_DIR="${V4_DIR}/microservices/values"
    APP="values:app"
    PORT=8023
    ;;
  metrics)
    WORKING_DIR="${V4_DIR}/microservices/metrics"
    APP="metrics:app"
    PORT=8024
    ;;
  signals)
    WORKING_DIR="${V4_DIR}/microservices/signals"
    APP="signals:app"
    PORT=8025
    ;;
  alerts)
    WORKING_DIR="${V4_DIR}/microservices/alerts"
    APP="alerts:app"
    PORT=8026
    ;;
  monitor)
    WORKING_DIR="${V4_DIR}/microservices"
    APP="monitor.monitor:app"
    PORT=8027
    for dependency_port in 8010 8020 8021 8022 8023 8024 8025 8026; do
      ready=0
      for _ in $(seq 1 60); do
        if curl -fsS "http://127.0.0.1:${dependency_port}/health" >/dev/null 2>&1; then
          ready=1
          break
        fi
        sleep 1
      done
      if [[ "${ready}" -ne 1 ]]; then
        echo "Dependency on port ${dependency_port} did not become healthy" >&2
        exit 1
      fi
    done
    ;;
  *)
    echo "Unknown CapitalNerve service: ${SERVICE_NAME}" >&2
    exit 2
    ;;
esac

cd "${WORKING_DIR}"
exec "${PYTHON_BIN}" -m uvicorn "${APP}" \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --workers 1 \
  --no-access-log
