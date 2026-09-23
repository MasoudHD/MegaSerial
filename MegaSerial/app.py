"""Application entry point."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import __app_name__, cli, file_association
from .icons import app_icon
from .main_window import MainWindow


def _run_association_command(register: bool) -> int:
    try:
        if register:
            command = file_association.register()
            print(f"Associated {file_association.EXTENSION} files with: {command}")
        else:
            file_association.unregister()
            print(f"Removed the {file_association.EXTENSION} file association.")
    except file_association.AssociationError as exc:
        print(f"{__app_name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = cli.build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    if args.register_file_association or args.unregister_file_association:
        return _run_association_command(args.register_file_association)

    project_path = None
    if args.project:
        try:
            project_path = cli.resolve_project_path(args.project)
        except cli.ProjectPathError as exc:
            print(f"{__app_name__}: {exc}", file=sys.stderr)
            return 2

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    # Windows appends " - {display name}" to the title bar; keep the title we set on the window.
    app.setApplicationDisplayName("")
    icon = app_icon()
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.showMaximized()
    if project_path:
        # Same code path as File > Open, so behavior cannot drift.
        window.open_project(str(project_path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
