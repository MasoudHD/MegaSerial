import unittest
from copy import deepcopy
from MegaSerial.panel_model import PanelWorkspace


def workspace():
    return PanelWorkspace({"max_columns": 3, "row_counts": [2, 1],
                           "panels": [{"id": "general", "title": "General"},
                                      {"id": "gps", "title": "GPS Receiver"},
                                      {"id": "can", "title": "CAN Bus"}]})


class WorkspaceTests(unittest.TestCase):
    def test_routing_and_titles(self):
        w = workspace()
        for ev, dest in [({}, "general"), ({"dir": "tx"}, "general"),
                         ({"panel_id": "gps"}, "gps"), ({"panel_id": "unknown"}, "general")]:
            self.assertEqual(w.destination(ev), dest)
        self.assertTrue(w.update_title("gps", "موقع"))
        self.assertEqual(w.titles()["gps"], "موقع")
        self.assertFalse(w.update_title("unknown", "Unknown"))
        self.assertFalse(w.update_title("general", "Other"))

    def test_scope_and_no_mutation(self):
        w = workspace()
        events = [{"panel_id": ident, "data": b"OK"} for ident in ("gps", "can", "general")]
        original = deepcopy(events)
        for scope, expected in [(None, [False, False, False]), (["gps"], [False, True, True]),
                                (["gps", "can"], [False, False, True]), ([], [True, True, True])]:
            w.scope = scope
            self.assertEqual([w.accepts(e, lambda e: False) for e in events], expected)
        self.assertEqual(events, original)

    def test_layout_changes_and_scope(self):
        w = workspace()
        state = w.to_dict()
        state["panels"][2] = {"id": "modem", "title": "Modem"}
        added = PanelWorkspace(state)
        self.assertTrue(added.in_scope("modem"))
        state["scope"] = ["gps", "can"]
        changed = PanelWorkspace(state)
        self.assertEqual(changed.scope, ["gps"])
        changed.update_title("gps", "New title")
        self.assertEqual(changed.scope, ["gps"])
        self.assertEqual(changed.destination({"panel_id": "can"}), "general")

    def test_roundtrip_and_invalid_defaults(self):
        w = workspace()
        w.active = True
        w.scope = ["gps"]
        self.assertEqual(PanelWorkspace(w.to_dict()).to_dict(), w.to_dict())
        for bad in (None, [], {"row_counts": [0]}, {"max_columns": 999},
                    {"panels": [{"id": "gps", "title": "GPS"}]}):
            self.assertEqual(PanelWorkspace.restore(bad).to_dict(), PanelWorkspace().to_dict())
