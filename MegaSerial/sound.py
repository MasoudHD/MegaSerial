"""Play a short notification sound without blocking the UI."""
from __future__ import annotations

import shutil
import subprocess
import sys

_FREEDESKTOP = "/usr/share/sounds/freedesktop/stereo/complete.oga"


def _play_windows() -> bool:
    try:
        import winsound

        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        return True
    except Exception:  # noqa: BLE001
        return False


def _linux_candidates() -> list[list[str]]:
    cmds: list[list[str]] = []
    if shutil.which("canberra-gtk-play"):
        cmds.append(["canberra-gtk-play", "-i", "complete"])
    if shutil.which("paplay"):
        cmds.append(["paplay", _FREEDESKTOP])
    if shutil.which("pw-play"):
        cmds.append(["pw-play", _FREEDESKTOP])
    return cmds


def _play_linux() -> bool:
    for argv in _linux_candidates():
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _play_qt_beep() -> None:
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.beep()
    except Exception:  # noqa: BLE001
        pass


def play_notification() -> None:
    """Fire-and-forget notification sound."""
    if sys.platform == "win32":
        if _play_windows():
            return
    elif sys.platform != "darwin" and _play_linux():
        return

    _play_qt_beep()
