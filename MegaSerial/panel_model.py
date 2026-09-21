"""Project-owned panel layout and routing. Contains no Qt or event storage."""
from copy import deepcopy
from .protocol_profiles import preset, validate_profile
from .panel_protocol import valid_panel_id
from .panel_positions import position_id

GENERAL = "11"
PANEL_SCHEMA_VERSION = 2
MAX_ROWS = 10
MAX_COLUMNS = 10


def position_ids(row_counts):
    return [position_id(row, column) for row, count in enumerate(row_counts, 1)
            for column in range(1, count + 1)]


def default_title(ident):
    return "General" if ident == GENERAL else f"Panel {ident}"


class PanelWorkspace:
    def __init__(self, state=None):
        self.active = False
        self.max_columns = 1
        self.row_counts = [1]
        self.panels = [{"id": GENERAL, "title": "General"}]
        self.protocol_profile = preset()
        self.hidden_ids = []
        self.panel_widths = {}
        self.row_heights = {}
        self.automatic = False
        self.seen_ids = []
        self.manual_layout = None
        self.scope = None  # None means All, [] means no panels are filtered.
        if state is not None:
            self._load(state)

    def _load(self, state):
        if not isinstance(state, dict):
            raise ValueError("Panel workspace must be an object")
        columns = state.get("max_columns", 1)
        counts = state.get("row_counts", [1])
        if type(columns) is not int or not 1 <= columns <= MAX_COLUMNS:
            raise ValueError("Maximum columns must be between 1 and 10")
        if (not isinstance(counts, list) or not 1 <= len(counts) <= MAX_ROWS
                or any(type(n) is not int or not 1 <= n <= columns for n in counts)):
            raise ValueError("Each row must contain 1..maximum columns panels (up to 10 rows)")
        expected_ids = position_ids(counts)
        panels = state.get("panels", [{"id": ident, "title": default_title(ident)}
                                      for ident in expected_ids])
        if not isinstance(panels, list) or len(panels) != sum(counts):
            raise ValueError("Panel count must match the layout")
        ids = []
        for p in panels:
            if (not isinstance(p, dict) or not isinstance(p.get("id"), str)
                    or not valid_panel_id(p["id"]) or not isinstance(p.get("title"), str)):
                raise ValueError("Panel IDs must be nonempty, without whitespace or |")
            ids.append(p["id"])
        if ids != expected_ids:
            raise ValueError("Panel IDs must match their row and column positions")
        scope = state.get("scope")
        if scope is not None and (not isinstance(scope, list) or any(not isinstance(s, str) for s in scope)):
            raise ValueError("Invalid search scope")
        try:
            self.protocol_profile = validate_profile(state.get("protocol_profile", preset()))
        except (ValueError, TypeError):
            self.protocol_profile = preset()
        self.active = bool(state.get("active", False))
        self.max_columns, self.row_counts = columns, list(counts)
        self.panels = deepcopy(panels)
        for panel in self.panels:
            panel["title"] = panel["title"] or default_title(panel["id"])
        self.scope = None if scope is None else list(dict.fromkeys(s for s in scope if s in ids))
        def weights(key, allowed):
            values = state.get(key, {})
            if not isinstance(values, dict):
                return {}
            return {k: v for k, v in values.items()
                    if k in allowed and type(v) is int and 1 <= v <= 100000}

        self.panel_widths = weights("panel_widths", ids)
        self.row_heights = weights("row_heights", [str(i) for i in range(len(counts))])
        self.automatic = state.get("automatic") is True
        seen = state.get("seen_ids", [])
        self.seen_ids = [i for i in ids if i in seen] if isinstance(seen, list) else []
        manual = state.get("manual_layout")
        if self.automatic and isinstance(manual, dict):
            manual = {**manual, "automatic": False, "manual_layout": None}
            self.manual_layout = PanelWorkspace.restore(manual).to_dict()
        if self.automatic and counts != [10] * 10:
            self.automatic = False
        hidden = state.get("hidden_ids", [])
        self.hidden_ids = [ident for ident in ids if ident in hidden] if isinstance(hidden, list) else []

    @classmethod
    def restore(cls, state):
        try:
            return cls(state)
        except (ValueError, TypeError):
            return cls()

    def to_dict(self):
        return {"schema_version": PANEL_SCHEMA_VERSION, "active": self.active, "rows": len(self.row_counts),
                "max_columns": self.max_columns, "row_counts": list(self.row_counts),
                "panels": deepcopy(self.panels), "scope": deepcopy(self.scope),
                "protocol_profile": deepcopy(self.protocol_profile),
                "hidden_ids": list(self.hidden_ids),
                "panel_widths": dict(self.panel_widths), "row_heights": dict(self.row_heights),
                "automatic": self.automatic, "seen_ids": list(self.seen_ids),
                "manual_layout": deepcopy(self.manual_layout)}

    def set_automatic(self, enabled):
        if enabled == self.automatic:
            return
        if enabled:
            saved = self.to_dict()
            old = {p["id"]: p for p in self.panels}
            self.max_columns = 10
            self.row_counts = [10] * 10
            self.panels = [old.get(i, {"id": i, "title": default_title(i)})
                           for i in position_ids(self.row_counts)]
            self.manual_layout = saved
            self.automatic = True
            self.seen_ids = [GENERAL]
            self.hidden_ids = []
        else:
            saved = self.manual_layout or {}
            # Keep device titles and protocol changes made while automatic was on.
            titles = {p["id"]: p for p in self.panels}
            restored = PanelWorkspace.restore(saved)
            restored.panels = [deepcopy(titles.get(p["id"], p)) for p in restored.panels]
            restored.protocol_profile = self.protocol_profile
            restored.active = self.active
            self.__dict__.update(restored.__dict__)

    def observe(self, event):
        """Discover destinations before filtering; no event storage or mutation."""
        if not self.automatic or event.get("type") != "data":
            return False
        ident = self.destination(event)
        if ident in self.seen_ids:
            return False
        self.seen_ids.append(ident)
        return True

    def is_visible(self, ident):
        return (ident not in self.hidden_ids and
                (not self.automatic or ident == GENERAL or ident in self.seen_ids))

    def set_visible(self, ident, visible):
        if ident not in self.titles():
            return
        if visible:
            self.hidden_ids = [i for i in self.hidden_ids if i != ident]
        elif ident not in self.hidden_ids:
            self.hidden_ids.append(ident)

    def destination(self, event):
        ident = event.get("panel_id")
        return ident if ident in self.titles() else GENERAL

    def titles(self):
        return {p["id"]: p["title"] for p in self.panels}

    def update_title(self, ident, title):
        for p in self.panels:
            if p["id"] == ident:
                p["title"] = title or default_title(ident)
                return True
        return False

    def in_scope(self, ident):
        return self.scope is None or ident in self.scope

    def accepts(self, event, predicate):
        return not self.in_scope(self.destination(event)) or predicate(event)


