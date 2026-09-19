"""Widget-level tests for MonitorView zoom.

These need a QApplication, so the whole module is skipped when no Qt platform
plugin can be initialized (for example a headless box without offscreen Qt).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtWidgets import QApplication

    from MegaSerial.monitor import (
        MAX_FONT_POINT_SIZE, MIN_FONT_POINT_SIZE, MonitorView,
    )

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # noqa: BLE001 - no usable Qt platform in this environment
    raise unittest.SkipTest(f"Qt widgets unavailable: {exc}")


def _wheel(view: MonitorView, angle: int, ctrl: bool) -> None:
    modifiers = (Qt.KeyboardModifier.ControlModifier if ctrl
                 else Qt.KeyboardModifier.NoModifier)
    event = QWheelEvent(
        QPointF(10.0, 10.0), QPointF(10.0, 10.0), QPoint(0, 0), QPoint(0, angle),
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
    )
    _APP.sendEvent(view.edit.viewport(), event)


class MonitorViewZoomTests(unittest.TestCase):
    def setUp(self):
        self.view = MonitorView(font_point_size=12)
        self.addCleanup(self.view.deleteLater)

    def test_initial_and_explicit_font_sizes_are_clamped(self):
        self.assertEqual(self.view.font_point_size, 12)
        self.assertEqual(self.view.set_font_point_size(MAX_FONT_POINT_SIZE + 10),
                         MAX_FONT_POINT_SIZE)
        self.assertEqual(self.view.set_font_point_size(MIN_FONT_POINT_SIZE - 10),
                         MIN_FONT_POINT_SIZE)

    def test_ctrl_wheel_zooms_in_and_out(self):
        _wheel(self.view, 120, ctrl=True)
        self.assertEqual(self.view.font_point_size, 13)
        _wheel(self.view, -120, ctrl=True)
        self.assertEqual(self.view.font_point_size, 12)

    def test_plain_wheel_leaves_the_font_alone(self):
        _wheel(self.view, 120, ctrl=False)
        self.assertEqual(self.view.font_point_size, 12)

    def test_zoom_gestures_are_delegated_to_the_owner_when_set(self):
        seen = []
        view = MonitorView(font_point_size=12, on_zoom_requested=seen.append)
        self.addCleanup(view.deleteLater)

        _wheel(view, 120, ctrl=True)
        _wheel(view, -120, ctrl=True)

        # The owner decides the new size, so the view must not change it itself.
        self.assertEqual(seen, [1, -1])
        self.assertEqual(view.font_point_size, 12)

    def test_zoom_does_not_change_rendered_log_content(self):
        opts = {"show_ts": False, "show_delays": False, "show_dir": False,
                "show_linenum": False, "autoscroll": False,
                "colors": {"rx": "#1", "tx": "#2", "info": "#3"}}
        self.view.append_event({"type": "data", "dir": "rx", "data": b"hello"}, opts)
        before = self.view.plain_text()

        self.view.set_font_point_size(MAX_FONT_POINT_SIZE)

        self.assertEqual(self.view.plain_text(), before)


if __name__ == "__main__":
    unittest.main()
