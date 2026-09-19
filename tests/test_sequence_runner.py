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
        ADVANCE_RESPONSE, ADVANCE_TIME, LOOP_COUNT, LOOP_FOREVER, LOOP_NONE,
        LOOP_UNTIL_RX, NamedSequence, ON_TIMEOUT_RETRY, ON_TIMEOUT_STOP, RxMonitor,
        SequenceGroupRunner, SequenceLoop, SequenceRunner, Step,
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


class SequenceRunResult:
    def __init__(self, rx: RxMonitor | None = None, feed_after: int | None = None,
                 feed: bytes = b""):
        self.rx = rx or RxMonitor()
        self.sent: list[bytes] = []
        self.logs: list[str] = []
        self.results: list[tuple[int, str]] = []
        self.completed: bool | None = None
        self._feed_after = feed_after
        self._feed = feed

    def send(self, payload: bytes) -> bool:
        self.sent.append(payload)
        if self._feed_after is not None and len(self.sent) == self._feed_after:
            self.rx.feed(self._feed)
        return True


def run_sequence(steps, loop=None, result: SequenceRunResult | None = None,
                 runner_hook=None) -> SequenceRunResult:
    result = result or SequenceRunResult()
    runner = SequenceRunner(steps, result.send, result.rx, loop=loop)
    runner.log.connect(lambda msg, _kind: result.logs.append(msg))
    runner.step_result.connect(lambda i, status, _d: result.results.append((i, status)))
    runner.finished_all.connect(lambda ok: setattr(result, "completed", ok))
    if runner_hook:
        runner_hook(runner)
    runner.run()
    return result


class SequenceLoopModelTests(unittest.TestCase):
    def test_a_sequence_without_loop_metadata_runs_once(self):
        self.assertEqual(NamedSequence().loop, SequenceLoop())
        self.assertEqual(SequenceLoop().mode, LOOP_NONE)
        self.assertFalse(SequenceLoop().repeats)

        legacy = NamedSequence.from_dict({"name": "Legacy", "steps": []})
        self.assertEqual(legacy.loop.mode, LOOP_NONE)

    def test_invalid_modes_and_repeat_counts_are_normalized(self):
        self.assertEqual(SequenceLoop(mode="sideways").mode, LOOP_NONE)
        self.assertEqual(SequenceLoop(mode=LOOP_COUNT, count=0).count, 1)
        self.assertEqual(SequenceLoop(mode=LOOP_COUNT, count=-7).count, 1)
        self.assertEqual(SequenceLoop(mode=LOOP_COUNT, count="not a number").count, 1)
        self.assertEqual(SequenceLoop(delay_ms=-1).delay_ms, 0)

    def test_termination_pattern_uses_the_selected_format(self):
        ascii_loop = SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="READY")
        hex_loop = SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="52 45 41 44 59",
                                until_rx_fmt="hex")

        self.assertEqual(ascii_loop.until_rx_bytes(), b"READY")
        self.assertEqual(hex_loop.until_rx_bytes(), b"READY")
        # Other modes never carry a pattern.
        self.assertEqual(SequenceLoop(mode=LOOP_FOREVER, until_rx="X").until_rx_bytes(), b"")

    def test_loop_config_round_trips_through_a_dict(self):
        loop = SequenceLoop(mode=LOOP_UNTIL_RX, count=4, until_rx="OK",
                            until_rx_fmt="HEX", delay_ms=250)

        self.assertEqual(SequenceLoop.from_dict(loop.to_dict()), loop)

    def test_named_sequence_round_trips_its_loop(self):
        original = NamedSequence(name="Poll", steps=[step("a")],
                                 loop=SequenceLoop(mode=LOOP_COUNT, count=3, delay_ms=10))

        self.assertEqual(NamedSequence.from_dict(original.to_dict()), original)


