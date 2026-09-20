"""Protocol selection, preview and project round trips through the real UI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import csv
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from MegaSerial import config, project
from MegaSerial.main_window import MainWindow
from MegaSerial.panel_model import PanelWorkspace
from MegaSerial.protocol_profiles import preset, save_profile, load_profile
from MegaSerial.protocol_dialog import ProtocolDialog
from MegaSerial.monitor import write_events_csv, CSV_ENCODING

_APP = QApplication.instance() or QApplication([])


class ProtocolIntegrationTests(unittest.TestCase):
    def setUp(self):
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        with patch('MegaSerial.main_window.config.load', return_value=deepcopy(config.DEFAULTS)):
            self.w = MainWindow()
        self.w.presentation_combo.setCurrentIndex(1)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.w.deleteLater()
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def select(self, profile):
        w = self.w
        w.panel_view.set_workspace(PanelWorkspace({'active': True, 'max_columns': 4,
                                                   'row_counts': [4, 4, 4, 4],
                                                   'protocol_profile': profile}))

    def text(self, ident):
        return self.w.panel_view.widgets[ident].monitor.plain_text()

    def test_preset_dialog_creates_layout_and_routes_without_line_mode(self):
        def choose(dialog):
            dialog.kind.setCurrentIndex(dialog.kind.findData('zmonitor'))
            dialog.accept()
            return 1
        with patch.object(ProtocolDialog, 'exec', choose):
            self.w._configure_protocol()
        self.assertEqual(self.w.panel_view.workspace.row_counts, [4, 4, 4, 4])
        self.assertFalse(self.w.linemode_check.isEnabled())
        with patch.object(self.w.rx_monitor, 'feed') as feed:
            self.w.on_data_received(b'\xc8\xd2Hello\xfa')
        feed.assert_called_once_with(b'\xc8\xd2Hello\xfa')
        self.assertIn('Hello', self.text('32'))
        self.assertEqual(self.w.events[-1]['data'], b'\xc8\xd2Hello\xfa')
        self.assertEqual(self.w.events[-1]['device_channel'], '9')

    def test_title_style_ansi_filter_and_unknown_data(self):
        self.select(preset('zmonitor'))
        w = self.w
        w.on_data_received(b'\xc8\xd2#TITLE_STYLE:title=GPS;color=255,0,0;bg=black\xfa')
        self.assertEqual(w.panel_view.widgets['32'].header.text(), '32 — GPS')
        self.assertIn('#ff0000', w.panel_view.widgets['32'].header.styleSheet())
        self.assertEqual(self.text('32'), '')
        w.on_data_received(b'\xc8\xd2\x1b[31mERROR\x1b[0m\xfa')
        self.assertIn('ERROR', self.text('32'))
        self.assertNotIn('[31m', self.text('32'))
        w.filter_pattern.setText('^ERROR$')
        w.filter_check.setChecked(True)
        self.assertIn('ERROR', self.text('32'))
        w.filter_check.setChecked(False)
        w.on_data_received(b'unframed data')
        self.assertIn('unframed data', self.text('11'))
        state = w.panel_view.workspace.to_dict()
        state['protocol_profile']['mapping'] = {}
        w.panel_view.set_workspace(PanelWorkspace(state))
        w.on_data_received(b'\xc8\xd2unmapped\xfa')
        self.assertIn('unmapped', self.text('11'))
        self.assertEqual(w.events[-1]['device_channel'], '9')
        self.assertIn('Unmapped', w.events[-1]['protocol_diagnostic'])

    def test_partial_switch_clear_and_disconnect_preserve_or_reset_as_expected(self):
        self.select(preset('zmonitor'))
        w = self.w
        w.on_data_received(b'\xc8\xd2unfinished')
        self.assertEqual(len(w.events), 0)
        state = w.panel_view.workspace.to_dict()
        state['protocol_profile'] = preset()
        w.panel_view.set_workspace(PanelWorkspace(state))
        self.assertEqual(w.events[-1]['data'], b'\xc8\xd2unfinished')
        self.assertTrue(w.linemode_check.isEnabled())
        self.select(preset('zmonitor'))
        w.on_data_received(b'\xc8\xd2disconnect')
        w.on_serial_closed()
        self.assertEqual(w.events[-1]['data'], b'\xc8\xd2disconnect')
        w.on_data_received(b'\xc8\xd2clear')
        w.clear_monitor()
        w.on_data_received(b'\xc8\xd2new\xfa')
        self.assertEqual(len(w.events), 1)
        self.assertIn('new', self.text('32'))

    def test_preview_import_export_and_cancel_do_not_touch_session(self):
        w = self.w
        dialog = ProtocolDialog(preset(), {'11': 'General'}, lambda: b'\xc8\xd2OK\xfa')
        self.addCleanup(dialog.deleteLater)
        dialog.kind.setCurrentIndex(dialog.kind.findData('zmonitor'))
        dialog.use_latest()
        dialog.test_packet()
        self.assertIn('Channel: 9', dialog.result.toPlainText())
        self.assertIn('Destination: 32', dialog.result.toPlainText())
        dialog.sample.setPlainText('C8 D2 4F')
        dialog.test_packet()
        self.assertIn('Incomplete packet', dialog.result.toPlainText())
        dialog.reject()
        self.assertEqual(len(w.events), 0)
        self.assertEqual(w.panel_view.workspace.protocol_profile['kind'], 'megaserial')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            save_profile(path, dialog.profile())
            dialog.populate(load_profile(path))
            self.assertEqual(dialog.profile(), load_profile(path))

    def test_project_and_csv_roundtrip_raw_channel_profile_styles(self):
        self.select(preset('zmonitor'))
        w = self.w
        w.on_data_received(b'\xc8\xd2#TITLE:GPS\xfa\xc8\xd2#TITLE_COLOR:red\xfa')
        w.on_data_received(b'\xc8\xd2\x1b[32mHello, "GPS"\nnext\x1b[0m\xfa')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.msproj'
            project.save_project(path, project.collect_project_data(
                project_name='zMonitor', settings={}, events=list(w.events),
                panel_view=w.panel_view.workspace.to_dict()))
            original = deepcopy(list(w.events))
            w.clear_monitor()
            self.assertTrue(w.open_project(str(path)))
            self.assertEqual(w.panel_view.workspace.protocol_profile, preset('zmonitor'))
            self.assertEqual(list(w.events), original)
            self.assertIn('#ff0000', w.panel_view.widgets['32'].header.styleSheet())
            self.assertIn('Hello, "GPS"', self.text('32'))
            csv_path = Path(folder) / 'session.csv'
            write_events_csv(csv_path, w._panel_filtered_events(), w.panel_view.workspace.titles())
            with csv_path.open(encoding=CSV_ENCODING, newline='') as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['device_channel'], '9')
            self.assertEqual(rows[0]['protocol'], 'zmonitor')
            self.assertIn('Hello, "GPS"\\nnext', rows[0]['text'])
            self.assertNotIn('[32m', rows[0]['text'])
            self.assertTrue(rows[0]['data'].startswith('C8 D2'))

    def test_custom_text_profile_and_title_colors_survive_layout_edit(self):
        from MegaSerial.panel_view import PanelLayoutDialog
        self.select({**preset('text'), 'prefix': '$', 'separator': ':', 'mapping': {'gps': '32'}})
        self.w.on_data_received(b'$gps:custom\n')
        self.assertIn('custom', self.text('32'))
        self.w.panel_view.apply_control({'panel_id': '32', 'panel_style': {'color': 'red'}})
        dialog = PanelLayoutDialog(self.w.panel_view.workspace)
        self.addCleanup(dialog.deleteLater)
        dialog.accept()
        panel = next(p for p in dialog.result_workspace.panels if p['id'] == '32')
        self.assertEqual(panel['title_color'], '#ff0000')
        self.assertEqual(dialog.result_workspace.protocol_profile['kind'], 'text')

    def test_invalid_colors_and_profile_metadata_preserve_layout(self):
        self.select(preset('zmonitor'))
        for color in ('²,2,3', '9' * 5000 + ',2,3'):
            packet = b'\xc8\xd2#TITLE_COLOR:' + color.encode() + b'\xfa'
            self.w.on_data_received(packet)
            self.assertEqual(self.w.events[-1]['protocol_diagnostic'], 'Invalid title color')
        state = self.w.panel_view.workspace.to_dict()
        state['protocol_profile'] = {'version': 999}
        state['panels'][0]['title_color'] = {'invalid': 'color'}
        self.w.panel_view.set_workspace(PanelWorkspace.restore(state))
        self.assertEqual(self.w.panel_view.workspace.row_counts, [4, 4, 4, 4])
        self.assertEqual(self.w.panel_view.workspace.protocol_profile['kind'], 'megaserial')
