"""Stable routing IDs for the bounded panel matrix."""
import re


def position_id(row, column):
    return f"{row}:{column}" if 10 in (row, column) else f"{row}{column}"


def valid_position_id(value):
    return isinstance(value, str) and re.fullmatch(r"(?:[1-9][1-9]|10:(?:[1-9]|10)|[1-9]:10)", value) is not None
