#!/usr/bin/env bash
set -euo pipefail

V4_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${V4_DIR}/.." && pwd)"
DEPLOY_USER="${SUDO_USER:-${USER}}"
DEPLOY_GROUP="$(id -gn "${DEPLOY_USER}")"
ENV_DIR="/etc/capital-nerve"
APP_ENV="${ENV_DIR}/v4.env"
OPENAI_ENV="${ENV_DIR}/openai.env"
WEB_ROOT="/var/www/capital-nerve"
SYSTEMD_TEMPLATE="/etc/systemd/system/capital-nerve@.service"
SYSTEMD_TARGET="/etc/systemd/system/capital-nerve.target"
CADDYFILE="/etc/caddy/Caddyfile"
CADDY_PORT="${CAPITAL_NERVE_CADDY_PORT:-8188}"
SERVICES=(backend company event event_type values metrics signals alerts monitor)
PORTS=(8010 8020 8021 8022 8023 8024 8025 8026 8027)

info() {
  printf '\n\033[1;34m==> %s\033[0m\n' "$*"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_linux() {
  [[ "$(uname -s)" == "Linux" ]] || die "This installer must be run on the Raspberry Pi, not macOS."
  [[ "${EUID}" -ne 0 ]] || die "Run this as your normal Pi user, not with sudo. The script invokes sudo when needed."
  command -v sudo >/dev/null 2>&1 || die "sudo is required."
}

version_at_least() {
  local actual="$1"
  local required="$2"
  [[ "$(printf '%s\n%s\n' "${required}" "${actual}" | sort -V | head -n1)" == "${required}" ]]
}

prompt_secret() {
  local prompt="$1"
  local target_name="$2"
  local value=""
  read -r -s -p "${prompt}: " value
  echo
  [[ -n "${value}" ]] || die "${prompt} cannot be empty."
  [[ "${value}" != *$'\n'* && "${value}" != *$'\r'* ]] || die "${prompt} cannot contain a newline."
  printf -v "${target_name}" '%s' "${value}"
}

systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

install_node() {
  if command -v node >/dev/null 2>&1; then
    local node_version
    node_version="$(node --version | sed 's/^v//')"
    if version_at_least "${node_version}" "20.19.0"; then
      info "Node.js ${node_version} is already suitable"
      return
    fi
  fi

  info "Installing Node.js 22"
  local setup_script
  setup_script="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/setup_22.x -o "${setup_script}"
  sudo -E bash "${setup_script}"
  rm -f "${setup_script}"
  sudo apt-get install -y nodejs
  version_at_least "$(node --version | sed 's/^v//')" "20.19.0" || die "Node.js 20.19 or newer is required."
}

install_tailscale() {
  if command -v tailscale >/dev/null 2>&1; then
    info "Tailscale is already installed"
    return
  fi

  info "Installing Tailscale"
  local install_script
  install_script="$(mktemp)"
  curl -fsSL https://tailscale.com/install.sh -o "${install_script}"
  sh "${install_script}"
  rm -f "${install_script}"
}

select_caddy_port() {
  local managed_port=""
  if sudo test -s "${CADDYFILE}" && sudo grep -q "Managed by ${V4_DIR}/deploy_pi.sh" "${CADDYFILE}"; then
    managed_port="$(sudo sed -n 's/^:\([0-9][0-9]*\) .*/\1/p' "${CADDYFILE}" | head -n1)"
  fi

  # Reuse our active listener on repeat runs. After a failed first attempt,
  # avoid a port already owned by another local application.
  if [[ "${managed_port}" == "${CADDY_PORT}" ]] && sudo systemctl is-active --quiet caddy; then
    CADDY_PORT="${managed_port}"
    return
  fi

  while sudo ss -H -ltn "sport = :${CADDY_PORT}" | grep -q .; do
    CADDY_PORT=$((CADDY_PORT + 1))
  done
}

write_configuration() {
  local admin_email="$1"
  local admin_password="$2"
  local openai_key="$3"
  local public_origin="$4"
  local app_tmp
  local openai_tmp

  app_tmp="$(mktemp)"
  openai_tmp="$(mktemp)"
  chmod 600 "${app_tmp}" "${openai_tmp}"

  {
    echo "V4_COOKIE_SECURE=true"
    echo "V4_CORS_ORIGINS=${public_origin}"
    echo "V4_DB_PATH=${V4_DIR}/data/capital_nerve.db"
    echo "V4_APP_DB_PATH=${V4_DIR}/data/capital_nerve_app.db"
    echo "V4_CATALOG_DIR=${V4_DIR}/microservices/catalog"
    echo "VALUES_SERVICE_ENV_PATH=${OPENAI_ENV}"
    echo "VALUES_SERVICE_PARSE_MAX_WORKERS=1"
    echo "VALUES_SERVICE_EXTRACTION_MAX_WORKERS=1"
    echo "MONITOR_POLL_INTERVAL_SECONDS=120"
    printf 'V4_ADMIN_EMAIL=%s\n' "$(systemd_quote "${admin_email}")"
    printf 'V4_ADMIN_PASSWORD=%s\n' "$(systemd_quote "${admin_password}")"
  } >"${app_tmp}"

  {
    echo "OPENAI_API_KEY=${openai_key}"
    echo "OPENAI_MODEL=gpt-4.1-mini"
    echo "OPENAI_PARSE_MODEL=gpt-4.1-mini"
  } >"${openai_tmp}"

  sudo install -d -m 750 -o root -g "${DEPLOY_GROUP}" "${ENV_DIR}"
  sudo install -m 640 -o root -g "${DEPLOY_GROUP}" "${app_tmp}" "${APP_ENV}"
  sudo install -m 640 -o root -g "${DEPLOY_GROUP}" "${openai_tmp}" "${OPENAI_ENV}"
  rm -f "${app_tmp}" "${openai_tmp}"
}

install_systemd_units() {
  local unit_tmp
  local target_tmp
  unit_tmp="$(mktemp)"
  target_tmp="$(mktemp)"

  cat >"${unit_tmp}" <<EOF
[Unit]
Description=CapitalNerve v4 %i service
Wants=network-online.target
After=network-online.target
PartOf=capital-nerve.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
EnvironmentFile=${APP_ENV}
ExecStart=${V4_DIR}/deploy/run_service.sh %i
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=capital-nerve.target
EOF

  cat >"${target_tmp}" <<EOF
[Unit]
Description=CapitalNerve v4 application
Wants=$(printf 'capital-nerve@%s.service ' "${SERVICES[@]}")
After=network-online.target

[Install]
WantedBy=multi-user.target
EOF

  sudo install -m 644 "${unit_tmp}" "${SYSTEMD_TEMPLATE}"
  sudo install -m 644 "${target_tmp}" "${SYSTEMD_TARGET}"
  rm -f "${unit_tmp}" "${target_tmp}"
  sudo systemctl daemon-reload
  sudo systemctl enable capital-nerve.target >/dev/null
}

install_caddy_config() {
  local caddy_tmp
  caddy_tmp="$(mktemp)"
  cat >"${caddy_tmp}" <<EOF
# Managed by ${V4_DIR}/deploy_pi.sh
:${CADDY_PORT} {
    bind 127.0.0.1
    encode zstd gzip

    handle_path /api/* {
        reverse_proxy 127.0.0.1:8010
    }

    handle {
        root * ${WEB_ROOT}
        try_files {path} /index.html
        file_server
    }

    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
    }
}
EOF

  if sudo test -s "${CADDYFILE}" && ! sudo grep -q "Managed by ${V4_DIR}/deploy_pi.sh" "${CADDYFILE}"; then
    local backup="${CADDYFILE}.before-capital-nerve.$(date +%Y%m%d%H%M%S)"
    sudo cp "${CADDYFILE}" "${backup}"
    echo "Saved the previous Caddy configuration as ${backup}"
  fi
  sudo install -m 644 "${caddy_tmp}" "${CADDYFILE}"
  rm -f "${caddy_tmp}"
  sudo caddy fmt --overwrite "${CADDYFILE}"
  sudo caddy validate --config "${CADDYFILE}"
  sudo systemctl enable --now caddy
  sudo systemctl reload caddy
}

wait_for_services() {
  info "Waiting for CapitalNerve services"
  local index
  for index in "${!SERVICES[@]}"; do
    local service="${SERVICES[$index]}"
    local port="${PORTS[$index]}"
    local ready=0
    for _ in $(seq 1 90); do
      if curl -fsS "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
        ready=1
        break
      fi
      sleep 1
    done
    if [[ "${ready}" -ne 1 ]]; then
      sudo journalctl -u "capital-nerve@${service}.service" -n 50 --no-pager
      die "${service} did not become healthy on port ${port}."
    fi
    echo "  ready: ${service} (${port})"
  done
}

remove_bootstrap_secret() {
  local cleaned
  cleaned="$(mktemp)"
  sudo awk '!/^V4_ADMIN_EMAIL=/ && !/^V4_ADMIN_PASSWORD=/' "${APP_ENV}" >"${cleaned}"
  sudo install -m 640 -o root -g "${DEPLOY_GROUP}" "${cleaned}" "${APP_ENV}"
  rm -f "${cleaned}"
}

main() {
  require_linux
  info "CapitalNerve v4 Raspberry Pi deployment"
  echo "Repository: ${REPO_DIR}"
  echo "Service user: ${DEPLOY_USER}"

  local admin_email
  local admin_password
  local admin_password_confirm
  local openai_key
  read -r -p "Initial administrator email: " admin_email
  [[ "${admin_email}" == *@*.* ]] || die "Enter a valid administrator email address."
  prompt_secret "Initial administrator password (minimum 12 characters)" admin_password
  [[ ${#admin_password} -ge 12 ]] || die "The administrator password must be at least 12 characters."
  prompt_secret "Confirm administrator password" admin_password_confirm
  [[ "${admin_password}" == "${admin_password_confirm}" ]] || die "The passwords do not match."
  prompt_secret "OpenAI API key" openai_key
  [[ "${openai_key}" != *'='* ]] || die "The OpenAI key contains an unexpected '=' character."

  info "Installing operating-system packages"
  sudo apt-get update
  sudo apt-get install -y curl git python3-venv python3-pip sqlite3 caddy rsync jq iproute2
  install_node
  install_tailscale
  select_caddy_port
  echo "Caddy will use private local port ${CADDY_PORT}."

  info "Connecting this Pi to Tailscale"
  sudo systemctl enable --now tailscaled
  local tailscale_state
  tailscale_state="$(sudo tailscale status --json 2>/dev/null | jq -r '.BackendState // empty' || true)"
  if [[ "${tailscale_state}" == "Running" ]]; then
    sudo tailscale set --hostname=capital-nerve
  else
    sudo tailscale up --hostname=capital-nerve
  fi
  local public_host
  public_host="$(sudo tailscale status --json | jq -r '.Self.DNSName // empty' | sed 's/\.$//')"
  [[ -n "${public_host}" ]] || die "Tailscale did not provide a DNS hostname. Ensure MagicDNS is enabled."
  local public_origin="https://${public_host}"
  echo "Public origin will be ${public_origin}"

  info "Installing Python dependencies"
  if [[ ! -x "${REPO_DIR}/.venv/bin/python" ]]; then
    python3 -m venv "${REPO_DIR}/.venv"
  fi
  "${REPO_DIR}/.venv/bin/pip" install --upgrade pip wheel
  local requirement
  for requirement in "${V4_DIR}/backend/requirements.txt" "${V4_DIR}"/microservices/*/requirements.txt; do
    "${REPO_DIR}/.venv/bin/pip" install -r "${requirement}"
  done

  info "Building the production frontend"
  npm --prefix "${V4_DIR}/frontend" ci
  npm --prefix "${V4_DIR}/frontend" run build
  sudo install -d -m 755 "${WEB_ROOT}"
  sudo rsync -a --delete "${V4_DIR}/frontend/dist/" "${WEB_ROOT}/"
  sudo find "${WEB_ROOT}" -type d -exec chmod 755 {} +
  sudo find "${WEB_ROOT}" -type f -exec chmod 644 {} +

  info "Writing protected production configuration"
  write_configuration "${admin_email}" "${admin_password}" "${openai_key}" "${public_origin}"
  chmod +x "${V4_DIR}/deploy/run_service.sh"
  install_systemd_units
  install_caddy_config

  info "Starting the application"
  sudo systemctl restart capital-nerve.target
  wait_for_services
  curl -fsS "http://127.0.0.1:${CADDY_PORT}/api/health" >/dev/null || die "Caddy API proxy health check failed."

  info "Publishing the site through Tailscale Funnel"
  sudo tailscale funnel --bg "${CADDY_PORT}"
  remove_bootstrap_secret

  info "Deployment complete"
  echo "CapitalNerve: ${public_origin}"
  echo "Application status: sudo systemctl status capital-nerve.target"
  echo "Service logs: sudo journalctl -u 'capital-nerve@*.service' -f"
  echo "Funnel status: tailscale funnel status"
  echo
  echo "The bootstrap administrator password has been removed from ${APP_ENV}."
}

main "$@"
