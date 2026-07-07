"""Extract numeric samples from serial text for live plotting."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

GRAPH_MODE_AUTO = "auto"
GRAPH_MODE_TIME = "time"
GRAPH_MODE_XY = "xy"
GRAPH_MODES = (GRAPH_MODE_AUTO, GRAPH_MODE_TIME, GRAPH_MODE_XY)

_NUM = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"


@dataclass
class ParsedPoint:
    series: str
    x: float | None   # None → use timestamp / sample index
    y: float
    ts: datetime | None = None


def _float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _parse_xy(text: str, ts: datetime) -> list[ParsedPoint]:
    x_m = re.search(rf"x\s*[:=]\s*({_NUM})", text, re.I)
    y_m = re.search(rf"y\s*[:=]\s*({_NUM})", text, re.I)
    if x_m and y_m:
        xv, yv = _float(x_m.group(1)), _float(y_m.group(1))
        if xv is not None and yv is not None:
            return [ParsedPoint("Y", xv, yv, ts)]

    # "1.2, 3.4" or "1.2 3.4"
    if re.fullmatch(rf"{_NUM}\s*[,;]\s*{_NUM}", text):
        a, b = re.split(r"[,;]", text, maxsplit=1)
        xv, yv = _float(a.strip()), _float(b.strip())
        if xv is not None and yv is not None:
            return [ParsedPoint("Y", xv, yv, ts)]
    return []


def _parse_labeled(text: str, ts: datetime) -> list[ParsedPoint]:
    points: list[ParsedPoint] = []
    for m in re.finditer(rf"(\w+)\s*[:=]\s*({_NUM})", text):
        key, val_s = m.group(1), m.group(2)
        if key.lower() in ("x", "y"):
            continue
        val = _float(val_s)
        if val is not None:
            points.append(ParsedPoint(key, None, val, ts))
    return points


def _parse_single_number(text: str, ts: datetime) -> list[ParsedPoint]:
    if re.fullmatch(_NUM, text):
        val = _float(text)
        if val is not None:
            return [ParsedPoint("value", None, val, ts)]
    return []


def parse_line(text: str, ts: datetime, mode: str = GRAPH_MODE_AUTO) -> list[ParsedPoint]:
    """Parse one line of ASCII-ish serial text into plot points."""
    text = text.replace("\r", "").strip()
    if not text:
        return []

    if mode == GRAPH_MODE_XY:
        return _parse_xy(text, ts)

    if mode == GRAPH_MODE_TIME:
        labeled = _parse_labeled(text, ts)
        if labeled:
            return labeled
        return _parse_single_number(text, ts)

    # auto: prefer XY when both axes present, else labeled channels, else lone number
    xy = _parse_xy(text, ts)
    if xy:
        return xy
    labeled = _parse_labeled(text, ts)
    if labeled:
        return labeled
    return _parse_single_number(text, ts)
