"""Save and load full project files (sequences, groups, settings, logs)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .panel_model import migrate_panel_project

FORMAT_VERSION = 1


def _event_to_dict(ev: dict) -> dict:
    out = dict(ev)
    if isinstance(out.get("ts"), datetime):
        out["ts"] = out["ts"].isoformat()
    if out.get("type") == "data" and isinstance(out.get("data"), bytes):
        out["data"] = out["data"].hex()
        out["data_encoding"] = "hex"
    return out


def _event_from_dict(d: dict) -> dict:
    ev = dict(d)
    ts = ev.get("ts")
    if isinstance(ts, str):
        try:
            ev["ts"] = datetime.fromisoformat(ts)
        except ValueError:
            ev["ts"] = datetime.now()
    if ev.get("type") == "data" and ev.get("data_encoding") == "hex":
        ev["data"] = bytes.fromhex(ev["data"])
        del ev["data_encoding"]
    return ev


def collect_project_data(
    *,
    project_name: str,
    settings: dict,
    events: list[dict],
    panel_view: dict | None = None,
) -> dict:
    """Build a serializable project document from live app state."""
    return {
        **({"panel_view": panel_view} if panel_view is not None else {}),
        "format_version": FORMAT_VERSION,
        "project_name": project_name,
        "settings": settings,
        "events": [_event_to_dict(ev) for ev in events],
    }


def save_project(path: str | Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_project(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("Project file is not a valid JSON object.")
    version = raw.get("format_version", 1)
    if version > FORMAT_VERSION:
        raise ValueError(f"Unsupported project format version {version}.")

    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    events = [_event_from_dict(ev) for ev in raw.get("events", []) if isinstance(ev, dict)]

    panel_state, events = migrate_panel_project(raw.get("panel_view"), events)

    return {
        "panel_view": panel_state,
        "project_name": raw.get("project_name", "") or "",
        "settings": settings,
        "events": events,
    }
