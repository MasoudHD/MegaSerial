"""Per-user Windows file association for ``.msproj`` projects.

MegaSerial ships as a portable executable with no installer, so it never touches
the registry during normal startup. Association is an explicit action:

    MegaSerial.exe --register-file-association
    MegaSerial.exe --unregister-file-association

Everything is written under ``HKEY_CURRENT_USER\\Software\\Classes``, so no
administrator rights are needed and nothing is changed for other users.

The layout of the entries is computed by :func:`registry_entries`, which is pure
and therefore testable on any platform.
"""
from __future__ import annotations

import sys
from pathlib import Path

EXTENSION = ".msproj"
PROG_ID = "MegaSerial.Project"
FILE_TYPE_LABEL = "MegaSerial Project"
PACKAGE = "MegaSerial"

# Per-user class registrations live here; HKLM would require elevation.
CLASSES_ROOT = r"Software\Classes"
EXTENSION_KEY = rf"{CLASSES_ROOT}\{EXTENSION}"
PROG_ID_KEY = rf"{CLASSES_ROOT}\{PROG_ID}"
COMMAND_KEY = rf"{PROG_ID_KEY}\shell\open\command"
ICON_KEY = rf"{PROG_ID_KEY}\DefaultIcon"


class AssociationError(RuntimeError):
    """Raised when the association cannot be created or removed."""


def launch_command(executable: str | None = None, frozen: bool | None = None) -> str:
    """Command Windows runs for a double-clicked project.

    ``%1`` is quoted so paths containing spaces arrive as a single argument.
    """
    exe = executable or sys.executable
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        return f'"{exe}" "%1"'
    # Running from source: go through the package so imports resolve.
    return f'"{exe}" -m {PACKAGE} "%1"'


def icon_value(executable: str | None = None, frozen: bool | None = None) -> str | None:
    """Icon shown for project files, taken from the packaged executable."""
    exe = executable or sys.executable
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    return f'"{exe}",0' if frozen else None


def registry_entries(executable: str | None = None,
                     frozen: bool | None = None) -> list[tuple[str, str]]:
    """Return the ``(key_path, default_value)`` pairs the association needs."""
    entries = [
        (EXTENSION_KEY, PROG_ID),
        (PROG_ID_KEY, FILE_TYPE_LABEL),
        (COMMAND_KEY, launch_command(executable, frozen)),
    ]
    icon = icon_value(executable, frozen)
    if icon:
        entries.insert(2, (ICON_KEY, icon))
    return entries


def _winreg():
    if sys.platform != "win32":
        raise AssociationError(
            "File association is a Windows feature; nothing to do on this platform.")
    import winreg

    return winreg


def _notify_shell() -> None:
    """Ask Explorer to reload associations so the change is visible at once."""
    try:
        import ctypes

        # SHCNE_ASSOCCHANGED, SHCNF_IDLIST
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:  # noqa: BLE001 - cosmetic only; the keys are already written
        pass


def register(executable: str | None = None) -> str:
    """Associate ``.msproj`` with this executable for the current user."""
    winreg = _winreg()
    command = launch_command(executable)
    try:
        for key_path, value in registry_entries(executable):
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0,
                                    winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
    except OSError as exc:
        raise AssociationError(f"Could not write the association: {exc}") from exc
    _notify_shell()
    return command


def _delete_tree(winreg, root, key_path: str) -> None:
    try:
        with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(winreg, root, rf"{key_path}\{child}")
    except FileNotFoundError:
        return
    winreg.DeleteKey(root, key_path)


def unregister() -> None:
    """Remove the current user's ``.msproj`` association."""
    winreg = _winreg()
    root = winreg.HKEY_CURRENT_USER
    try:
        _delete_tree(winreg, root, PROG_ID_KEY)
        # Only drop the extension key if it still points at us, so an
        # association since set by another application is left alone.
        try:
            with winreg.OpenKey(root, EXTENSION_KEY, 0, winreg.KEY_READ) as key:
                current, _ = winreg.QueryValueEx(key, "")
        except FileNotFoundError:
            current = None
        if current == PROG_ID:
            _delete_tree(winreg, root, EXTENSION_KEY)
    except OSError as exc:
        raise AssociationError(f"Could not remove the association: {exc}") from exc
    _notify_shell()


def describe() -> str:
    """Human-readable summary of what registration would do."""
    exe = Path(sys.executable).name
    return (f"Associate {EXTENSION} with {exe} for the current user "
            f"(HKEY_CURRENT_USER\\{EXTENSION_KEY}).")
