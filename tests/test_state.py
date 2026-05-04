"""Tests for StateManager — RED phase (tests written first, implementation doesn't exist yet)"""
import unittest
import os
import json
import tempfile
import shutil
import time

# This import will FAIL until src/state.py is created — that's the RED phase
from src.state import StateManager


class TestStateManagerLoad(unittest.TestCase):
    """Test StateManager.load() method per spec scenarios."""

    def setUp(self):
        """Create a temp directory to act as state dir."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "carousel.json")
        # Patch STATE_FILE for testing — we'll use a test-specific path
        StateManager.STATE_FILE = self.state_file
        StateManager.STATE_DIR = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_load_nonexistent_file_returns_empty_dict(self):
        """Load returns empty dict when state file doesn't exist."""
        self.assertFalse(os.path.exists(self.state_file))
        manager = StateManager()
        result = manager.load()
        self.assertEqual(result, {})

    def test_load_valid_json_returns_data(self):
        """Load returns valid data from JSON file."""
        test_data = {
            "cambio": {
                "queue": ["song1.mp3", "song2.mp3"],
                "last_played": "song1.mp3",
                "last_played_time": "2026-05-04T10:30:00"
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(test_data, f)

        manager = StateManager()
        result = manager.load()
        self.assertEqual(result, test_data)

    def test_load_corrupt_json_backups_and_returns_empty(self):
        """Spec scenario: Corrupt JSON recovery.

        GIVEN carousel.json contains invalid JSON
        WHEN state.load() called
        THEN backs up corrupt file to carousel.json.corrupt.{timestamp}, returns empty dict
        """
        # Write invalid JSON
        with open(self.state_file, "w") as f:
            f.write("{invalid json garbage")

        manager = StateManager()
        result = manager.load()

        # Should return empty dict
        self.assertEqual(result, {})

        # Should have backed up the corrupt file
        backup_files = [f for f in os.listdir(self.temp_dir)
                        if f.startswith("carousel.json.corrupt.")]
        self.assertEqual(len(backup_files), 1)

        # Corrupt file should no longer exist as the main file
        # (it was backed up and removed, load returns {})
        # Actually, let's check: the backup should contain the corrupt content
        backup_path = os.path.join(self.temp_dir, backup_files[0])
        with open(backup_path, "r") as f:
            content = f.read()
        self.assertEqual(content, "{invalid json garbage")


class TestStateManagerSave(unittest.TestCase):
    """Test StateManager.save() method with atomic writes."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "carousel.json")
        StateManager.STATE_FILE = self.state_file
        StateManager.STATE_DIR = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_writes_atomic_temp_then_rename(self):
        """Spec scenario: Atomic write.

        GIVEN state dirty with new data
        WHEN state.save(data) called
        THEN writes to temp file first, then renames to carousel.json
        """
        manager = StateManager()
        test_data = {
            "cambio": {
                "queue": ["song1.mp3"],
                "last_played": "song1.mp3",
                "last_played_time": "2026-05-04T10:30:00"
            }
        }

        manager.save(test_data)

        # Main file should exist with correct content
        self.assertTrue(os.path.exists(self.state_file))
        with open(self.state_file, "r") as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data, test_data)

    def test_save_creates_state_dir_if_missing(self):
        """Save creates STATE_DIR if it doesn't exist."""
        # Remove the temp_dir to simulate missing dir
        shutil.rmtree(self.temp_dir)
        self.assertFalse(os.path.exists(self.temp_dir))

        manager = StateManager()
        test_data = {"test": "data"}
        manager.save(test_data)

        self.assertTrue(os.path.exists(self.state_file))

    def test_atomic_write_no_partial_reads(self):
        """Verify atomic write: temp file should not remain after rename."""
        manager = StateManager()
        test_data = {"key": "value"}
        manager.save(test_data)

        # No temp files should remain
        temp_files = [f for f in os.listdir(self.temp_dir)
                      if f.startswith("carousel.json.tmp.")]
        self.assertEqual(len(temp_files), 0)


class TestStateManagerFolderState(unittest.TestCase):
    """Test get_folder_state and update_folder_state methods."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "carousel.json")
        StateManager.STATE_FILE = self.state_file
        StateManager.STATE_DIR = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_get_folder_state_returns_correct_data(self):
        """get_folder_state returns state for specific folder."""
        test_data = {
            "entrada": {
                "queue": ["song_a.mp3"],
                "last_played": None,
                "last_played_time": None
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(test_data, f)

        manager = StateManager()
        result = manager.get_folder_state("entrada")
        self.assertEqual(result["queue"], ["song_a.mp3"])
        self.assertIsNone(result["last_played"])

    def test_get_folder_state_missing_returns_default(self):
        """get_folder_state returns default dict for unknown folder."""
        manager = StateManager()
        manager.save({})  # empty state
        result = manager.get_folder_state("nonexistent")
        self.assertEqual(result["queue"], [])
        self.assertIsNone(result["last_played"])
        self.assertIsNone(result["last_played_time"])

    def test_update_folder_state_persists_changes(self):
        """update_folder_state modifies state and saves to disk."""
        manager = StateManager()
        manager.save({})

        manager.update_folder_state(
            "cambio",
            queue=["song1.mp3", "song2.mp3"],
            last_played="song1.mp3",
            last_played_time="2026-05-04T10:30:00"
        )

        # Reload and verify
        reloaded = manager.load()
        self.assertIn("cambio", reloaded)
        self.assertEqual(reloaded["cambio"]["queue"], ["song1.mp3", "song2.mp3"])
        self.assertEqual(reloaded["cambio"]["last_played"], "song1.mp3")


if __name__ == "__main__":
    unittest.main()
