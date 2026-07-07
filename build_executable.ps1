# Build a standalone, single-file MegaSerial.exe for Windows.
# Bundles Python, PyQt6, pyserial and pyqtgraph — no install required on target PCs.
#
# Output: .\dist\MegaSerial.exe
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Venv = ".buildvenv-win"
$Py = Join-Path $Venv "Scripts\python.exe"
$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"

if (-not (Test-Path $Py)) {
    python -m venv $Venv
    & $Py -m pip install --upgrade pip
    & $Py -m pip install pyinstaller pillow
    & $Py -m pip install -r requirements.txt
}

# Windows .exe icons must be .ico; generate one from the bundled PNG.
& $Py -m pip install pillow -q
& $Py scripts/make_app_icon_ico.py

& $PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name MegaSerial `
    --icon MegaSerial/resources/app_icon.ico `
    --add-data "MegaSerial/resources/app_icon.png;MegaSerial/resources" `
    --add-data "MegaSerial/resources/about.md;MegaSerial/resources" `
    --add-data "MegaSerial/resources/app_config.json;MegaSerial/resources" `
    --hidden-import serial `
    --collect-submodules MegaSerial `
    --collect-all pyqtgraph `
    megaserial_entry.py

Write-Host ""
Write-Host "Built: $((Get-Location).Path)\dist\MegaSerial.exe"
