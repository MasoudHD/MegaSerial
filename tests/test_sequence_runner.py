"""Execution-semantics tests for the sequence runners.

The runners are QThread subclasses, but ``run()`` is a plain method, so these
tests call it directly and stay deterministic instead of relying on scheduling.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QCoreApplication

    from MegaSerial.sequence import (
        ADVANCE_TIME, NamedSequence, RxMonitor, SequenceGroupRunner, Step,
    )

    _APP = QCoreApplication.instance() or QCoreApplication([])
except Exception as exc:  # noqa: BLE001 - no usable Qt build in this environment
    raise unittest.SkipTest(f"Qt core unavailable: {exc}")


def step(name: str) -> Step:
    """A step that sends its name and advances immediately."""
    return Step(name=name, data=name, line_ending="None",
                advance=ADVANCE_TIME, delay_ms=0)


def sequence(name: str, enabled: bool = True) -> NamedSequence:
    return NamedSequence(name=name, steps=[step(name)], enabled=enabled)


class GroupRunResult:
    def __init__(self):
        self.sent: list[bytes] = []
        self.started: list[str] = []
        self.logs: list[str] = []
        self.completed: bool | None = None

    def send(self, payload: bytes) -> bool:
        self.sent.append(payload)
        return True


def run_group(sequences, **kwargs) -> GroupRunResult:
    result = GroupRunResult()
    runner = SequenceGroupRunner(sequences, result.send, RxMonitor(), **kwargs)
    runner.sequence_started.connect(lambda _i, name: result.started.append(name))
    runner.log.connect(lambda msg, _kind: result.logs.append(msg))
    runner.finished_all.connect(lambda ok: setattr(result, "completed", ok))
    runner.run()
    return result


class GroupSequenceEnabledTests(unittest.TestCase):
    def test_all_enabled_runs_every_sequence_in_order(self):
        result = run_group([sequence("a"), sequence("b"), sequence("c")])

        self.assertEqual(result.started, ["a", "b", "c"])
        self.assertEqual(result.sent, [b"a", b"b", b"c"])
        self.assertTrue(result.completed)

    def test_disabled_sequences_are_skipped_but_ordering_is_preserved(self):
        result = run_group([
            sequence("a"), sequence("b", enabled=False), sequence("c"),
        ])

        self.assertEqual(result.started, ["a", "c"])
        self.assertEqual(result.sent, [b"a", b"c"])
        self.assertTrue(result.completed)
        self.assertIn("[b] skipped (disabled)", result.logs)

    def test_all_disabled_finishes_without_sending_anything(self):
        result = run_group([sequence("a", enabled=False), sequence("b", enabled=False)])

        self.assertEqual(result.sent, [])
        self.assertEqual(result.started, [])
        self.assertFalse(result.completed)
        self.assertIn("No enabled steps in the sequence group.", result.logs)

    def test_a_disabled_sequence_still_runs_when_launched_on_its_own(self):
        # Disabling only removes it from the group run; the sequence itself is intact.
        disabled = sequence("solo", enabled=False)

        self.assertTrue(all(s.enabled for s in disabled.steps))
        self.assertEqual(disabled.steps[0].payload_bytes(), b"solo")

    def test_no_delay_is_spent_after_the_last_sequence_that_actually_runs(self):
        result = run_group(
            [sequence("a"), sequence("b", enabled=False)], delay_between_ms=5000)

        self.assertEqual(result.sent, [b"a"])
        self.assertNotIn("Waiting 5000 ms before next sequence…", result.logs)
        self.assertTrue(result.completed)

    def test_a_sequence_with_no_enabled_steps_is_still_skipped(self):
        empty = NamedSequence(name="empty", steps=[step("x")])
        empty.steps[0].enabled = False

        result = run_group([sequence("a"), empty])

        self.assertEqual(result.sent, [b"a"])
        self.assertIn("[empty] skipped (no enabled steps)", result.logs)


if __name__ == "__main__":
    unittest.main()
