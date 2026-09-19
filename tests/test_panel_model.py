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
