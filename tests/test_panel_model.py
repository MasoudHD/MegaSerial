import unittest
from copy import deepcopy
from MegaSerial.panel_model import PanelWorkspace


def workspace():
    return PanelWorkspace({"max_columns": 3, "row_counts": [2, 1],
                           "panels": [{"id": "11", "title": "General"},
                                      {"id": "12", "title": "GPS Receiver"},
                                      {"id": "21", "title": "CAN Bus"}]})


class WorkspaceTests(unittest.TestCase):
    def test_routing_and_titles(self):
        w = workspace()
        for ev, dest in [({}, "11"), ({"dir": "tx"}, "11"),
                         ({"panel_id": "12"}, "12"), ({"panel_id": "unknown"}, "11")]:
            self.assertEqual(w.destination(ev), dest)
        self.assertTrue(w.update_title("12", "موقع"))
        self.assertEqual(w.titles()["12"], "موقع")
        self.assertFalse(w.update_title("unknown", "Unknown"))
        self.assertTrue(w.update_title("11", "Other"))

    def test_scope_and_no_mutation(self):
        w = workspace()
        events = [{"panel_id": ident, "data": b"OK"} for ident in ("12", "21", "11")]
        original = deepcopy(events)
        for scope, expected in [(None, [False, False, False]), (["12"], [False, True, True]),
                                (["12", "21"], [False, False, True]), ([], [True, True, True])]:
            w.scope = scope
            self.assertEqual([w.accepts(e, lambda e: False) for e in events], expected)
        self.assertEqual(events, original)

    def test_layout_changes_and_scope(self):
        w = workspace()
        state = w.to_dict()
        state["row_counts"] = [3]
        state["panels"][2] = {"id": "13", "title": "Modem"}
        added = PanelWorkspace(state)
        self.assertTrue(added.in_scope("13"))
        state["scope"] = ["12", "21"]
        changed = PanelWorkspace(state)
        self.assertEqual(changed.scope, ["12"])
        changed.update_title("12", "New title")
        self.assertEqual(changed.scope, ["12"])
        self.assertEqual(changed.destination({"panel_id": "21"}), "11")

    def test_automatic_ids_without_titles(self):
        w = PanelWorkspace({"max_columns": 4, "row_counts": [4, 2, 3]})
        self.assertEqual(list(w.titles()), ["11", "12", "13", "14", "21", "22", "31", "32", "33"])
        self.assertEqual(w.destination({"panel_id": "32"}), "32")
        self.assertEqual(w.titles()["32"], "Panel 32")
        w.update_title("32", "GPS")
        self.assertEqual(w.destination({"panel_id": "32"}), "32")

    def test_roundtrip_and_invalid_defaults(self):
        w = workspace()
        w.active = True
        w.scope = ["12"]
        self.assertEqual(PanelWorkspace(w.to_dict()).to_dict(), w.to_dict())
        for bad in (None, [], {"row_counts": [0]}, {"max_columns": 999},
                    {"panels": [{"id": "12", "title": "GPS"}]}):
            self.assertEqual(PanelWorkspace.restore(bad).to_dict(), PanelWorkspace().to_dict())

    def test_visibility_preserves_routing_scope_and_handles_layout_changes(self):
        w = workspace()
        w.scope = ['12']
        w.set_visible('12', False)
        self.assertFalse(w.is_visible('12'))
        self.assertEqual(w.destination({'panel_id': '12'}), '12')
        self.assertTrue(w.in_scope('12'))
        restored = PanelWorkspace(w.to_dict())
        self.assertFalse(restored.is_visible('12'))
        restored.set_visible('12', True)
        self.assertTrue(restored.is_visible('12'))
        state = w.to_dict()
        state['row_counts'] = [1]
        state['panels'] = state['panels'][:1]
        self.assertEqual(PanelWorkspace(state).hidden_ids, [])
        self.assertEqual(workspace().hidden_ids, [])
        self.assertEqual(PanelWorkspace({**state, 'hidden_ids': 'invalid'}).hidden_ids, [])

    def test_automatic_discovery_and_manual_restore(self):
        w = workspace()
        w.panel_widths = {'11': 1200, '12': 800}
        w.set_visible('21', False)
        manual = w.to_dict()
        w.set_automatic(True)
        self.assertEqual(w.row_counts, [10] * 10)
        self.assertEqual(len(set(w.titles())), 100)
        self.assertEqual([i for i in w.titles() if w.is_visible(i)], ['11'])
        ev = {'type': 'data', 'dir': 'rx', 'panel_id': '10:2', 'data': b'raw'}
        before = deepcopy(ev)
        self.assertTrue(w.observe(ev))
        self.assertFalse(w.observe(ev))
        self.assertTrue(w.is_visible('10:2'))
        self.assertEqual(w.destination({'panel_id': '3:10'}), '3:10')
        self.assertEqual(w.destination({'panel_id': '1010'}), '11')
        self.assertEqual(ev, before)
        self.assertEqual(PanelWorkspace.restore(w.to_dict()).to_dict(), w.to_dict())
        w.set_automatic(False)
        self.assertEqual(w.to_dict(), manual)

    def test_automatic_hidden_panels_and_invalid_state(self):
        w = workspace()
        w.set_automatic(True)
        w.observe({'type': 'data', 'panel_id': '32'})
        w.set_visible('32', False)
        w.observe({'type': 'data', 'panel_id': '32'})
        self.assertFalse(w.is_visible('32'))
        self.assertFalse(w.observe({'type': 'log', 'panel_id': '99'}))
        self.assertFalse(w.is_visible('99'))
        w.observe({'type': 'data', 'panel_id': 'unknown'})
        self.assertTrue(w.is_visible('11'))
        restored = PanelWorkspace.restore({**w.to_dict(), 'seen_ids': 7})
        self.assertTrue(restored.is_visible('11'))
