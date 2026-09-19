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
        w.on_data_received(b'EL:12|Fix|OK\r\n@PANEL_TITLE:12|Receiver\n')
        w.on_data_received(b'@PANEL:unknown|Missing\nordinary\n')
        w._append_data('tx', b'AT')
        self.assertIn('Fix|OK', self.text('12'))
        self.assertNotIn('@PANEL:', self.text('12'))
        self.assertEqual(w.panel_view.widgets['12'].header.text(), '12 — Receiver')
        self.assertIn('Missing', self.text('11'))
        self.assertIn('ordinary', self.text('11'))
        self.assertIn('AT', self.text('11'))
        self.assertEqual(w.events[2]['panel_id'], 'unknown')
        self.assertEqual(w.events[0]['data'], b'@PANEL:12|Fix|OK\r\n')
        before = list(w.events)
        w.presentation_combo.setCurrentIndex(0)
        self.assertIn('@PANEL:12|Fix|OK', w.view1.plain_text())
        w.presentation_combo.setCurrentIndex(1)
        self.assertEqual(list(w.events), before)

    def test_binary_raw_mode_and_timeout_continuations_not_parsed(self):
        w = self.window
        w.on_data_received(b'ordinary partial')
        w._flush_rx_buffer()
        w.on_data_received(b'@PANEL:12|not at line start\n@PANEL:12|\x00\n')
        self.assertTrue(all('panel_id' not in e for e in w.events))
        w.linemode_check.setChecked(False)
        w.on_data_received(b'@PANEL:12|raw\n')
        self.assertNotIn('panel_id', w.events[-1])

    def test_search_scope_and_shared_zoom(self):
        w = self.window
        w.on_data_received(b'@PANEL:12|OK\n@PANEL:21|OK\nplain\n@PANEL:12|ERROR\n')
        original = deepcopy(list(w.events))
        w.panel_view.workspace.scope = ['12']
        w.filter_pattern.setText('ERROR')
        w.filter_check.setChecked(True)
        self.assertNotIn('OK', self.text('12'))
        self.assertIn('ERROR', self.text('12'))
        self.assertIn('OK', self.text('21'))
        self.assertIn('plain', self.text('11'))
        w.panel_view.workspace.scope = None
        w._rerender_all()
        self.assertEqual(self.text('21'), '')
        self.assertEqual(self.text('11'), '')
        w.zoom_monitor(2)
        self.assertEqual(w.panel_view.widgets['12'].monitor.font_point_size, w.view1.font_point_size)
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
        w.on_data_received(b'@PANEL:12|first\n@PANEL:12|second\n@PANEL:21|third\n')
        self.assertNotIn('first', self.text('12'))
        self.assertIn('second', self.text('12'))
        w.clear_monitor()
        self.assertEqual(self.text('12'), '')
        self.assertEqual(len(w.events), 0)

    def test_project_window_roundtrip_and_legacy_reset(self):
        import tempfile
        from pathlib import Path
        from MegaSerial import project
        w = self.window
        w.panel_view.workspace.scope = ['12']
        w.on_data_received('@PANEL_TITLE:12|گیرنده\n@PANEL:12|موقع\n'.encode())
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
            self.assertIn('موقع', self.text('12'))
            legacy = Path(folder) / 'legacy.msproj'
            project.save_project(legacy, project.collect_project_data(
                project_name='Old', settings={}, events=[{'type': 'data', 'dir': 'rx',
                                                         'ts': w.events[0]['ts'], 'data': b'legacy'}]))
            self.assertTrue(w.open_project(str(legacy)))
            self.assertEqual(w.presentation_combo.currentIndex(), 0)
            self.assertEqual(w.panel_view.workspace.row_counts, [1])
            w.presentation_combo.setCurrentIndex(1)
            self.assertIn('legacy', self.text('11'))

    def test_global_display_options_theme_and_independent_scrollbars(self):
        w = self.window
        w.on_data_received(b'@PANEL:12|first\n@PANEL:21|second\n@PANEL:12|third\n')
        w.ts_check.setChecked(False)
        w.delay_check.setChecked(True)
        self.assertIn(' ms', self.text('12'))
        w.delay_check.setChecked(False)
        self.assertNotIn(' ms', self.text('12'))
        w.ts_check.setChecked(True)
        self.assertIn(w.events[0]['ts'].strftime('%H:%M:%S'), self.text('12'))
        self.assertIsNot(w.panel_view.widgets['12'].monitor.edit.verticalScrollBar(),
                         w.panel_view.widgets['21'].monitor.edit.verticalScrollBar())
        font_size = w.zoom_monitor(1)
        w._apply_theme('light')
        self.assertEqual(w.panel_view.widgets['12'].monitor.font_point_size, font_size)
        self.assertIn('first', self.text('12'))

    def test_rapid_rx_and_multiline_retention(self):
        from collections import deque
        w = self.window
        w.events = deque(maxlen=30)
        w.on_data_received(b''.join(f'@PANEL:{"12" if i % 2 else "21"}|value={i}\n'.encode()
                                   for i in range(300)))
        self.assertEqual(len(w.events), 30)
        self.assertNotIn('value=269', self.text('12'))
        self.assertIn('value=299', self.text('12'))
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
        self.assertNotIn('three', self.text('11'))
        self.assertIn('keep', self.text('11'))

    def test_panel_csv_uses_scoped_selection_and_normal_header_unchanged(self):
        import csv
        import tempfile
        from pathlib import Path
        from MegaSerial.monitor import CSV_ENCODING, CSV_COLUMNS
        w = self.window
        w.on_data_received(b'@PANEL:12|OK\n@PANEL:21|OK\n@PANEL:12|ERROR\n')
        w.panel_view.workspace.scope = ['12']
        w.filter_pattern.setText('ERROR')
        w.filter_check.setChecked(True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.csv'
            with patch('MegaSerial.main_window.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                w.export_log_csv()
                with path.open(encoding=CSV_ENCODING) as fh:
                    rows = list(csv.DictReader(fh))
                self.assertEqual([r['panel_id'] for r in rows], ['21', '12'])
                w.presentation_combo.setCurrentIndex(0)
                w.export_log_csv()
                with path.open(encoding=CSV_ENCODING) as fh:
                    self.assertEqual(next(csv.reader(fh)), CSV_COLUMNS)

    def test_created_cells_receive_position_ids_without_title_setup(self):
        from MegaSerial.panel_model import PanelWorkspace
        from PyQt6.QtCore import Qt
        w = self.window
        initial = PanelWorkspace()
        initial.active = True
        dialog = PanelLayoutDialog(initial)
        self.addCleanup(dialog.deleteLater)
        dialog.columns.setValue(3)
        dialog.rows.setValue(3)
        for row, count in enumerate([3, 1, 2]):
            dialog.counts.cellWidget(row, 0).setValue(count)
        self.assertEqual(dialog.table.item(5, 1).text(), '32')
        self.assertFalse(dialog.table.item(5, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        # A message received before creating its cell is replayed into that cell.
        w.on_data_received(b'@PANEL:32|before creation\n')
        dialog.accept()
        w.panel_view.set_workspace(dialog.result_workspace)
        w.on_data_received(b'@PANEL:11|first cell\n@PANEL:32|after creation\n')
        self.assertIn('before creation', self.text('32'))
        self.assertIn('after creation', self.text('32'))
        self.assertIn('first cell', self.text('11'))
        self.assertEqual(w.panel_view.widgets['32'].header.text(), '32 — Panel 32')
        w.on_data_received(b'@PANEL_TITLE:32|GPS Receiver\n@PANEL:32|after title\n')
        self.assertEqual(w.panel_view.widgets['32'].header.text(), '32 — GPS Receiver')
        self.assertIn('after title', self.text('32'))
        # Editing row 1 must not move row 3's title or routing.
        updated = PanelLayoutDialog(w.panel_view.workspace)
        self.addCleanup(updated.deleteLater)
        updated.counts.cellWidget(0, 0).setValue(1)
        updated.accept()
        w.panel_view.set_workspace(updated.result_workspace)
        self.assertEqual(w.panel_view.widgets['32'].header.text(), '32 — GPS Receiver')
        self.assertIn('after creation', self.text('32'))
