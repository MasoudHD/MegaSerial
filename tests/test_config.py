"""Characterization tests for current global config-file behavior."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from MegaSerial import config


class ConfigPersistenceTests(unittest.TestCase):
    def _instances_from(self, path: Path) -> tuple[dict, dict, dict, dict]:
        with patch.object(config, "config_path", return_value=path):
            first = config.load()
            second = config.load()
        return first, deepcopy(first), second, deepcopy(second)

    def test_no_config_file_returns_the_declared_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing-config.json"
            with patch.object(config, "config_path", return_value=path):
                loaded = config.load()

        self.assertEqual(loaded, config.DEFAULTS)
        self.assertFalse(loaded.get("show_line_numbers", False))
        self.assertFalse(loaded.get("clear_after_send", False))

    def test_line_number_and_clear_after_send_are_declared_defaults(self):
        self.assertIs(config.DEFAULTS["show_line_numbers"], False)
        self.assertIs(config.DEFAULTS["clear_after_send"], False)

    def test_partial_config_overrides_only_its_present_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "dark", "baudrate": 9600}), encoding="utf-8")
            with patch.object(config, "config_path", return_value=path):
                loaded = config.load()

        self.assertEqual(loaded["theme"], "dark")
        self.assertEqual(loaded["baudrate"], 9600)
        self.assertEqual(loaded["send_format"], "ASCII")

    def test_malformed_and_non_object_json_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch.object(config, "config_path", return_value=path):
                path.write_text("{not json", encoding="utf-8")
                self.assertEqual(config.load(), config.DEFAULTS)
                path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
                self.assertEqual(config.load(), config.DEFAULTS)

    def test_unknown_top_level_keys_survive_load_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"future_key": {"enabled": True}}), encoding="utf-8")
            with patch.object(config, "config_path", return_value=path):
                loaded = config.load()
                config.save(loaded)
                saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["future_key"], {"enabled": True})
        self.assertEqual(saved["future_key"], {"enabled": True})

    def test_read_oserror_falls_back_to_defaults(self):
        path = MagicMock()
        path.exists.return_value = True
        with patch.object(config, "config_path", return_value=path):
            with patch("builtins.open", side_effect=OSError("denied")):
                self.assertEqual(config.load(), config.DEFAULTS)

    def test_write_oserror_is_silently_ignored(self):
        with patch.object(config, "config_path", return_value=Path("unwritable-config.json")):
            with patch("builtins.open", side_effect=OSError("denied")):
                self.assertIsNone(config.save({"theme": "dark"}))

    def test_line_number_and_clear_after_send_values_round_trip_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            data = dict(config.DEFAULTS)
            data.update({"show_line_numbers": True, "clear_after_send": True})
            with patch.object(config, "config_path", return_value=path):
                config.save(data)
                loaded = config.load()

        self.assertTrue(loaded["show_line_numbers"])
        self.assertTrue(loaded["clear_after_send"])

    def test_two_instances_preserve_independent_changed_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "system", "baudrate": 115200}), encoding="utf-8")
            first, first_snapshot, second, second_snapshot = self._instances_from(path)
            first["theme"] = "dark"
            second["baudrate"] = 9600
            with patch.object(config, "config_path", return_value=path):
                config.save(first, snapshot=first_snapshot)
                config.save(second, snapshot=second_snapshot)
                merged = config.load()

        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(merged["baudrate"], 9600)

    def test_same_key_conflict_is_last_writer_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "system"}), encoding="utf-8")
            first, first_snapshot, second, second_snapshot = self._instances_from(path)
            first["theme"] = "dark"
            second["theme"] = "light"
            with patch.object(config, "config_path", return_value=path):
                config.save(first, snapshot=first_snapshot)
                config.save(second, snapshot=second_snapshot)
                merged = config.load()

        self.assertEqual(merged["theme"], "light")

    def test_unchanged_stale_keys_and_unknown_keys_do_not_overwrite_disk_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "system", "future_key": "keep"}), encoding="utf-8")
            first, first_snapshot, second, second_snapshot = self._instances_from(path)
            first["theme"] = "dark"
            with patch.object(config, "config_path", return_value=path):
                config.save(first, snapshot=first_snapshot)
                config.save(second, snapshot=second_snapshot)
                merged = config.load()

        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(merged["future_key"], "keep")

    def test_collections_are_replaced_as_whole_changed_keys(self):
        for key, original, first_value, second_value in (
            ("shortcuts", [{"name": "Original"}], [{"name": "First"}], [{"name": "Second"}]),
            ("history", [{"text": "Original"}], [{"text": "First"}], [{"text": "Second"}]),
            ("sequence", [{"name": "Original"}], [{"name": "First"}], [{"name": "Second"}]),
            ("sequence_groups", [{"name": "Original"}], [{"name": "First"}], [{"name": "Second"}]),
        ):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps({key: original}), encoding="utf-8")
                first, first_snapshot, second, second_snapshot = self._instances_from(path)
                first[key] = first_value
                second[key] = second_value
                with patch.object(config, "config_path", return_value=path):
                    config.save(first, snapshot=first_snapshot)
                    config.save(second, snapshot=second_snapshot)
                    merged = config.load()

                self.assertEqual(merged[key], second_value)

    def test_atomic_save_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch.object(config, "config_path", return_value=path):
                config.save({"theme": "dark", "future_key": True})
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved, {"theme": "dark", "future_key": True})

    def test_write_failure_keeps_previous_json_and_releases_the_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = {"theme": "dark"}
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(config, "config_path", return_value=path):
                with patch.object(config.os, "replace", side_effect=OSError("replace failed")):
                    config.save({"theme": "light"})
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)
                with config._ConfigLock(path, timeout_s=0):
                    pass

            self.assertEqual(list(Path(directory).glob(".config.json.*.tmp")), [])

    def test_single_instance_save_without_snapshot_remains_a_full_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"old_key": "discarded"}), encoding="utf-8")
            with patch.object(config, "config_path", return_value=path):
                config.save({"theme": "dark"})
                saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved, {"theme": "dark"})


if __name__ == "__main__":
    unittest.main()
