"""Persist settings, saved shortcuts and sequences to ``~/.config/MegaSerial``."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time


_LOCK_TIMEOUT_S = 2.0
_LOCK_POLL_S = 0.05


class _ConfigLock:
    """Cross-process advisory lock for a config path.

    Linux and other POSIX platforms use ``fcntl.flock``. Windows uses a
    one-byte ``msvcrt.locking`` lock. The companion lock file is intentionally
    retained; the operating-system lock is released when its file handle closes
    or the process exits.
    """

    def __init__(self, path: Path, timeout_s: float = _LOCK_TIMEOUT_S):
        self._path = path.with_name(f"{path.name}.lock")
        self._timeout_s = timeout_s
        self._fh = None

    def __enter__(self) -> "_ConfigLock":
        self._fh = open(self._path, "a+b")
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(b"\0")
            self._fh.flush()

        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                self._acquire_once()
                return self
            except OSError as exc:
                if not self._is_contended(exc) or time.monotonic() >= deadline:
                    self._close()
                    raise
                time.sleep(_LOCK_POLL_S)

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        try:
            if self._fh is not None:
                self._release_once()
        finally:
            self._close()

    @staticmethod
    def _is_contended(exc: OSError) -> bool:
        return exc.errno in (11, 13) or getattr(exc, "winerror", None) in (32, 33)

    def _acquire_once(self) -> None:
        if os.name == "nt":
            import msvcrt

            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_once(self) -> None:
        if os.name == "nt":
            import msvcrt

            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)

    def _close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    d = Path(base) / "MegaSerial"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


DEFAULTS = {
    "theme": "system",              # system | dark | light
    "show_timestamps": True,
    "show_delays": False,
    "show_direction": True,
    "autoscroll": True,
    "show_line_numbers": False,
    "monitor_font_point_size": 11,
    "line_mode": True,
    "send_format": "ASCII",
    "line_ending": "CRLF (\\r\\n)",
    "line_ending_custom_suffix": "",
    "clear_after_send": False,
    "echo_tx": True,
    "last_port": "",
    "baudrate": 115200,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "rtscts": False,
    "xonxoff": False,
    "auto_reconnect": True,
    "shortcuts": [],                # [{name, data, fmt, line_ending}]
    "history": [],                  # [{ts, text, fmt, line_ending}] manual sends
    "sequence": [],                 # [Step.to_dict(), ...]
    "sequence_loop": False,
    "sequence_loop_delay_ms": 0,
    "sequence_groups": [],          # [{name, steps: [Step.to_dict(), ...]}]
    "group_delay_ms": 0,
    "group_loop": False,
    "project_name": "",
    # Monitor views
    "split_view": False,
    "view1_format": "ASCII",
    "view1_bytes_per_row": 16,
    "view2_format": "HEX",
    "view2_bytes_per_row": 16,
    # Regex filter
    "filter_enabled": False,
    "filter_pattern": "",
    "filter_direction": "all",       # all | rx | tx
    "filter_case_insensitive": False,
    # Live graph
    "graph_view": False,
    "graph_mode": "auto",
    "graph_max_points": 1000,
    "graph_rx_only": True,
    "graph_autoscroll": True,
}


def _load_path(path: Path) -> dict:
    data = dict(DEFAULTS)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                data.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return data


def load() -> dict:
    return _load_path(config_path())


def _changed_keys(snapshot: dict, data: dict) -> set[str]:
    return {
        key
        for key in snapshot.keys() | data.keys()
        if key not in snapshot or key not in data or snapshot[key] != data[key]
    }


def _atomic_write(path: Path, data: dict) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def save(data: dict, *, snapshot: dict | None = None) -> None:
    """Persist config, merging only keys changed since *snapshot* when given."""
    path = config_path()
    try:
        with _ConfigLock(path):
            if snapshot is None:
                merged = data
            else:
                merged = _load_path(path)
                for key in _changed_keys(snapshot, data):
                    if key in data:
                        merged[key] = data[key]
                    else:
                        merged.pop(key, None)
            _atomic_write(path, merged)
    except OSError:
        pass
