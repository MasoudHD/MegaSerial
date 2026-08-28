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


@dataclass
class Step:
    name: str = "Step"
    data: str = ""
    fmt: str = utils.FORMAT_ASCII
    line_ending: str = "CRLF (\\r\\n)"
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
        return utils.build_payload(self.data, self.fmt, self.line_ending)

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

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": [s.to_dict() for s in self.steps]}

    @classmethod
    def from_dict(cls, d: dict) -> "NamedSequence":
        steps = [Step.from_dict(s) for s in d.get("steps", [])]
        return cls(name=d.get("name", "Sequence") or "Sequence", steps=steps)


CSV_FIELDS = [
    "name", "data", "fmt", "line_ending", "enabled", "advance", "delay_ms",
    "expect", "expect_fmt", "timeout_ms", "on_timeout", "max_retries", "beep_on_match",
    "fail_on",
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
                 loop: bool = False, loop_delay_ms: int = 0):
        super().__init__()
        self._steps = [s for s in steps if s.enabled]
        self._all_indices = [i for i, s in enumerate(steps) if s.enabled]
        self._send = send_fn
        self._rx = rx
        self._loop = loop
        self._loop_delay_ms = loop_delay_ms
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

        completed = True
        pass_num = 0
        while not self._stop.is_set():
            pass_num += 1
            if self._loop:
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
            if self._stop.is_set() or not self._loop:
                break
            if self._loop_delay_ms:
                if self._sleep(self._loop_delay_ms):
                    break

        self.finished_all.emit(completed)

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
            len([s for s in seq.steps if s.enabled]) for seq in self._sequences
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

                enabled = [s for s in seq.steps if s.enabled]
                if not enabled:
                    self.log.emit(f"[{seq.name}] skipped (no enabled steps)", "info")
                    continue

                self.sequence_started.emit(seq_idx, seq.name)
                self.log.emit(f"=== Running sequence: {seq.name} ===", "info")

                runner = SequenceRunner(seq.steps, self._send, self._rx, loop=False)
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

                if seq_idx < len(self._sequences) - 1 and self._delay_between_ms:
                    self.log.emit(
                        f"Waiting {self._delay_between_ms} ms before next sequence…", "info")
                    if self._sleep(self._delay_between_ms):
                        completed = False
                        break

            if self._stop.is_set() or not self._loop:
                break

        self.finished_all.emit(completed)
