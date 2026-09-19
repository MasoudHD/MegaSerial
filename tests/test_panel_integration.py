"""Offscreen integration checks; no serial hardware or user config writes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from copy import deepcopy
from unittest.mock import patch
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from MegaSerial import config
from MegaSerial.main_window import MainWindow
from MegaSerial.panel_view import PanelLayoutDialog
from test_panel_model import workspace

_APP = QApplication.instance() or QApplication([])


class PanelIntegrationTests(unittest.TestCase):
    def setUp(self):
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        with patch('MegaSerial.main_window.config.load', return_value=deepcopy(config.DEFAULTS)):
            self.window = MainWindow()
        self.addCleanup(self.cleanup_window)
        self.window.panel_view.set_workspace(workspace())
        self.window.presentation_combo.setCurrentIndex(1)

    def cleanup_window(self):
        self.window.deleteLater()
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def text(self, ident):
        return self.window.panel_view.widgets[ident].monitor.plain_text()

    def test_fragmented_rx_title_unknown_and_tx(self):
        w = self.window
        w.on_data_received(b'@PAN')
        w._flush_rx_buffer()
        self.assertEqual(len(w.events), 0)
        w.on_data_received(b'EL:gps|Fix|OK\r\n@PANEL_TITLE:gps|Receiver\n')
        w.on_data_received(b'@PANEL:unknown|Missing\nordinary\n')
        w._append_data('tx', b'AT')
        self.assertIn('Fix|OK', self.text('gps'))
        self.assertNotIn('@PANEL:', self.text('gps'))
        self.assertEqual(w.panel_view.widgets['gps'].header.text(), 'Receiver')
        self.assertIn('Missing', self.text('general'))
        self.assertIn('ordinary', self.text('general'))
        self.assertIn('AT', self.text('general'))
        self.assertEqual(w.events[2]['panel_id'], 'unknown')
        self.assertEqual(w.events[0]['data'], b'@PANEL:gps|Fix|OK\r\n')
        before = list(w.events)
        w.presentation_combo.setCurrentIndex(0)
        self.assertIn('@PANEL:gps|Fix|OK', w.view1.plain_text())
        w.presentation_combo.setCurrentIndex(1)
        self.assertEqual(list(w.events), before)

    def test_binary_raw_mode_and_timeout_continuations_not_parsed(self):
        w = self.window
        w.on_data_received(b'ordinary partial')
        w._flush_rx_buffer()
        w.on_data_received(b'@PANEL:gps|not at line start\n@PANEL:gps|\x00\n')
        self.assertTrue(all('panel_id' not in e for e in w.events))
        w.linemode_check.setChecked(False)
        w.on_data_received(b'@PANEL:gps|raw\n')
        self.assertNotIn('panel_id', w.events[-1])

    def test_search_scope_and_shared_zoom(self):
        w = self.window
        w.on_data_received(b'@PANEL:gps|OK\n@PANEL:can|OK\nplain\n@PANEL:gps|ERROR\n')
        original = deepcopy(list(w.events))
        w.panel_view.workspace.scope = ['gps']
        w.filter_pattern.setText('ERROR')
        w.filter_check.setChecked(True)
        self.assertNotIn('OK', self.text('gps'))
        self.assertIn('ERROR', self.text('gps'))
        self.assertIn('OK', self.text('can'))
        self.assertIn('plain', self.text('general'))
        w.panel_view.workspace.scope = None
        w._rerender_all()
        self.assertEqual(self.text('can'), '')
        self.assertEqual(self.text('general'), '')
        w.zoom_monitor(2)
        self.assertEqual(w.panel_view.widgets['gps'].monitor.font_point_size, w.view1.font_point_size)
        self.assertEqual(list(w.events), original)

    def test_layout_dialog_and_title_menu(self):
        dialog = PanelLayoutDialog(self.window.panel_view.workspace)
        self.addCleanup(dialog.deleteLater)
        dialog.columns.setValue(4)
        dialog.rows.setValue(3)
        for i, count in enumerate([4, 2, 3]):
            dialog.counts.cellWidget(i, 0).setValue(count)
        self.assertEqual(dialog.table.rowCount(), 9)
        dialog.accept()
        self.assertEqual(dialog.result_workspace.row_counts, [4, 2, 3])
        self.window.panel_view.set_workspace(dialog.result_workspace)
        self.assertEqual(len(self.window.panel_view.widgets), 9)
        self.assertEqual(len(self.window.panel_view.scope_menu.actions()), 10)

    def test_bounded_retention_clear_and_replay(self):
        from collections import deque
        w = self.window
        w.events = deque(maxlen=2)
        w.on_data_received(b'@PANEL:gps|first\n@PANEL:gps|second\n@PANEL:can|third\n')
        self.assertNotIn('first', self.text('gps'))
        self.assertIn('second', self.text('gps'))
        w.clear_monitor()
        self.assertEqual(self.text('gps'), '')
        self.assertEqual(len(w.events), 0)

    def test_project_window_roundtrip_and_legacy_reset(self):
        import tempfile
        from pathlib import Path
        from MegaSerial import project
        w = self.window
        w.panel_view.workspace.scope = ['gps']
        w.on_data_received('@PANEL_TITLE:gps|گیرنده\n@PANEL:gps|موقع\n'.encode())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'panel.msproj'
            with patch('MegaSerial.main_window.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                w.save_project()
            state = w.panel_view.workspace.to_dict()
            self.assertNotIn('panel_view', w._collect_settings())
            w.panel_view.set_workspace(workspace())
            w.presentation_combo.setCurrentIndex(0)
            w.clear_monitor()
            self.assertTrue(w.open_project(str(path)))
            self.assertEqual(w.presentation_combo.currentIndex(), 1)
            self.assertEqual(w.panel_view.workspace.to_dict(), state)
            self.assertIn('موقع', self.text('gps'))
            legacy = Path(folder) / 'legacy.msproj'
            project.save_project(legacy, project.collect_project_data(
                project_name='Old', settings={}, events=[{'type': 'data', 'dir': 'rx',
                                                         'ts': w.events[0]['ts'], 'data': b'legacy'}]))
            self.assertTrue(w.open_project(str(legacy)))
            self.assertEqual(w.presentation_combo.currentIndex(), 0)
            self.assertEqual(w.panel_view.workspace.row_counts, [1])
            w.presentation_combo.setCurrentIndex(1)
            self.assertIn('legacy', self.text('general'))

    def test_global_display_options_theme_and_independent_scrollbars(self):
        w = self.window
        w.on_data_received(b'@PANEL:gps|first\n@PANEL:can|second\n@PANEL:gps|third\n')
        w.ts_check.setChecked(False)
        w.delay_check.setChecked(True)
        self.assertIn(' ms', self.text('gps'))
        w.delay_check.setChecked(False)
        self.assertNotIn(' ms', self.text('gps'))
        w.ts_check.setChecked(True)
        self.assertIn(w.events[0]['ts'].strftime('%H:%M:%S'), self.text('gps'))
        self.assertIsNot(w.panel_view.widgets['gps'].monitor.edit.verticalScrollBar(),
                         w.panel_view.widgets['can'].monitor.edit.verticalScrollBar())
        font_size = w.zoom_monitor(1)
        w._apply_theme('light')
        self.assertEqual(w.panel_view.widgets['gps'].monitor.font_point_size, font_size)
        self.assertIn('first', self.text('gps'))

    def test_rapid_rx_and_multiline_retention(self):
        from collections import deque
        w = self.window
        w.events = deque(maxlen=30)
        w.on_data_received(b''.join(f'@PANEL:{"gps" if i % 2 else "can"}|value={i}\n'.encode()
                                   for i in range(300)))
        self.assertEqual(len(w.events), 30)
        self.assertNotIn('value=269', self.text('gps'))
        self.assertIn('value=299', self.text('gps'))
        self.assertEqual(len(w.panel_view.rendered_blocks), 30)
        before = {ident: widget.monitor.plain_text() for ident, widget in w.panel_view.widgets.items()}
        w._rerender_all()
        after = {ident: widget.monitor.plain_text() for ident, widget in w.panel_view.widgets.items()}
        self.assertEqual(before, after)
        w.clear_monitor()
        w.events = deque(maxlen=2)
        w._append_data('tx', b'one\ntwo\nthree')
        w._append_data('tx', b'keep')
        w._append_data('tx', b'last')
        self.assertNotIn('three', self.text('general'))
        self.assertIn('keep', self.text('general'))

    def test_panel_csv_uses_scoped_selection_and_normal_header_unchanged(self):
        import csv
        import tempfile
        from pathlib import Path
        from MegaSerial.monitor import CSV_ENCODING, CSV_COLUMNS
        w = self.window
        w.on_data_received(b'@PANEL:gps|OK\n@PANEL:can|OK\n@PANEL:gps|ERROR\n')
        w.panel_view.workspace.scope = ['gps']
        w.filter_pattern.setText('ERROR')
        w.filter_check.setChecked(True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.csv'
            with patch('MegaSerial.main_window.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                w.export_log_csv()
                with path.open(encoding=CSV_ENCODING) as fh:
                    rows = list(csv.DictReader(fh))
                self.assertEqual([r['panel_id'] for r in rows], ['can', 'gps'])
                w.presentation_combo.setCurrentIndex(0)
                w.export_log_csv()
                with path.open(encoding=CSV_ENCODING) as fh:
                    self.assertEqual(next(csv.reader(fh)), CSV_COLUMNS)
