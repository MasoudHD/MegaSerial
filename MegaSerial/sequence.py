"""Sequential command runner.

A sequence is a list of :class:`Step` objects. Each step sends a payload and
then decides when to advance to the next step:

* ``time``     - wait a fixed delay, then continue.
* ``response`` - wait until an expected reply is seen (or timeout).
* ``both``     - wait for the expected reply, then also wait the delay.

The runner lives on its own :class:`QThread` so long delays never block the UI.
It reads incoming bytes through an :class:`RxMonitor` that the main window keeps
fed from the serial port.
"""
from __future__ import annotations

import csv
import threading
import time
from dataclasses import dataclass, asdict, field

from PyQt6.QtCore import QThread, pyqtSignal

from . import utils

ADVANCE_TIME = "time"
ADVANCE_RESPONSE = "response"
ADVANCE_BOTH = "both"
ADVANCE_MODES = (ADVANCE_TIME, ADVANCE_RESPONSE, ADVANCE_BOTH)

ADVANCE_LABELS = {
    ADVANCE_TIME: "After delay",
    ADVANCE_RESPONSE: "On response",
    ADVANCE_BOTH: "Response + delay",
}

ON_TIMEOUT_CONTINUE = "continue"
ON_TIMEOUT_STOP = "stop"
ON_TIMEOUT_RETRY = "retry"

# How often a whole sequence repeats. The loop wraps the full step list; it
# never changes how an individual step advances, retries or fails.
LOOP_NONE = "none"
LOOP_COUNT = "count"
LOOP_UNTIL_RX = "until_rx"
LOOP_FOREVER = "forever"
LOOP_MODES = (LOOP_NONE, LOOP_COUNT, LOOP_UNTIL_RX, LOOP_FOREVER)

LOOP_LABELS = {
    LOOP_NONE: "No loop (run once)",
    LOOP_COUNT: "Repeat a fixed number of times",
    LOOP_UNTIL_RX: "Repeat until a reply is received",
    LOOP_FOREVER: "Repeat forever",
}

MIN_LOOP_COUNT = 1
MAX_LOOP_COUNT = 1_000_000
MAX_LOOP_DELAY_MS = 3_600_000


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class SequenceLoop:
    """Loop configuration for one whole sequence.

    Values are normalized on construction, so an out-of-range repeat count or an
    unknown mode can never reach the runner.
    """

    mode: str = LOOP_NONE
    count: int = 1
    until_rx: str = ""
    until_rx_fmt: str = utils.FORMAT_ASCII
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if self.mode not in LOOP_MODES:
            self.mode = LOOP_NONE
        self.count = _clamp_int(self.count, MIN_LOOP_COUNT, MAX_LOOP_COUNT, MIN_LOOP_COUNT)
        self.delay_ms = _clamp_int(self.delay_ms, 0, MAX_LOOP_DELAY_MS, 0)
        self.until_rx = self.until_rx or ""
        self.until_rx_fmt = utils.normalize_format(self.until_rx_fmt)

    @property
    def repeats(self) -> bool:
        return self.mode != LOOP_NONE

    def until_rx_bytes(self) -> bytes:
        """Pattern that ends the loop, or empty when the mode does not use one."""
        if self.mode != LOOP_UNTIL_RX or not self.until_rx:
            return b""
        return utils.parse_input(self.until_rx, self.until_rx_fmt)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "SequenceLoop":
        if isinstance(d, cls):
            return cls(**asdict(d))
        if not isinstance(d, dict):
            return cls()
        return cls(
            mode=str(d.get("mode", LOOP_NONE) or LOOP_NONE),
            count=d.get("count", MIN_LOOP_COUNT),
            until_rx=str(d.get("until_rx", "") or ""),
            until_rx_fmt=d.get("until_rx_fmt", utils.FORMAT_ASCII),
            delay_ms=d.get("delay_ms", 0),
        )


