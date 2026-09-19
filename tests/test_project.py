"""Characterization tests for current .msproj serialization behavior."""
from __future__ import annotations

from datetime import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from MegaSerial import project


TS = datetime(2024, 1, 2, 3, 4, 5, 123456)


class ProjectSerializationTests(unittest.TestCase):
    def _load_raw(self, raw: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.msproj"
            path.write_text(json.dumps(raw), encoding="utf-8")
            return project.load_project(path)

    def test_collect_project_data_serializes_datetime_and_bytes_events(self):
        settings = {"theme": "dark", "unknown_future_setting": "kept"}
        events = [
            {"type": "data", "dir": "rx", "ts": TS, "data": b"\x00\xff"},
            {"type": "log", "kind": "info", "ts": TS, "msg": "Connected"},
        ]

        data = project.collect_project_data(
            project_name="Demo", settings=settings, events=events)

        self.assertEqual(data["format_version"], 1)
        self.assertEqual(data["project_name"], "Demo")
        self.assertEqual(data["settings"], settings)
        self.assertEqual(data["events"][0], {
            "type": "data", "dir": "rx", "ts": "2024-01-02T03:04:05.123456",
            "data": "00ff", "data_encoding": "hex",
        })
        self.assertEqual(data["events"][1]["ts"], "2024-01-02T03:04:05.123456")

    def test_save_and_load_round_trip_current_project_shape(self):
        data = project.collect_project_data(
            project_name="Demo",
            settings={"sequence": [], "extra": True},
            events=[{"type": "data", "dir": "tx", "ts": TS, "data": b"AT"}],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.msproj"
            project.save_project(path, data)
            loaded = project.load_project(path)

        self.assertEqual(loaded["project_name"], "Demo")
        self.assertEqual(loaded["settings"], {"sequence": [], "extra": True})
        self.assertEqual(loaded["events"], [
            {"type": "data", "dir": "tx", "ts": TS, "data": b"AT"},
        ])

    def test_load_rejects_newer_project_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "newer.msproj"
            path.write_text('{"format_version": 2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported project format version 2"):
                project.load_project(path)

    def test_missing_lower_and_current_format_versions_are_accepted(self):
        for version in (None, 0, 1):
            with self.subTest(version=version):
                raw = {"project_name": "Demo"}
                if version is not None:
                    raw["format_version"] = version
                loaded = self._load_raw(raw)
                self.assertEqual(loaded["project_name"], "Demo")

    def test_missing_or_non_object_settings_become_empty_dict(self):
        self.assertEqual(self._load_raw({"format_version": 1})["settings"], {})
        self.assertEqual(
            self._load_raw({"format_version": 1, "settings": ["not", "a", "dict"]})["settings"],
            {},
        )

    def test_missing_events_becomes_empty_list(self):
        self.assertEqual(self._load_raw({"format_version": 1})["events"], [])

    def test_unknown_top_level_fields_are_discarded_but_settings_and_events_keep_unknown_fields(self):
        loaded = self._load_raw({
            "format_version": 1,
            "top_level_future_field": "discarded",
            "settings": {"future_setting": {"value": 1}},
            "events": [{"type": "log", "msg": "hello", "future_event_field": True}],
        })

        self.assertNotIn("top_level_future_field", loaded)
        self.assertEqual(loaded["settings"], {"future_setting": {"value": 1}})
        self.assertEqual(loaded["events"], [
            {"type": "log", "msg": "hello", "future_event_field": True},
        ])

    def test_invalid_timestamp_is_replaced_with_current_time(self):
        with patch.object(project, "datetime") as mocked_datetime:
            mocked_datetime.fromisoformat.side_effect = ValueError
            mocked_datetime.now.return_value = TS
            loaded = self._load_raw({
                "format_version": 1,
                "events": [{"type": "log", "ts": "not-a-timestamp", "msg": "hello"}],
            })

        self.assertEqual(loaded["events"][0]["ts"], TS)

    def test_invalid_hex_event_data_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._load_raw({
                "format_version": 1,
                "events": [{"type": "data", "data_encoding": "hex", "data": "not-hex"}],
            })


if __name__ == "__main__":
    unittest.main()
