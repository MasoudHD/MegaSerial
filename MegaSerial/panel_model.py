"""Project-owned panel layout and routing. Contains no Qt or event storage."""
from copy import deepcopy
from .panel_protocol import valid_panel_id

GENERAL = "general"
MAX_ROWS = 8
MAX_COLUMNS = 8


class PanelWorkspace:
    def __init__(self, state=None):
        self.active = False
        self.max_columns = 1
        self.row_counts = [1]
        self.panels = [{"id": GENERAL, "title": "General"}]
        self.scope = None  # None means All, [] means no panels are filtered.
        if state is not None:
            self._load(state)

    def _load(self, state):
        if not isinstance(state, dict):
            raise ValueError("Panel workspace must be an object")
        columns = state.get("max_columns", 1)
        counts = state.get("row_counts", [1])
        panels = state.get("panels", [{"id": GENERAL, "title": "General"}])
        if type(columns) is not int or not 1 <= columns <= MAX_COLUMNS:
            raise ValueError("Maximum columns must be between 1 and 8")
        if (not isinstance(counts, list) or not 1 <= len(counts) <= MAX_ROWS
                or any(type(n) is not int or not 1 <= n <= columns for n in counts)):
            raise ValueError("Each row must contain 1..maximum columns panels (up to 8 rows)")
        if not isinstance(panels, list) or len(panels) != sum(counts):
            raise ValueError("Panel count must match the layout")
        ids = []
        for p in panels:
            if (not isinstance(p, dict) or not isinstance(p.get("id"), str)
                    or not valid_panel_id(p["id"]) or not isinstance(p.get("title"), str)):
                raise ValueError("Panel IDs must be nonempty, without whitespace or |")
            ids.append(p["id"])
        if len(set(ids)) != len(ids) or ids[0] != GENERAL:
            raise ValueError("IDs must be unique; the first panel must be general")
        scope = state.get("scope")
        if scope is not None and (not isinstance(scope, list) or any(not isinstance(s, str) for s in scope)):
            raise ValueError("Invalid search scope")
        self.active = bool(state.get("active", False))
        self.max_columns, self.row_counts = columns, list(counts)
        self.panels = deepcopy(panels)
        self.panels[0]["title"] = "General"
        self.scope = None if scope is None else list(dict.fromkeys(s for s in scope if s in ids))

    @classmethod
    def restore(cls, state):
        try:
            return cls(state)
        except (ValueError, TypeError):
            return cls()

    def to_dict(self):
        return {"active": self.active, "rows": len(self.row_counts),
                "max_columns": self.max_columns, "row_counts": list(self.row_counts),
                "panels": deepcopy(self.panels), "scope": deepcopy(self.scope)}

    def destination(self, event):
        ident = event.get("panel_id")
        return ident if ident in self.titles() else GENERAL

    def titles(self):
        return {p["id"]: p["title"] for p in self.panels}

    def update_title(self, ident, title):
        for p in self.panels:
            if p["id"] == ident and ident != GENERAL:
                p["title"] = title
                return True
        return False

    def in_scope(self, ident):
        return self.scope is None or ident in self.scope

    def accepts(self, event, predicate):
        return not self.in_scope(self.destination(event)) or predicate(event)
