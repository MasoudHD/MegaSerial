import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from MegaSerial import project
from MegaSerial.panel_model import PanelWorkspace
from test_panel_model import workspace


class PanelPersistenceTests(unittest.TestCase):
    def test_roundtrip(self):
        w = workspace()
        w.active = True
        w.scope = ['gps', 'can']
        w.update_title('gps', 'گیرنده')
        events = [{'type': 'data', 'dir': 'rx', 'ts': datetime.now(),
                   'data': b'@PANEL:gps|OK\n', 'panel_id': 'gps', 'panel_payload': 'OK'},
                  {'type': 'data', 'dir': 'tx', 'data': b'AT'}]
        data = project.collect_project_data(project_name='Panel', settings={}, events=events,
                                            panel_view=w.to_dict())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'panels.msproj'
            project.save_project(path, data)
            loaded = project.load_project(path)
        self.assertEqual(data['format_version'], 1)
        self.assertEqual(PanelWorkspace.restore(loaded['panel_view']).to_dict(), w.to_dict())
        self.assertEqual(loaded['events'], events)
        self.assertEqual(w.destination(loaded['events'][1]), 'general')

    def test_old_project_and_old_event(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.msproj'
            path.write_text('{"events": [{"type": "log", "msg": "legacy"}]}')
            loaded = project.load_project(path)
        w = PanelWorkspace.restore(loaded['panel_view'])
        self.assertFalse(w.active)
        self.assertEqual(w.row_counts, [1])
        self.assertEqual(w.destination(loaded['events'][0]), 'general')
