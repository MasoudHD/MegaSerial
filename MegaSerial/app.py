"""Application entry point."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import __app_name__
from .icons import app_icon
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    # Windows appends " - {display name}" to the title bar; keep the title we set on the window.
    app.setApplicationDisplayName("")
    icon = app_icon()
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
