"""Characterization tests for sequence models and CSV persistence."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from MegaSerial.sequence import (
    ADVANCE_BOTH,
    ON_TIMEOUT_RETRY,
    NamedSequence,
    Step,
    steps_from_csv,
    steps_to_csv,
)


class StepModelTests(unittest.TestCase):
    def test_payload_and_match_patterns_use_the_existing_formats(self):
        step = Step(
            data="41 54",
            fmt="hex",
            line_ending="LF (\\n)",
            expect="OK",
            expect_fmt="ASCII",
            fail_on="ERROR",
        )

        self.assertEqual(step.payload_bytes(), b"AT\n")
        self.assertEqual(step.expect_bytes(), b"OK")
        self.assertEqual(step.fail_on_bytes(), b"ERROR")

    def test_from_dict_coerces_current_csv_style_values_and_keeps_fail_on(self):
        step = Step.from_dict({
            "name": "Configure",
            "fmt": "hex",
            "enabled": "no",
            "advance": ADVANCE_BOTH,
            "delay_ms": "250",
            "timeout_ms": "1500",
            "on_timeout": ON_TIMEOUT_RETRY,
            "max_retries": "3",
            "beep_on_match": "yes",
            "fail_on": "ERROR",
        })

        self.assertEqual(step.fmt, "HEX")
        self.assertFalse(step.enabled)
        self.assertEqual(step.advance, ADVANCE_BOTH)
        self.assertEqual(step.delay_ms, 250)
        self.assertEqual(step.timeout_ms, 1500)
        self.assertEqual(step.max_retries, 3)
        self.assertTrue(step.beep_on_match)
        self.assertEqual(step.fail_on, "ERROR")

    def test_named_sequence_round_trips_steps(self):
        original = NamedSequence(name="Bring up", steps=[Step(name="Ping", fail_on="ERROR")])
        restored = NamedSequence.from_dict(original.to_dict())

        self.assertEqual(restored.name, "Bring up")
        self.assertEqual(restored.steps[0].name, "Ping")
        self.assertEqual(restored.steps[0].fail_on, "ERROR")


class SequenceCsvTests(unittest.TestCase):
    def test_csv_round_trip_preserves_fail_on_and_step_fields(self):
        steps = [
            Step(
                name="Handshake",
                data="PING",
                fmt="ASCII",
                line_ending="CRLF (\\r\\n)",
                advance=ADVANCE_BOTH,
                delay_ms=125,
                expect="PONG",
                expect_fmt="ASCII",
                timeout_ms=900,
                on_timeout=ON_TIMEOUT_RETRY,
                max_retries=4,
                beep_on_match=True,
                fail_on="ERROR",
            )
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            steps_to_csv(str(path), steps)
            restored = steps_from_csv(str(path))

        self.assertEqual([step.to_dict() for step in restored], [step.to_dict() for step in steps])

    def test_csv_skips_rows_without_name_data_or_expect(self):
        content = (
            "name,data,expect,fail_on\n"
            ",,,ERROR\n"
            ",,OK,ERROR\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            path.write_text(content, encoding="utf-8")
            restored = steps_from_csv(str(path))

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].expect, "OK")
        self.assertEqual(restored[0].fail_on, "ERROR")


if __name__ == "__main__":
    unittest.main()
