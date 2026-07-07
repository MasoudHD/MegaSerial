"""Persist settings, saved shortcuts and sequences to ``~/.config/MegaSerial``."""
from __future__ import annotations

import json
import os
from pathlib import Path


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
    "line_mode": True,
    "send_format": "ASCII",
    "line_ending": "CRLF (\\r\\n)",
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


def load() -> dict:
    path = config_path()
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


def save(data: dict) -> None:
    path = config_path()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass
