"""Application icon and bundled resource paths."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon, QPixmap


def resource_path(*parts: str) -> Path:
    """Resolve a path to a file shipped inside the package (or PyInstaller bundle)."""
    if getattr(sys, "_MEIPASS", None):
        # PyInstaller --add-data places files under MegaSerial/ inside the bundle.
        base = Path(sys._MEIPASS) / "MegaSerial"
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def app_icon() -> QIcon:
    return QIcon(str(resource_path("resources", "app_icon.png")))


def app_logo_pixmap(size: int = 36) -> QPixmap:
    return app_icon().pixmap(size, size)