class SequenceLoopExecutionTests(unittest.TestCase):
    def test_no_loop_runs_the_sequence_exactly_once(self):
        for loop in (None, SequenceLoop()):
            with self.subTest(loop=loop):
                result = run_sequence([step("a"), step("b")], loop=loop)
                self.assertEqual(result.sent, [b"a", b"b"])
                self.assertTrue(result.completed)

    def test_count_of_one_runs_the_sequence_once(self):
        result = run_sequence([step("a")], loop=SequenceLoop(mode=LOOP_COUNT, count=1))

        self.assertEqual(result.sent, [b"a"])
        self.assertTrue(result.completed)

    def test_count_greater_than_one_repeats_the_whole_sequence(self):
        result = run_sequence([step("a"), step("b")],
                              loop=SequenceLoop(mode=LOOP_COUNT, count=3))

        self.assertEqual(result.sent, [b"a", b"b"] * 3)
        self.assertTrue(result.completed)

    def test_until_rx_repeats_until_the_pattern_arrives(self):
        result = SequenceRunResult(feed_after=3, feed=b"READY\r\n")
        run_sequence([step("poll")],
                     loop=SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="READY"),
                     result=result)

        self.assertEqual(result.sent, [b"poll"] * 3)
        self.assertTrue(result.completed)
        self.assertTrue(any("Loop ended" in msg for msg in result.logs))

    def test_until_rx_matches_a_pattern_split_across_received_chunks(self):
        result = SequenceRunResult()

        def send(payload: bytes) -> bool:
            result.sent.append(payload)
            # "READY" only exists once both chunks have arrived.
            result.rx.feed(b"REA" if len(result.sent) == 1 else b"DY")
            return True

        result.send = send
        run_sequence([step("poll")],
                     loop=SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="READY"),
                     result=result)

        self.assertEqual(result.sent, [b"poll", b"poll"])
        self.assertTrue(result.completed)

    def test_until_rx_ignores_data_received_before_the_run_started(self):
        result = SequenceRunResult(feed_after=2, feed=b"READY")
        result.rx.feed(b"READY from an earlier run")

        run_sequence([step("poll")],
                     loop=SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="READY"),
                     result=result)

        self.assertEqual(result.sent, [b"poll", b"poll"])

    def test_until_rx_without_a_pattern_runs_once_instead_of_forever(self):
        result = run_sequence([step("a")], loop=SequenceLoop(mode=LOOP_UNTIL_RX))

        self.assertEqual(result.sent, [b"a"])
        self.assertTrue(result.completed)

    def test_an_invalid_termination_pattern_stops_before_sending_anything(self):
        result = run_sequence(
            [step("a")],
            loop=SequenceLoop(mode=LOOP_UNTIL_RX, until_rx="ZZ", until_rx_fmt="HEX"))

        self.assertEqual(result.sent, [])
        self.assertFalse(result.completed)
        self.assertTrue(any("Invalid loop termination pattern" in m for m in result.logs))

    def test_forever_keeps_running_until_stop_is_requested(self):
        result = SequenceRunResult()
        holder = {}

        def send(payload: bytes) -> bool:
            result.sent.append(payload)
            if len(result.sent) == 5:
                holder["runner"].request_stop()
            return True

        result.send = send
        run_sequence([step("a")], loop=SequenceLoop(mode=LOOP_FOREVER),
                     result=result, runner_hook=lambda r: holder.__setitem__("runner", r))

        self.assertEqual(result.sent, [b"a"] * 5)
        self.assertFalse(result.completed)

    def test_cancelling_a_counted_loop_stops_it_early(self):
        result = SequenceRunResult()
        holder = {}

        def send(payload: bytes) -> bool:
            result.sent.append(payload)
            if len(result.sent) == 2:
                holder["runner"].request_stop()
            return True

        result.send = send
        run_sequence([step("a")], loop=SequenceLoop(mode=LOOP_COUNT, count=100),
                     result=result, runner_hook=lambda r: holder.__setitem__("runner", r))

        self.assertEqual(result.sent, [b"a"] * 2)
        self.assertFalse(result.completed)

    def test_a_step_that_stops_the_sequence_is_not_retried_by_the_loop(self):
        failing = Step(name="expect", data="go", line_ending="None",
                       advance=ADVANCE_RESPONSE, expect="NEVER", timeout_ms=10,
                       on_timeout=ON_TIMEOUT_STOP, max_retries=0)

        result = run_sequence([failing], loop=SequenceLoop(mode=LOOP_COUNT, count=5))

        self.assertEqual(result.sent, [b"go"])
        self.assertFalse(result.completed)
        self.assertEqual(result.results, [(0, "timeout")])

    def test_step_timeout_and_retry_behavior_is_unchanged_inside_a_loop(self):
        retrying = Step(name="expect", data="go", line_ending="None",
                        advance=ADVANCE_RESPONSE, expect="NEVER", timeout_ms=10,
                        on_timeout=ON_TIMEOUT_RETRY, max_retries=2)

        result = run_sequence([retrying], loop=SequenceLoop(mode=LOOP_COUNT, count=2))

        # 3 attempts (1 + 2 retries) per pass, over two passes.
        self.assertEqual(result.sent, [b"go"] * 6)
        self.assertEqual(result.results, [(0, "timeout"), (0, "timeout")])
        self.assertTrue(result.completed)

    def test_a_sequences_own_loop_also_applies_inside_a_group_run(self):
        looped = NamedSequence(name="a", steps=[step("a")],
                               loop=SequenceLoop(mode=LOOP_COUNT, count=3))

        result = run_group([looped, sequence("b")])

        self.assertEqual(result.sent, [b"a", b"a", b"a", b"b"])
        self.assertTrue(result.completed)


if __name__ == "__main__":
    unittest.main()
