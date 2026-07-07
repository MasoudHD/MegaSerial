"""Conversion helpers for ASCII / HEX / binary serial payloads.

All functions convert between human-typed text and raw ``bytes`` so the rest of
the app only ever moves ``bytes`` in and out of the serial port.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Data formats and line endings
# ---------------------------------------------------------------------------

FORMAT_ASCII = "ASCII"
FORMAT_HEX = "HEX"
FORMAT_BINARY = "Binary"
FORMATS = (FORMAT_ASCII, FORMAT_HEX, FORMAT_BINARY)

# Label -> bytes appended after the payload when sending.
LINE_ENDINGS = {
    "None": b"",
    "LF (\\n)": b"\n",
    "CR (\\r)": b"\r",
    "CRLF (\\r\\n)": b"\r\n",
}

_ASCII_ESCAPES = {
    "n": b"\n",
    "r": b"\r",
    "t": b"\t",
    "0": b"\x00",
    "\\": b"\\",
    '"': b'"',
    "'": b"'",
}


class ParseError(ValueError):
    """Raised when user input cannot be parsed into bytes."""


# ---------------------------------------------------------------------------
# Text -> bytes
# ---------------------------------------------------------------------------

def parse_ascii(text: str) -> bytes:
    """Encode ASCII/UTF-8 text, expanding a small set of C-style escapes.

    Supported escapes: ``\\n \\r \\t \\0 \\\\ \\" \\' \\xHH``.
    """
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "x" and i + 3 < n + 1:
                hex_part = text[i + 2:i + 4]
                if len(hex_part) == 2 and re.fullmatch(r"[0-9a-fA-F]{2}", hex_part):
                    out.append(int(hex_part, 16))
                    i += 4
                    continue
                raise ParseError(f"Invalid \\x escape near position {i}")
            if nxt in _ASCII_ESCAPES:
                out += _ASCII_ESCAPES[nxt]
                i += 2
                continue
            # Unknown escape: keep the backslash literally.
            out += ch.encode("utf-8")
            i += 1
            continue
        out += ch.encode("utf-8")
        i += 1
    return bytes(out)


def parse_hex(text: str) -> bytes:
    """Parse a hex string. Accepts spaces, commas, ``0x`` prefixes and newlines."""
    cleaned = text.replace("0x", " ").replace("0X", " ")
    cleaned = re.sub(r"[,;\s]+", "", cleaned)
    if cleaned == "":
        return b""
    if len(cleaned) % 2 != 0:
        raise ParseError("Hex input must have an even number of digits.")
    if not re.fullmatch(r"[0-9a-fA-F]+", cleaned):
        raise ParseError("Hex input contains non-hex characters.")
    return bytes.fromhex(cleaned)


def parse_binary(text: str) -> bytes:
    """Parse a binary string. Bits are grouped into bytes (8 bits each)."""
    cleaned = re.sub(r"[,;\s]+", "", text)
    if cleaned == "":
        return b""
    if not re.fullmatch(r"[01]+", cleaned):
        raise ParseError("Binary input may only contain 0 and 1.")
    if len(cleaned) % 8 != 0:
        raise ParseError("Binary input length must be a multiple of 8 bits.")
    return bytes(int(cleaned[i:i + 8], 2) for i in range(0, len(cleaned), 8))


def normalize_format(fmt: str) -> str:
    """Map a (possibly lower/mixed case) format name to a canonical constant."""
    key = (fmt or "").strip().lower()
    mapping = {
        "ascii": FORMAT_ASCII,
        "hex": FORMAT_HEX,
        "binary": FORMAT_BINARY,
        "bin": FORMAT_BINARY,
    }
    return mapping.get(key, FORMAT_ASCII)


def parse_input(text: str, fmt: str) -> bytes:
    fmt = normalize_format(fmt)
    if fmt == FORMAT_ASCII:
        return parse_ascii(text)
    if fmt == FORMAT_HEX:
        return parse_hex(text)
    if fmt == FORMAT_BINARY:
        return parse_binary(text)
    raise ParseError(f"Unknown format: {fmt}")


# ---------------------------------------------------------------------------
# bytes -> text (for the monitor view)
# ---------------------------------------------------------------------------

def to_hex(data: bytes, bytes_per_row: int = 0, sep: str = " ") -> str:
    tokens = [f"{b:02X}" for b in data]
    if bytes_per_row and bytes_per_row > 0:
        rows = [sep.join(tokens[i:i + bytes_per_row])
                for i in range(0, len(tokens), bytes_per_row)]
        return "\n".join(rows)
    return sep.join(tokens)


def to_binary(data: bytes, bytes_per_row: int = 0) -> str:
    tokens = [f"{b:08b}" for b in data]
    if bytes_per_row and bytes_per_row > 0:
        rows = [" ".join(tokens[i:i + bytes_per_row])
                for i in range(0, len(tokens), bytes_per_row)]
        return "\n".join(rows)
    return " ".join(tokens)


def to_ascii(data: bytes, show_nonprintable_as_hex: bool = False) -> str:
    """Render bytes as text. Printable ASCII is kept; other bytes become dots
    (or ``\\xHH`` when ``show_nonprintable_as_hex`` is set)."""
    out = []
    for b in data:
        if b in (0x0A, 0x0D, 0x09):  # keep newlines/tabs
            out.append(chr(b))
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        elif show_nonprintable_as_hex:
            out.append(f"\\x{b:02X}")
        else:
            out.append("·")
    return "".join(out)


def to_hexdump(data: bytes, width: int = 16) -> str:
    """Classic ``hexdump`` style: offset | hex bytes | ascii gutter."""
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(width * 3 - 1)
        ascii_part = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        lines.append(f"{off:08X}  {hex_part}  |{ascii_part}|")
    return "\n".join(lines)


def format_output(data: bytes, fmt: str, bytes_per_row: int = 16,
                  show_nonprintable_as_hex: bool = False) -> str:
    if fmt == FORMAT_ASCII:
        return to_ascii(data, show_nonprintable_as_hex)
    if fmt == FORMAT_HEX:
        return to_hex(data, bytes_per_row)
    if fmt == FORMAT_BINARY:
        return to_binary(data, bytes_per_row)
    if fmt == "Hexdump":
        return to_hexdump(data, bytes_per_row or 16)
    return to_ascii(data)


def human_preview(data: bytes, limit: int = 48) -> str:
    """Short one-line preview used in logs and step labels."""
    text = to_ascii(data)
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if len(text) > limit:
        text = text[:limit] + "…"
    return text
