#!/usr/bin/env bash
# Apply already-pulled CapitalNerve v4 code on the Raspberry Pi.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_ROOT="/var/www/capital-nerve"
TARGET="capital-nerve.target"

usage() {
  cat <<'EOF'
Usage: ./v4/update_pi.sh --backend | --frontend | --all

  --backend   Restart all CapitalNerve systemd services.
  --frontend  Install locked frontend dependencies, build the static site, and publish it.
  --all       Publish the frontend, then restart all CapitalNerve services.

Pull code first, if needed: git pull
EOF
}

[[ $# -eq 1 ]] || { usage >&2; exit 2; }

case "$1" in
  --backend) update_frontend=0; restart_backend=1 ;;
  --frontend) update_frontend=1; restart_backend=0 ;;
  --all) update_frontend=1; restart_backend=1 ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

[[ "$(uname -s)" == "Linux" ]] || {
  echo "This script must be run on the Raspberry Pi." >&2
  exit 1
}

if [[ "${update_frontend}" -eq 1 ]]; then
  echo "==> Building and publishing frontend"
  npm --prefix "${SCRIPT_DIR}/frontend" ci
  npm --prefix "${SCRIPT_DIR}/frontend" run build
  sudo install -d -m 755 "${WEB_ROOT}"
  sudo rsync -a --delete "${SCRIPT_DIR}/frontend/dist/" "${WEB_ROOT}/"
  sudo find "${WEB_ROOT}" -type d -exec chmod 755 {} +
  sudo find "${WEB_ROOT}" -type f -exec chmod 644 {} +
fi

if [[ "${restart_backend}" -eq 1 ]]; then
  echo "==> Restarting CapitalNerve services"
  sudo systemctl restart "${TARGET}"
  sudo systemctl --no-pager --full status "${TARGET}"
fi

echo "==> Update complete"
