#!/usr/bin/env bash
# Build a standalone, single-file MegaSerial executable that runs on any
# Debian-based Linux without installing Python, PyQt6 or pyserial.
#
# The result is written to ./dist/MegaSerial
set -euo pipefail
cd "$(dirname "$0")"

VENV=.buildvenv

# Create an isolated build venv that can still see the system PyQt6/pyserial.
if [[ ! -x "$VENV/bin/pyinstaller" ]]; then
    python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip pyinstaller
fi

"$VENV/bin/pyinstaller" \
    --noconfirm --clean --onefile \
    --name MegaSerial \
    --icon MegaSerial/resources/app_icon.png \
    --add-data "MegaSerial/resources/app_icon.png:MegaSerial/resources" \
    --add-data "MegaSerial/resources/about.md:MegaSerial/resources" \
    --add-data "MegaSerial/resources/app_config.json:MegaSerial/resources" \
    --hidden-import serial \
    --collect-submodules MegaSerial \
    megaserial_entry.py

echo
echo "Built: $(pwd)/dist/MegaSerial"