def migrate_panel_project(state, events):
    """Upgrade legacy custom IDs by position; preserve raw bytes and original IDs.

    Returns copies only when upgrading. Invalid metadata is left to restore's
    safe default; projects without panel metadata need no migration.
    """
    if not isinstance(state, dict) or state.get("schema_version", 1) != 1:
        return state, events
    panels = state.get("panels")
    if not isinstance(panels, list):
        return state, events
    try:
        layout = PanelWorkspace({"max_columns": state.get("max_columns", 1),
                                 "row_counts": state.get("row_counts", [1])})
        if len(panels) != len(layout.panels):
            return state, events
        old_ids = [p["id"] for p in panels]
        if (any(not isinstance(i, str) or not valid_panel_id(i) for i in old_ids)
                or len(set(old_ids)) != len(old_ids)):
            return state, events
        mapping = dict(zip(old_ids, position_ids(layout.row_counts)))
        upgraded = {**state, "schema_version": PANEL_SCHEMA_VERSION,
                    "panels": [{"id": mapping[p["id"]], "title": p["title"]} for p in panels]}
        if state.get("scope") is not None:
            upgraded["scope"] = [mapping[i] for i in state["scope"] if i in mapping]
        upgraded = PanelWorkspace(upgraded).to_dict()
    except (KeyError, TypeError, ValueError):
        return state, events
    migrated_events = []
    for ev in events:
        ident = ev.get("panel_id")
        if ident in mapping and mapping[ident] != ident:
            ev = {**ev, "panel_id": mapping[ident], "original_panel_id": ident}
        migrated_events.append(ev)
    return upgraded, migrated_events
