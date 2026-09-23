"""Command-line parsing for MegaSerial.

Kept free of Qt so argument handling and project-path validation stay testable
without a display.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import __app_name__, __version__

# Extensions the File > Open dialog offers by name.
PROJECT_SUFFIXES = (".msproj", ".json")


class ProjectPathError(ValueError):
    """Raised when a project path given on the command line cannot be used."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description=f"{__app_name__} v{__version__} — serial monitor for embedded work.",
    )
    parser.add_argument(
        "project", nargs="?",
        help="MegaSerial project (.msproj) to open on startup.",
    )
    parser.add_argument(
        "--register-file-association", action="store_true",
        help="Associate .msproj files with this executable for the current user.",
    )
    parser.add_argument(
        "--unregister-file-association", action="store_true",
        help="Remove the current user's .msproj file association.",
    )
    return parser


def resolve_project_path(raw: str) -> Path:
    """Validate a project path from the command line.

    Handles quoted paths containing spaces and non-ASCII characters, because
    Windows passes the clicked file through verbatim.
    """
    text = (raw or "").strip()
    if not text:
        raise ProjectPathError("No project file given.")
    path = Path(text).expanduser()
    if not path.exists():
        raise ProjectPathError(f"No such file: {path}")
    if not path.is_file():
        raise ProjectPathError(f"Not a file: {path}")
    if path.suffix.lower() not in PROJECT_SUFFIXES:
        supported = ", ".join(PROJECT_SUFFIXES)
        raise ProjectPathError(
            f"{path.name} is not a MegaSerial project (expected {supported}).")
    return path.resolve()
