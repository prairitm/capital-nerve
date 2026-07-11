#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  elif [[ -x "${ROOT_DIR}/../.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/../.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi
NPM_BIN="${NPM_BIN:-npm}"
HOST="${HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-45}"
RELOAD="${RELOAD:-0}"

mkdir -p "${LOG_DIR}"

declare -a SERVICE_NAMES=()
declare -a SERVICE_URLS=()
declare -a PIDS=()
CLEANED_UP=0

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

start_process() {
  local name="$1"
  local dir="$2"
  local url="$3"
  shift 3

  local log_file="${LOG_DIR}/${name}.log"
  echo "Starting ${name} -> ${url}"
  (
    cd "${dir}"
    "$@"
  ) >"${log_file}" 2>&1 &

  local pid=$!
  PIDS+=("${pid}")
  SERVICE_NAMES+=("${name}")
  SERVICE_URLS+=("${url}")
  echo "  pid=${pid} log=${log_file}"
}

cleanup() {
  local status=$?
  if [[ "${CLEANED_UP}" == "1" ]]; then
    exit "${status}"
  fi
  CLEANED_UP=1
  if ((${#PIDS[@]} > 0)); then
    echo
    echo "Stopping services..."
    for pid in "${PIDS[@]}"; do
      if kill -0 "${pid}" >/dev/null 2>&1; then
        kill "${pid}" >/dev/null 2>&1 || true
      fi
    done
    wait "${PIDS[@]}" >/dev/null 2>&1 || true
  fi
  exit "${status}"
}
trap cleanup EXIT INT TERM

wait_for_url() {
  local name="$1"
  local url="$2"
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))

  while ((SECONDS < deadline)); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "Ready ${name} (${url})"
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for ${name} (${url})" >&2
  echo "Last log lines:" >&2
  tail -n 40 "${LOG_DIR}/${name}.log" >&2 || true
  return 1
}

start_uvicorn() {
  local name="$1"
  local dir="$2"
  local app="$3"
  local port="$4"
  local url="http://${HOST}:${port}/health"

  if [[ "${RELOAD}" == "1" || "${RELOAD}" == "true" ]]; then
    start_process "${name}" "${dir}" "${url}" \
      "${PYTHON_BIN}" -m uvicorn "${app}" --host "${HOST}" --port "${port}" --reload
  else
    start_process "${name}" "${dir}" "${url}" \
      "${PYTHON_BIN}" -m uvicorn "${app}" --host "${HOST}" --port "${port}"
  fi
}

require_command "${PYTHON_BIN}"
require_command "${NPM_BIN}"
require_command curl

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies. Run: cd ${ROOT_DIR}/frontend && ${NPM_BIN} install" >&2
  exit 1
fi

start_uvicorn "backend" "${ROOT_DIR}/backend" "main:app" 8010
start_uvicorn "company" "${ROOT_DIR}/microservices/company" "company:app" 8020
start_uvicorn "event" "${ROOT_DIR}/microservices/event" "event:app" 8021
start_uvicorn "event_type" "${ROOT_DIR}/microservices/event_type" "event_type:app" 8022
start_uvicorn "values" "${ROOT_DIR}/microservices/values" "values:app" 8023
start_uvicorn "metrics" "${ROOT_DIR}/microservices/metrics" "metrics:app" 8024
start_uvicorn "signals" "${ROOT_DIR}/microservices/signals" "signals:app" 8025
start_uvicorn "alerts" "${ROOT_DIR}/microservices/alerts" "alerts:app" 8026

start_process "frontend" "${ROOT_DIR}/frontend" "http://127.0.0.1:5174" \
  "${NPM_BIN}" run dev -- --host "${FRONTEND_HOST}" --port 5174

echo
echo "Waiting for services..."
for i in "${!SERVICE_NAMES[@]}"; do
  wait_for_url "${SERVICE_NAMES[$i]}" "${SERVICE_URLS[$i]}"
done

cat <<EOF

All v4 services are running.
Frontend:      http://localhost:5174
Backend API:   http://${HOST}:8010
Microservices: http://${HOST}:8020-8026
Logs:          ${LOG_DIR}

Press Ctrl-C to stop everything.
EOF

wait "${PIDS[@]}"
