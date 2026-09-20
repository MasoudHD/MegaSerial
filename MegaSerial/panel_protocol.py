"""Strict, stateless parsing of complete UTF-8 panel protocol lines."""
from dataclasses import dataclass
from .ansi_text import plain_ansi


def valid_panel_id(value: str) -> bool:
    return bool(value) and all(c.isprintable() and not c.isspace() and c != "|" for c in value)


@dataclass(frozen=True)
class PanelCommand:
    kind: str
    panel_id: str = ""
    text: str = ""


class PanelProtocolParser:
    def parse(self, line: bytes) -> PanelCommand:
        # Callers must supply exactly one LF-terminated logical line. Invalid
        # UTF-8/control bytes are ordinary serial data, never commands.
        if not line.endswith(b"\n"):
            return PanelCommand("normal")
        try:
            text = line[:-1].removesuffix(b"\r").decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return PanelCommand("normal")
        if any(not c.isprintable() and c != "\t" for c in text):
            return PanelCommand("normal")
        for prefix, kind in (("@PANEL:", "data"), ("@PANEL_TITLE:", "title")):
            if text.startswith(prefix):
                panel_id, sep, payload = text[len(prefix):].partition("|")
                if sep and valid_panel_id(panel_id):
                    return PanelCommand(kind, panel_id, payload)
        return PanelCommand("normal")


def panel_event(ev: dict) -> dict:
    """A transient presentation projection; never modify retained raw bytes."""
    if "panel_payload" in ev:
        text = ev["panel_payload"]
        if ev.get("panel_ansi"):
            return {**ev, "data": plain_ansi(text).encode("utf-8"), "_panel_ansi_text": text}
        return {**ev, "data": text.encode("utf-8")}
    if "panel_title" in ev:
        return {**ev, "data": ("Title: " + ev["panel_title"]).encode("utf-8")}
    return ev
