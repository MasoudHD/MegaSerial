"""Validated device profiles and bounded streaming packet decoding, without Qt."""
from copy import deepcopy
import json
import re
from . import utils
from .panel_positions import valid_position_id
from .panel_protocol import PanelProtocolParser, valid_panel_id

MAX_PACKET = 65536
PROFILE_VERSION = 1
KINDS = ("megaserial", "zmonitor", "text", "frame")
ENCODINGS = ("utf-8", "ascii", "latin-1")


def preset(kind="megaserial"):
    profile = {"version": PROFILE_VERSION, "kind": kind, "encoding": "utf-8",
               "mapping": {}, "ansi": False, "prefix": "@PANEL:",
               "separator": "|", "ending": "0A", "start": "C8", "end": "FA",
               "channel_offset": 0, "payload_offset": 1, "channel_bias": 201 if kind == "zmonitor" else 0}
    if kind == "zmonitor":
        profile["ansi"] = True
        profile["mapping"] = {str(i): f"{i // 4 + 1}{i % 4 + 1}" for i in range(16)}
    return profile


def validate_profile(value):
    if not isinstance(value, dict) or value.get("version", 1) != PROFILE_VERSION:
        raise ValueError("Unsupported protocol profile version")
    kind = value.get("kind", "megaserial")
    if kind not in KINDS:
        raise ValueError("Unknown device protocol")
    p = {**preset(kind), **deepcopy(value)}
    if p["encoding"] not in ENCODINGS:
        raise ValueError("Choose UTF-8, ASCII or Latin-1 encoding")
    if type(p["ansi"]) is not bool:
        raise ValueError("ANSI option must be true or false")
    mapping = p["mapping"]
    if (not isinstance(mapping, dict) or len(mapping) > 256
            or any(not isinstance(k, str) or not valid_panel_id(k)
                   or not isinstance(v, str) or not valid_position_id(v)
                   for k, v in mapping.items())):
        raise ValueError("Map channel names to position IDs such as 11 or 32 (up to 256 mappings)")
    for key in ("prefix", "separator"):
        if not isinstance(p[key], str) or len(p[key]) > 128 or any(not c.isprintable() for c in p[key]):
            raise ValueError(f"{key.capitalize()} must be printable text (up to 128 characters)")
    if not p["separator"]:
        raise ValueError("Channel separator must not be empty")
    for key in ("start", "end", "ending"):
        if not isinstance(p[key], str):
            raise ValueError(f"{key} must contain hexadecimal bytes")
        data = utils.parse_hex(p[key])
        if not 1 <= len(data) <= 8:
            raise ValueError(f"{key.capitalize()} must contain 1–8 bytes")
        p[key] = utils.to_hex(data)
    for key in ("channel_offset", "payload_offset", "channel_bias"):
        if type(p[key]) is not int or not 0 <= p[key] <= (255 if key == "channel_bias" else 64):
            raise ValueError(f"Invalid {key.replace('_', ' ')}")
    if p["payload_offset"] <= p["channel_offset"]:
        raise ValueError("Payload must start after the channel byte")
    if kind == "zmonitor":
        # Only channel mapping is customizable for a named preset.
        fixed = preset(kind)
        for key in ("start", "end", "channel_offset", "payload_offset", "channel_bias", "encoding", "ansi"):
            p[key] = fixed[key]
    if kind in ("zmonitor", "frame"):
        maximum = 15 if kind == "zmonitor" else 255 - p["channel_bias"]
        if any(not 1 <= len(k) <= 3 or not k.isascii() or not k.isdecimal()
               or str(int(k)) != k or not 0 <= int(k) <= maximum for k in mapping):
            raise ValueError(f"Device channels must be decimal numbers from 0 to {maximum} (without leading zeros)")
    return p


def load_profile(path):
    with open(path, encoding="utf-8") as fh:
        return validate_profile(json.load(fh))


def save_profile(path, profile):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(validate_profile(profile), fh, ensure_ascii=False, indent=2)


def title_command(text):
    """Return zMonitor title/style fields; colors are validated by the UI."""
    command, sep, body = text.partition(":")
    name = command.upper()
    if not sep or name not in ("#TITLE", "#TITLE_COLOR", "#TITLE_BGCOLOR", "#TITLE_STYLE"):
        return None
    body = body.replace("\r", "").replace("\n", "")
    if name == "#TITLE":
        return {"title": body}
    if name in ("#TITLE_COLOR", "#TITLE_BGCOLOR"):
        return {"color" if name == "#TITLE_COLOR" else "bg": body.strip()}
    if body.lstrip().startswith("{"):
        try:
            fields = json.loads(body)
        except ValueError:
            raise ValueError("Invalid title-style JSON") from None
        if not isinstance(fields, dict):
            raise ValueError("Title style must be a JSON object")
    else:
        fields = {}
        for item in body.split(";"):
            key, sep, value = item.partition("=")
            if sep:
                fields[key.strip().lower()] = value.strip()
    result = {k: v for k, v in fields.items() if k in ("title", "color", "bg") and isinstance(v, str)}
    if "bg" not in result and isinstance(fields.get("background"), str):
        result["bg"] = fields["background"]
    if not result:
        raise ValueError("No recognized title-style fields")
    return result


