import unittest
from MegaSerial.event_history import EventHistory
from MegaSerial.panel_model import PanelWorkspace


class HistoryTests(unittest.TestCase):
    def test_independent_capacity_and_chronological_index(self):
        h = EventHistory()
        h.configure({'11': 2, '12': 10000, '21': 10000})
        quiet = {'panel_id': '21', 'data': b'quiet'}
        h.append(quiet)
        for n in range(10002):
            h.append({'panel_id': '12', 'n': n})
        self.assertEqual(len(h), 10001)
        self.assertIs(h[0], quiet)
        self.assertEqual(h[1]['n'], 2)
        self.assertEqual(h[-1]['n'], 10001)
        h.configure({'11': 2, '12': 1, '21': 10000})
        self.assertEqual(list(h), [quiet, {'panel_id': '12', 'n': 10001}])
        h.configure({'11': 2, '12': 500, '21': 10000})
        self.assertEqual(len(h), 2)

    def test_general_unknown_tx_multiline_and_clear(self):
        h = EventHistory()
        h.configure({'11': 2})
        h.append({'data': b'one\ntwo\nthree', 'dir': 'tx'})
        h.append({'panel_id': 'unknown', 'data': b'unknown'})
        removed = h.append({'msg': 'log'})
        self.assertEqual(removed['dir'], 'tx')
        self.assertEqual(h[0]['panel_id'], 'unknown')
        h.clear()
        self.assertEqual(list(h), [])

    def test_capacity_validation_roundtrip_and_old_defaults(self):
        w = PanelWorkspace({'max_columns': 2, 'row_counts': [2]})
        self.assertEqual(w.capacities(), {'11': 10000, '12': 10000})
        w.set_capacity('12', 12345)
        self.assertEqual(PanelWorkspace.restore(w.to_dict()).capacities()['12'], 12345)
        for value in [0, -1, True, '100', 1000001]:
            with self.assertRaises(ValueError):
                w.set_capacity('12', value)
        state = w.to_dict()
        state['panels'][1]['capacity'] = 'bad'
        self.assertEqual(PanelWorkspace.restore(state).capacities()['12'], 10000)

    def test_project_retains_more_than_old_shared_limit(self):
        import tempfile
        from pathlib import Path
        from MegaSerial import project
        w = PanelWorkspace({'max_columns': 2, 'row_counts': [2]})
        w.set_capacity('12', 12000)
        h = EventHistory()
        h.configure(w.capacities())
        for number in range(7000):
            h.append({'panel_id': '11', 'number': number})
            h.append({'panel_id': '12', 'number': number})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'depth.msproj'
            project.save_project(path, project.collect_project_data(
                project_name='depth', settings={}, events=list(h), panel_view=w.to_dict()))
            loaded = project.load_project(path)
        restored = EventHistory()
        restored.configure(PanelWorkspace.restore(loaded['panel_view']).capacities())
        for event in loaded['events']:
            restored.append(event)
        self.assertEqual(len(restored), 14000)
        self.assertEqual(list(restored), list(h))

    def test_recent_index_distinguishes_old_evictions(self):
        h = EventHistory(recent_limit=2)
        h.configure({'11': 3})
        for n in range(4):
            h.append({'number': n})
        self.assertFalse(h.evicted_recently)
        h.configure({'11': 1})
        h.append({'number': 4})
        self.assertTrue(h.evicted_recently)
