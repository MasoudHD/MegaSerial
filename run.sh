#!/usr/bin/env bash
# Launch MegaSerial. Uses the system Python (PyQt6 + pyserial are installed
# system-wide on this machine).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m MegaSerial "$@"
