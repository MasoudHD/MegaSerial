"""Characterization tests for sequence models and CSV persistence."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from MegaSerial import utils
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

    def test_custom_line_ending_builds_the_step_payload_from_the_suffix(self):
        step = Step(data="AT", line_ending=utils.LINE_ENDING_CUSTOM, custom_suffix=r"\r\n\x00")

        self.assertEqual(step.payload_bytes(), b"AT\r\n\x00")

    def test_custom_line_ending_without_a_suffix_appends_nothing(self):
        step = Step(data="AT", line_ending=utils.LINE_ENDING_CUSTOM)

        self.assertEqual(step.payload_bytes(), b"AT")

    def test_invalid_custom_suffix_raises_when_the_payload_is_built(self):
        step = Step(data="AT", line_ending=utils.LINE_ENDING_CUSTOM, custom_suffix=r"\xZZ")

        with self.assertRaises(utils.ParseError):
            step.payload_bytes()

    def test_steps_saved_before_custom_suffix_existed_keep_their_line_ending(self):
        legacy = {"name": "Legacy", "data": "AT", "line_ending": "CRLF (\\r\\n)"}
        step = Step.from_dict(legacy)

        self.assertEqual(step.custom_suffix, "")
        self.assertEqual(step.payload_bytes(), b"AT\r\n")

    def test_dict_round_trip_preserves_the_custom_suffix(self):
        step = Step(name="Ctrl-Z", data="AT",
                    line_ending=utils.LINE_ENDING_CUSTOM, custom_suffix=r"\x1a")
        restored = Step.from_dict(step.to_dict())

        self.assertEqual(restored, step)
        self.assertEqual(restored.payload_bytes(), b"AT\x1a")


class NamedSequenceEnabledTests(unittest.TestCase):
    def test_a_new_sequence_is_enabled_by_default(self):
        self.assertTrue(NamedSequence().enabled)
        self.assertTrue(NamedSequence(name="Init", steps=[Step()]).enabled)

    def test_groups_saved_before_this_field_treat_every_entry_as_enabled(self):
        legacy = {"name": "Legacy", "steps": [{"name": "Ping", "data": "AT"}]}

        restored = NamedSequence.from_dict(legacy)

        self.assertTrue(restored.enabled)
        self.assertEqual(restored.steps[0].name, "Ping")

    def test_enabled_state_round_trips_and_accepts_stored_strings(self):
        for value, expected in ((True, True), (False, False), ("false", False), ("yes", True)):
            with self.subTest(value=value):
                restored = NamedSequence.from_dict(
                    {"name": "Seq", "steps": [], "enabled": value})
                self.assertEqual(restored.enabled, expected)

        original = NamedSequence(name="Off", steps=[Step(name="A")], enabled=False)
        self.assertEqual(NamedSequence.from_dict(original.to_dict()), original)

    def test_disabling_a_sequence_leaves_its_steps_untouched(self):
        sequence = NamedSequence(name="Init", steps=[Step(name="A"), Step(name="B")])

        sequence.enabled = False
        restored = NamedSequence.from_dict(sequence.to_dict())

        self.assertFalse(restored.enabled)
        self.assertTrue(all(step.enabled for step in restored.steps))

    def test_ordering_is_preserved_across_mixed_enabled_entries(self):
        group = [
            NamedSequence(name="first", steps=[Step()], enabled=True),
            NamedSequence(name="second", steps=[Step()], enabled=False),
            NamedSequence(name="third", steps=[Step()], enabled=True),
        ]

        restored = [NamedSequence.from_dict(s.to_dict()) for s in group]

        self.assertEqual([s.name for s in restored], ["first", "second", "third"])
        self.assertEqual([s.enabled for s in restored], [True, False, True])


class SequenceCsvTests(unittest.TestCase):
    def _import_content(self, content: str, *, encoding: str = "utf-8") -> list[Step]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            path.write_text(content, encoding=encoding)
            return steps_from_csv(str(path))

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

    def test_csv_accepts_utf8_bom(self):
        restored = self._import_content("name,data\nPing,AT\n", encoding="utf-8-sig")

        self.assertEqual([(step.name, step.data) for step in restored], [("Ping", "AT")])

    def test_omitted_csv_fields_use_step_defaults(self):
        restored = self._import_content("name,data\nMinimal,AT\n")

        self.assertEqual(restored, [Step(name="Minimal", data="AT")])

    def test_unknown_csv_columns_are_ignored(self):
        restored = self._import_content("name,data,unknown_column\nPing,AT,value\n")

        self.assertEqual(restored, [Step(name="Ping", data="AT")])

    def test_invalid_csv_enum_values_keep_current_fallbacks(self):
        restored = self._import_content(
            "name,fmt,expect_fmt,advance,on_timeout,line_ending\n"
            "Fallback,unsupported,also-unsupported,later,unexpected,Unknown ending\n"
        )

        step = restored[0]
        self.assertEqual(step.fmt, "ASCII")
        self.assertEqual(step.expect_fmt, "ASCII")
        self.assertEqual(step.advance, "time")
        self.assertEqual(step.on_timeout, "unexpected")
        self.assertEqual(step.line_ending, "Unknown ending")

    def test_invalid_csv_integers_use_step_defaults(self):
        restored = self._import_content(
            "name,delay_ms,timeout_ms,max_retries\n"
            "Fallback,not-an-int,also-not-an-int,nope\n"
        )

        step = restored[0]
        self.assertEqual((step.delay_ms, step.timeout_ms, step.max_retries), (1000, 2000, 2))

    def test_csv_boolean_parsing_uses_current_truthy_values_and_defaults(self):
        restored = self._import_content(
            "name,enabled,beep_on_match\n"
            "True values,yes,on\n"
            "False values,false,off\n"
            "Empty values,,\n"
        )

        self.assertEqual(
            [(step.enabled, step.beep_on_match) for step in restored],
            [(True, True), (False, False), (True, False)],
        )

    def test_csv_fail_on_uses_the_expect_format(self):
        restored = self._import_content(
            "name,expect_fmt,fail_on\n"
            "Check,hex,45 52 52 4F 52\n"
        )

        self.assertEqual(restored[0].fail_on, "45 52 52 4F 52")
        self.assertEqual(restored[0].fail_on_bytes(), b"ERROR")

    def test_custom_suffix_round_trips_through_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            steps_to_csv(str(path), [
                Step(name="Custom", data="AT", line_ending=utils.LINE_ENDING_CUSTOM,
                     custom_suffix=r"\x1a"),
            ])
            header = path.read_text(encoding="utf-8").splitlines()[0]
            restored = steps_from_csv(str(path))

        self.assertIn("custom_suffix", header)
        self.assertEqual(restored[0].line_ending, utils.LINE_ENDING_CUSTOM)
        self.assertEqual(restored[0].custom_suffix, r"\x1a")
        self.assertEqual(restored[0].payload_bytes(), b"AT\x1a")

    def test_legacy_csv_without_custom_suffix_still_imports(self):
        restored = self._import_content(
            "name,data,line_ending\n"
            "Legacy,AT,CRLF (\\r\\n)\n"
        )

        self.assertEqual(restored[0].custom_suffix, "")
        self.assertEqual(restored[0].payload_bytes(), b"AT\r\n")


if __name__ == "__main__":
    unittest.main()
