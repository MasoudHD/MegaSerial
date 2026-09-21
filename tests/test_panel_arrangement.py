import unittest
from copy import deepcopy
from MegaSerial.panel_arrangement import positions, move_panel
from MegaSerial.panel_model import PanelWorkspace
from test_panel_model import workspace


class ArrangementTests(unittest.TestCase):
    def test_swap_and_empty_cell_preserve_identity(self):
        w = workspace()
        before = deepcopy(w.panels)
        self.assertTrue(move_panel(w, '12', 1, 0))
        self.assertEqual(positions(w)['21'], [0, 1])
        self.assertEqual(positions(w)['12'], [1, 0])
        self.assertTrue(move_panel(w, '12', 1, 2))
        self.assertEqual(positions(w)['12'], [1, 2])
        self.assertEqual(w.destination({'panel_id': '12'}), '12')
        self.assertEqual(w.panels, before)
        saved = w.to_dict()
        for target in [(-1, 0), (2, 0), (0, 3), (True, 0)]:
            self.assertFalse(move_panel(w, '12', *target))
        self.assertEqual(w.to_dict(), saved)
        self.assertEqual(PanelWorkspace.restore(saved).to_dict(), saved)

    def test_automatic_discovery_preserves_placed_and_hidden_panels(self):
        w = workspace()
        w.set_automatic(True)
        w.observe({'type': 'data', 'panel_id': '32'})
        move_panel(w, '32', 2, 2)
        old = deepcopy(positions(w))
        w.set_visible('32', False)
        for ident in ['99', '10:10', '12']:
            w.observe({'type': 'data', 'panel_id': ident})
        current = positions(w)
        for ident, cell in old.items():
            self.assertEqual(current[ident], cell)
        self.assertEqual(len({tuple(c) for c in current.values()}), len(current))
        w.set_visible('32', True)
        self.assertEqual(positions(w)['32'], [2, 2])
        w.display_positions = {}
        self.assertNotEqual(positions(w)['32'], [2, 2])

    def test_invalid_saved_positions_and_layout_shrink(self):
        state = workspace().to_dict()
        state['display_positions'] = {'11': [0, 0], '12': [0, 0], '21': [9, 9],
                                      'bad': [0, 1]}
        w = PanelWorkspace.restore(state)
        self.assertEqual(w.display_positions, {'11': [0, 0]})
        self.assertEqual(len(positions(w)), 3)
        state.update(row_counts=[1], panels=state['panels'][:1])
        self.assertEqual(positions(PanelWorkspace.restore(state)), {'11': [0, 0]})

    def test_manual_arrangement_survives_automatic_toggle(self):
        w = workspace()
        move_panel(w, '12', 1, 2)
        saved = w.to_dict()
        w.set_automatic(True)
        move_panel(w, '11', 1, 1)
        w.set_automatic(False)
        self.assertEqual(w.to_dict(), saved)