def loop_from_settings(settings: dict) -> SequenceLoop:
    """Read the Sequence tab's loop config, migrating pre-loop-mode settings.

    Older settings only had a ``sequence_loop`` flag, which meant "repeat until
    stopped", so it maps to :data:`LOOP_FOREVER`.
    """
    raw = settings.get("sequence_loop_config")
    if isinstance(raw, dict):
        return SequenceLoop.from_dict(raw)
    return SequenceLoop(
        mode=LOOP_FOREVER if settings.get("sequence_loop", False) else LOOP_NONE,
        delay_ms=settings.get("sequence_loop_delay_ms", 0),
    )


@dataclass
class Step:
    name: str = "Step"
    data: str = ""
    fmt: str = utils.FORMAT_ASCII
    line_ending: str = "CRLF (\\r\\n)"
    custom_suffix: str = ""    # appended when line_ending is "Custom"
    enabled: bool = True
    advance: str = ADVANCE_TIME
    delay_ms: int = 1000
    # Response matching (used by ``response`` and ``both``)
    expect: str = ""
    expect_fmt: str = utils.FORMAT_ASCII
    timeout_ms: int = 2000
    on_timeout: str = ON_TIMEOUT_CONTINUE
    max_retries: int = 2
    beep_on_match: bool = False
    fail_on: str = ""          # if this reply is seen first, the step fails fast

    def payload_bytes(self) -> bytes:
        return utils.build_payload(self.data, self.fmt, self.line_ending, self.custom_suffix)

    def expect_bytes(self) -> bytes:
        if not self.expect:
            return b""
        return utils.parse_input(self.expect, self.expect_fmt)

    def fail_on_bytes(self) -> bytes:
        if not self.fail_on:
            return b""
        return utils.parse_input(self.fail_on, self.expect_fmt)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        """Build a Step from a dict, coercing types (useful for CSV strings)."""
        def as_bool(v) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

        def as_int(v, default: int) -> int:
            try:
                return int(str(v).strip())
            except (ValueError, TypeError):
                return default

        base = cls()
        out: dict = {}
        for f in cls.__dataclass_fields__:
            if f not in d or d[f] is None or d[f] == "":
                continue
            default = getattr(base, f)
            if isinstance(default, bool):
                out[f] = as_bool(d[f])
            elif isinstance(default, int):
                out[f] = as_int(d[f], default)
            else:
                out[f] = d[f]
        step = cls(**out)
        step.fmt = utils.normalize_format(step.fmt)
        step.expect_fmt = utils.normalize_format(step.expect_fmt)
        if step.advance not in ADVANCE_MODES:
            step.advance = ADVANCE_TIME
        return step


@dataclass
class NamedSequence:
    """A named list of steps, used in the Sequence Group tab."""
    name: str = "Sequence"
    steps: list[Step] = field(default_factory=list)
    # Whether the group run includes this sequence. Independent of Step.enabled.
    enabled: bool = True
    loop: SequenceLoop = field(default_factory=SequenceLoop)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "enabled": self.enabled,
            "loop": self.loop.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NamedSequence":
        steps = [Step.from_dict(s) for s in d.get("steps", [])]
        # Groups written before these fields existed run every sequence once.
        raw_enabled = d.get("enabled", True)
        enabled = (raw_enabled if isinstance(raw_enabled, bool)
                   else str(raw_enabled).strip().lower() in ("1", "true", "yes", "y", "on"))
        return cls(name=d.get("name", "Sequence") or "Sequence", steps=steps,
                   enabled=enabled, loop=SequenceLoop.from_dict(d.get("loop")))


CSV_FIELDS = [
    "name", "data", "fmt", "line_ending", "enabled", "advance", "delay_ms",
    "expect", "expect_fmt", "timeout_ms", "on_timeout", "max_retries", "beep_on_match",
    "fail_on", "custom_suffix",
]


