"""Characterization tests for current .msproj serialization behavior."""
from __future__ import annotations

from datetime import datetime
import tempfile
import unittest
from pathlib import Path

from MegaSerial import project


TS = datetime(2024, 1, 2, 3, 4, 5, 123456)


class ProjectSerializationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
