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
        w.scope = ['12', '21']
        w.panel_widths = {'11': 1300, '12': 700}
        w.row_heights = {'0': 1200, '1': 800}
        w.update_title('12', 'گیرنده')
        events = [{'type': 'data', 'dir': 'rx', 'ts': datetime.now(),
                   'data': b'@PANEL:12|OK\n', 'panel_id': '12', 'panel_payload': 'OK'},
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
        self.assertEqual(w.destination(loaded['events'][1]), '11')

    def test_automatic_project_roundtrip(self):
        w = workspace()
        w.set_automatic(True)
        w.observe({'type': 'data', 'panel_id': '10:10'})
        data = project.collect_project_data(project_name='Auto', settings={}, events=[],
                                            panel_view=w.to_dict())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'auto.msproj'
            project.save_project(path, data)
            restored = PanelWorkspace.restore(project.load_project(path)['panel_view'])
        self.assertEqual(restored.to_dict(), w.to_dict())
        restored.set_automatic(False)
        self.assertEqual(restored.row_counts, [2, 1])

    def test_old_project_and_old_event(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.msproj'
            path.write_text('{"events": [{"type": "log", "msg": "legacy"}]}')
            loaded = project.load_project(path)
        w = PanelWorkspace.restore(loaded['panel_view'])
        self.assertFalse(w.active)
        self.assertEqual(w.row_counts, [1])
        self.assertEqual(w.destination(loaded['events'][0]), '11')

    def test_custom_id_project_migration_preserves_bytes_titles_and_scope(self):
        old_state = {"active": True, "max_columns": 2, "row_counts": [2, 1],
                     "panels": [{"id": "general", "title": "General"},
                                {"id": "gps", "title": "Receiver"},
                                {"id": "can", "title": "CAN"}], "scope": ["gps"]}
        events = [{"type": "data", "dir": "rx", "data": b"@PANEL:gps|OK\n",
                   "panel_id": "gps", "panel_payload": "OK"}]
        data = project.collect_project_data(project_name="Legacy panels", settings={},
                                            events=events, panel_view=old_state)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.msproj'
            project.save_project(path, data)
            loaded = project.load_project(path)
            self.assertEqual(loaded['panel_view']['scope'], ['12'])
            self.assertEqual(loaded['panel_view']['panels'][1], {'id': '12', 'title': 'Receiver'})
            self.assertEqual(loaded['events'][0]['panel_id'], '12')
            self.assertEqual(loaded['events'][0]['original_panel_id'], 'gps')
            self.assertEqual(loaded['events'][0]['data'], events[0]['data'])
            project.save_project(path, project.collect_project_data(
                project_name='Migrated', settings={}, events=loaded['events'], panel_view=loaded['panel_view']))
            self.assertEqual(project.load_project(path)['events'], loaded['events'])
        self.assertEqual(events[0]['panel_id'], 'gps')
        self.assertEqual(old_state['panels'][1]['id'], 'gps')