def steps_to_csv(path: str, steps: list["Step"]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for s in steps:
            row = s.to_dict()
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def steps_from_csv(path: str) -> list["Step"]:
    steps: list[Step] = []
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            # Skip blank lines / rows with no name and no data.
            cleaned = {(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                       for k, v in raw.items() if k}
            if not any(cleaned.get(f) for f in ("name", "data", "expect")):
                continue
            steps.append(Step.from_dict(cleaned))
    return steps


class RxMonitor:
    """Thread-safe accumulator of received bytes with change notification."""

    def __init__(self):
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._event = threading.Event()

    def feed(self, data: bytes) -> None:
        with self._lock:
            self._buffer += data
        self._event.set()

    def mark(self) -> int:
        with self._lock:
            return len(self._buffer)

    def contains(self, pattern: bytes, start_index: int = 0) -> bool:
        """Non-blocking check for ``pattern`` in everything received since *start_index*.

        Uses the same accumulated buffer as :meth:`wait_for`, so a pattern split
        across several received chunks still matches.
        """
        if not pattern:
            return False
        with self._lock:
            return pattern in bytes(self._buffer[start_index:])

    def wait_for(self, pattern: bytes, start_index: int, timeout: float,
                 stop_event: threading.Event) -> bool:
        """Block until ``pattern`` appears in the buffer after ``start_index``.

        Returns ``True`` on match, ``False`` on timeout or external stop.
        """
        if not pattern:
            return True
        deadline = time.monotonic() + timeout
        while True:
            if stop_event.is_set():
                return False
            self._event.clear()
            with self._lock:
                haystack = bytes(self._buffer[start_index:])
            if pattern in haystack:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._event.wait(min(remaining, 0.2))

    def wait_for_any(self, patterns: list[bytes], start_index: int, timeout: float,
                     stop_event: threading.Event) -> int:
        """Wait until any of ``patterns`` appears after ``start_index``.

        Returns the index of the matched pattern, or ``-1`` on timeout/stop.
        Empty patterns in the list are ignored.
        """
        active = [(i, p) for i, p in enumerate(patterns) if p]
        if not active:
            return -1
        deadline = time.monotonic() + timeout
        while True:
            if stop_event.is_set():
                return -1
            self._event.clear()
            with self._lock:
                haystack = bytes(self._buffer[start_index:])
            for i, p in active:
                if p in haystack:
                    return i
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return -1
            self._event.wait(min(remaining, 0.2))


class SequenceRunner(QThread):
    step_started = pyqtSignal(int, str)      # index, name
    step_result = pyqtSignal(int, str, str)  # index, status, detail
    log = pyqtSignal(str, str)               # message, kind (info/tx/warn/error)
    progress = pyqtSignal(int, int)          # current, total
    finished_all = pyqtSignal(bool)          # completed_normally

    # How long to keep retrying a send while the port is temporarily down
    # (e.g. during an auto-reconnect after a modem reset).
    _SEND_WAIT_S = 25.0

    def __init__(self, steps: list[Step], send_fn, rx: RxMonitor,
                 loop: "SequenceLoop | dict | None" = None):
        super().__init__()
        self._steps = [s for s in steps if s.enabled]
        self._all_indices = [i for i, s in enumerate(steps) if s.enabled]
        self._send = send_fn
        self._rx = rx
        self._loop = SequenceLoop.from_dict(loop) if loop is not None else SequenceLoop()
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def _sleep(self, ms: int) -> bool:
        """Interruptible sleep. Returns True if we were asked to stop."""
        if ms <= 0:
            return self._stop.is_set()
        return self._stop.wait(ms / 1000.0)

    def _send_resilient(self, payload: bytes, name: str) -> bool:
        """Send, waiting through a temporary port outage (auto-reconnect)."""
        if self._send(payload):
            return True
        deadline = time.monotonic() + self._SEND_WAIT_S
        warned = False
        while not self._stop.is_set() and time.monotonic() < deadline:
            if self._stop.wait(0.3):
                return False
            if self._send(payload):
                if warned:
                    self.log.emit(f"[{name}] port back, resent.", "info")
                return True
            if not warned:
                self.log.emit(f"[{name}] port unavailable, waiting for reconnect…", "warn")
                warned = True
        return False

    def run(self) -> None:  # noqa: C901 - the state machine is intentionally linear
        total = len(self._steps)
        if total == 0:
            self.log.emit("Sequence has no enabled steps.", "warn")
            self.finished_all.emit(False)
            return

        try:
            until_pattern = self._loop.until_rx_bytes()
        except utils.ParseError as exc:
            self.log.emit(f"Invalid loop termination pattern: {exc}", "error")
            self.finished_all.emit(False)
            return
        # Anchor before the first pass so a reply arriving mid-sequence counts.
        rx_mark = self._rx.mark() if until_pattern else 0

        completed = True
        pass_num = 0
        while not self._stop.is_set():
            pass_num += 1
            if self._loop.repeats:
                self.log.emit(f"--- Sequence pass #{pass_num} ---", "info")
            for pos, (orig_idx, step) in enumerate(zip(self._all_indices, self._steps)):
                if self._stop.is_set():
                    completed = False
                    break
                self.progress.emit(pos + 1, total)
                self.step_started.emit(orig_idx, step.name)
                if not self._run_step(orig_idx, step):
                    completed = False
                    self._stop.set()
                    break
            # A stop request or an aborting step ends the run; the loop never
            # swallows that outcome.
            if self._stop.is_set():
                break
            if not self._should_repeat(pass_num, until_pattern, rx_mark):
                break
            if self._loop.delay_ms and self._sleep(self._loop.delay_ms):
                break

        self.finished_all.emit(completed)

    def _should_repeat(self, pass_num: int, until_pattern: bytes, rx_mark: int) -> bool:
        """Decide whether another full pass of the sequence should start."""
        mode = self._loop.mode
        if mode == LOOP_FOREVER:
            return True
        if mode == LOOP_COUNT:
            return pass_num < self._loop.count
        if mode == LOOP_UNTIL_RX:
            if not until_pattern:
                return False   # nothing to wait for: behave like a single run
            if self._rx.contains(until_pattern, rx_mark):
                self.log.emit(
                    f"Loop ended: received {utils.human_preview(until_pattern)}", "info")
                return False
            return True
        return False

    def _run_step(self, idx: int, step: Step) -> bool:
        """Execute one step. Returns False to abort the whole sequence."""
        try:
            payload = step.payload_bytes()
            expected = step.expect_bytes()
            fail_pat = step.fail_on_bytes()
        except utils.ParseError as exc:
            self.step_result.emit(idx, "error", str(exc))
            self.log.emit(f"[{step.name}] parse error: {exc}", "error")
            return False

        attempts = step.max_retries + 1 if step.advance != ADVANCE_TIME else 1
        for attempt in range(attempts):
            if self._stop.is_set():
                return False

            mark = self._rx.mark()
            if not self._send_resilient(payload, step.name):
                if self._stop.is_set():
                    return False
                self.step_result.emit(idx, "error", "send failed (port unavailable)")
                self.log.emit(f"[{step.name}] send failed — port unavailable", "error")
                return False
            self.log.emit(f"→ [{step.name}] {utils.human_preview(payload)}", "tx")

            if step.advance == ADVANCE_TIME:
                if self._sleep(step.delay_ms):
                    return False
                self.step_result.emit(idx, "done", f"waited {step.delay_ms} ms")
                return True

            # response or both: wait for the expected reply, or a fail pattern
            if not expected:
                match_idx = 0   # nothing to wait for -> proceed immediately
            else:
                match_idx = self._rx.wait_for_any(
                    [expected, fail_pat], mark, step.timeout_ms / 1000.0, self._stop)
            if self._stop.is_set():
                return False

            if match_idx == 0:
                if step.advance == ADVANCE_BOTH:
                    self.log.emit(f"[{step.name}] response matched, waiting {step.delay_ms} ms", "info")
                    if self._sleep(step.delay_ms):
                        return False
                self.step_result.emit(idx, "matched", "response matched")
                self.log.emit(f"[{step.name}] response matched", "info")
                return True

            # Either a fail pattern matched (match_idx == 1) or a timeout (-1).
            if match_idx == 1:
                reason = f"error reply '{step.fail_on}'"
                self.log.emit(f"[{step.name}] {reason}", "error")
            else:
                reason = "no response (timeout)"

            if step.on_timeout == ON_TIMEOUT_RETRY and attempt < attempts - 1:
                self.log.emit(f"[{step.name}] {reason}, retry {attempt + 1}/{attempts - 1}", "warn")
                continue
            if step.on_timeout == ON_TIMEOUT_STOP:
                self.step_result.emit(idx, "failed" if match_idx == 1 else "timeout",
                                      f"{reason} - stopped")
                self.log.emit(f"[{step.name}] {reason}, stopping sequence", "error")
                return False
            self.step_result.emit(idx, "failed" if match_idx == 1 else "timeout",
                                  f"{reason} - continued")
            self.log.emit(f"[{step.name}] {reason}, continuing", "warn")
            return True

        return True


class SequenceGroupRunner(QThread):
    """Run multiple named sequences top-to-bottom with optional inter-sequence delay."""

    sequence_started = pyqtSignal(int, str)       # index, name
    sequence_finished = pyqtSignal(int, str, bool)  # index, name, completed
    step_started = pyqtSignal(int, int, str)      # seq_idx, step_idx, name
    step_result = pyqtSignal(int, int, str, str)  # seq_idx, step_idx, status, detail
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)               # current step, total steps
    finished_all = pyqtSignal(bool)

    def __init__(self, sequences: list[NamedSequence], send_fn, rx: RxMonitor,
                 delay_between_ms: int = 0, loop: bool = False):
        super().__init__()
        self._sequences = sequences
        self._send = send_fn
        self._rx = rx
        self._delay_between_ms = delay_between_ms
        self._loop = loop
        self._stop = threading.Event()
        self._current_runner: SequenceRunner | None = None

    def request_stop(self) -> None:
        self._stop.set()
        if self._current_runner:
            self._current_runner.request_stop()

    def _sleep(self, ms: int) -> bool:
        if ms <= 0:
            return self._stop.is_set()
        return self._stop.wait(ms / 1000.0)

    def run(self) -> None:
        if not self._sequences:
            self.log.emit("Sequence group is empty.", "warn")
            self.finished_all.emit(False)
            return

        total_steps = sum(
            len([s for s in seq.steps if s.enabled])
            for seq in self._sequences if seq.enabled
        )
        if total_steps == 0:
            self.log.emit("No enabled steps in the sequence group.", "warn")
            self.finished_all.emit(False)
            return

        completed = True
        pass_num = 0
        step_counter = 0

        while not self._stop.is_set():
            pass_num += 1
            if self._loop:
                self.log.emit(f"--- Sequence group pass #{pass_num} ---", "info")

            for seq_idx, seq in enumerate(self._sequences):
                if self._stop.is_set():
                    completed = False
                    break

                if not seq.enabled:
                    self.log.emit(f"[{seq.name}] skipped (disabled)", "info")
                    continue

                enabled = [s for s in seq.steps if s.enabled]
                if not enabled:
                    self.log.emit(f"[{seq.name}] skipped (no enabled steps)", "info")
                    continue

                self.sequence_started.emit(seq_idx, seq.name)
                self.log.emit(f"=== Running sequence: {seq.name} ===", "info")

                runner = SequenceRunner(seq.steps, self._send, self._rx, loop=seq.loop)
                self._current_runner = runner

                def _on_step_started(idx: int, name: str, _si=seq_idx) -> None:
                    nonlocal step_counter
                    step_counter += 1
                    self.progress.emit(step_counter, total_steps)
                    self.step_started.emit(_si, idx, name)

                def _on_step_result(idx: int, status: str, detail: str, _si=seq_idx) -> None:
                    self.step_result.emit(_si, idx, status, detail)

                runner.step_started.connect(_on_step_started)
                runner.step_result.connect(_on_step_result)
                runner.log.connect(self.log.emit)
                seq_completed = [True]
                runner.finished_all.connect(lambda ok: seq_completed.__setitem__(0, ok))
                runner.run()

                self._current_runner = None
                if not seq_completed[0]:
                    completed = False
                    self._stop.set()
                seq_ok = seq_completed[0] and not self._stop.is_set()
                self.sequence_finished.emit(seq_idx, seq.name, seq_ok)

                if self._stop.is_set():
                    break

                more_to_run = any(
                    later.enabled and any(s.enabled for s in later.steps)
                    for later in self._sequences[seq_idx + 1:]
                )
                if more_to_run and self._delay_between_ms:
                    self.log.emit(
                        f"Waiting {self._delay_between_ms} ms before next sequence…", "info")
                    if self._sleep(self._delay_between_ms):
                        completed = False
                        break

            if self._stop.is_set() or not self._loop:
                break

        self.finished_all.emit(completed)
