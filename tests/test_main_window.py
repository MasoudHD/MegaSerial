"""Window-level tests for project identity and the window title.

Needs a QApplication, so the module is skipped when Qt cannot be initialized.
The HOME override keeps the real user config untouched.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_CONFIG_HOME = tempfile.mkdtemp(prefix="megaserial-test-home-")
os.environ["HOME"] = _CONFIG_HOME
os.environ["XDG_CONFIG_HOME"] = str(Path(_CONFIG_HOME) / ".config")

try:
    from PyQt6.QtWidgets import QApplication

    from MegaSerial import __app_name__, project as project_io
    from MegaSerial.main_window import BASE_WINDOW_TITLE, MainWindow, window_title

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # noqa: BLE001 - no usable Qt platform in this environment
    raise unittest.SkipTest(f"Qt widgets unavailable: {exc}")


class WindowTitleTests(unittest.TestCase):
    def test_no_project_title_just_identifies_the_app(self):
        self.assertEqual(window_title(None), BASE_WINDOW_TITLE)
        self.assertEqual(window_title(""), BASE_WINDOW_TITLE)
        self.assertIn(__app_name__, BASE_WINDOW_TITLE)

    def test_title_shows_the_project_file_name_not_the_whole_path(self):
        title = window_title("/home/me/projects/EC200_Test.msproj")

        self.assertIn("EC200_Test.msproj", title)
        self.assertIn(__app_name__, title)
        self.assertNotIn("/home/me/projects", title)

    def test_title_handles_unicode_and_spaces_in_the_file_name(self):
        self.assertIn("مودم تست.msproj", window_title("/tmp/a b/مودم تست.msproj"))


class ActiveProjectTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.directory = tempfile.mkdtemp()

    def _write_project(self, name: str) -> Path:
        path = Path(self.directory) / name
        project_io.save_project(path, project_io.collect_project_data(
            project_name="Demo", settings={}, events=[]))
        return path

    def test_a_fresh_window_has_no_active_project(self):
        self.assertIsNone(self.window._project_path)
        self.assertEqual(self.window.windowTitle(), BASE_WINDOW_TITLE)

    def test_setting_the_active_project_updates_the_title_immediately(self):
        path = self._write_project("EC200_Test.msproj")

        self.window._set_project_path(path)

        self.assertEqual(self.window._project_path, str(path))
        self.assertIn("EC200_Test.msproj", self.window.windowTitle())

    def test_clearing_the_active_project_restores_the_plain_title(self):
        self.window._set_project_path(self._write_project("x.msproj"))

        self.window._set_project_path(None)

        self.assertIsNone(self.window._project_path)
        self.assertEqual(self.window.windowTitle(), BASE_WINDOW_TITLE)

    def test_the_title_ignores_the_project_name_stored_in_config(self):
        # A stale name in the settings must never stand in for an open file.
        self.window.cfg["project_name"] = "Stale name from an old session"
        self.window.project_name_edit.setText("Stale name from an old session")

        self.assertEqual(self.window.windowTitle(), BASE_WINDOW_TITLE)


if __name__ == "__main__":
    unittest.main()