class ProtocolDecoder:
    """Returns raw bytes plus optional event metadata; owns no session events."""
    def __init__(self, profile=None):
        self.profile = validate_profile(profile or preset())
        self.buffer = bytearray()
        self.discard_line = False

    def ordinary(self, raw, reason):
        return {"data": raw, "protocol": self.profile["kind"], "protocol_diagnostic": reason}

    def flush(self):
        self.discard_line = False
        if not self.buffer:
            return []
        raw = bytes(self.buffer)
        self.buffer.clear()
        return [self.ordinary(raw, "Incomplete packet")]

    def _packet(self, raw, body):
        p = self.profile
        try:
            if p["kind"] == "megaserial":
                command = PanelProtocolParser().parse(raw)
                if command.kind == "normal":
                    return self.ordinary(raw, "Not a MegaSerial command")
                return {"data": raw, "protocol": "megaserial", "panel_id": command.panel_id,
                        "device_channel": command.panel_id,
                        "panel_payload" if command.kind == "data" else "panel_title": command.text}
            if p["kind"] == "text":
                line = body.decode(p["encoding"], errors="strict")
                if p["ending"] == "0A":
                    line = line.removesuffix("\r")
                if not line.startswith(p["prefix"]):
                    return self.ordinary(raw, "Prefix not found")
                channel, sep, payload = line[len(p["prefix"]):].partition(p["separator"])
                if not sep or not valid_panel_id(channel):
                    raise ValueError("Missing channel or separator")
            else:
                if len(body) < p["payload_offset"]:
                    raise ValueError("Packet is shorter than its header")
                number = body[p["channel_offset"]] - p["channel_bias"]
                if number < 0 or (p["kind"] == "zmonitor" and number > 15):
                    raise ValueError("Channel byte is outside the supported range")
                channel = str(number)
                payload = body[p["payload_offset"]:].decode(p["encoding"], errors="strict")
            if any(not c.isprintable() and c not in ("\n", "\r", "\t", "\x1b" if p["ansi"] else "") for c in payload):
                raise ValueError("Payload contains unsupported control bytes")
            destination = p["mapping"].get(channel)
            if destination is None and p["kind"] == "text" and valid_position_id(channel):
                destination = channel
            event = {"data": raw, "protocol": p["kind"], "device_channel": channel,
                     "panel_id": destination, "panel_payload": payload}
            if destination is None:
                event["protocol_diagnostic"] = "Unmapped channel; displayed in General"
            if p["ansi"]:
                event["panel_ansi"] = True
            if p["kind"] == "zmonitor":
                style = title_command(payload)
                if style is not None:
                    event["panel_style"] = style
                    event["panel_control"] = True
            return event
        except (UnicodeError, ValueError) as exc:
            return self.ordinary(raw, str(exc))

    def feed(self, data):
        self.buffer.extend(data)
        out = []
        p = self.profile
        if p["kind"] in ("megaserial", "text"):
            ending = b"\n" if p["kind"] == "megaserial" else utils.parse_hex(p["ending"])
            while True:
                end = self.buffer.find(ending)
                if end < 0:
                    break
                raw = bytes(self.buffer[:end + len(ending)])
                del self.buffer[:len(raw)]
                if self.discard_line or len(raw) > MAX_PACKET:
                    out.append(self.ordinary(raw, "Oversized line"))
                else:
                    out.append(self._packet(raw, raw[:-len(ending)]))
                self.discard_line = False
            if len(self.buffer) > MAX_PACKET:
                # Keep a possible partial delimiter so framing recovers next read.
                keep = len(ending) - 1
                raw = bytes(self.buffer[:-keep] if keep else self.buffer)
                del self.buffer[:len(raw)]
                out.append(self.ordinary(raw, "Oversized incomplete line"))
                self.discard_line = True
            return out
        start, ending = utils.parse_hex(p["start"]), utils.parse_hex(p["end"])
        while self.buffer:
            pos = self.buffer.find(start)
            if pos < 0:
                keep = 0
                for n in range(1, min(len(start), len(self.buffer) + 1)):
                    if self.buffer.endswith(start[:n]):
                        keep = n
                count = len(self.buffer) - keep
                if count:
                    out.append(self.ordinary(bytes(self.buffer[:count]), "Unframed data"))
                    del self.buffer[:count]
                break
            if pos:
                out.append(self.ordinary(bytes(self.buffer[:pos]), "Unframed data"))
                del self.buffer[:pos]
            end = self.buffer.find(ending, len(start) + p["payload_offset"])
            # A new start marker resynchronizes an interrupted frame. Markers
            # inside payloads are unsupported; no escaping is guessed.
            next_start = self.buffer.find(start, len(start) + p["payload_offset"]) if start != ending else -1
            if next_start >= 0 and (end < 0 or next_start < end):
                out.append(self.ordinary(bytes(self.buffer[:next_start]), "Interrupted frame"))
                del self.buffer[:next_start]
                continue
            if end < 0:
                if len(self.buffer) > MAX_PACKET:
                    out.append(self.ordinary(bytes(self.buffer), "Oversized incomplete frame"))
                    self.buffer.clear()
                break
            raw = bytes(self.buffer[:end + len(ending)])
            del self.buffer[:len(raw)]
            out.append(self.ordinary(raw, "Oversized frame") if len(raw) > MAX_PACKET
                       else self._packet(raw, raw[len(start):-len(ending)]))
        return out
