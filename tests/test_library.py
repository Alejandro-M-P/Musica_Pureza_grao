"""Tests for MusicLibrary — RED phase (tests written first, implementation doesn't exist yet)"""
import unittest
import os
import tempfile
import shutil

# These imports will FAIL until src/library.py is created — that's the RED phase
from src.library import MusicLibrary, MusicFolderError


class TestMusicLibraryScan(unittest.TestCase):
    """Test MusicLibrary.scan() method per spec scenarios."""

    def setUp(self):
        """Create a temp directory with audio files for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        os.makedirs(os.path.join(self.music_base, "cambio"))
        # Create test audio files (empty files, just for extension detection)
        self.test_files = ["zebra.mp3", "alpha.mp3", "beat.wav"]
        for f in self.test_files:
            with open(os.path.join(self.music_base, "cambio", f), "w") as fh:
                fh.write("")  # empty file, just need the name

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_scan_returns_sorted_list_of_audio_files(self):
        """Spec scenario: Scan folder with audio files returns sorted list."""
        library = MusicLibrary(self.music_base)
        result = library.scan("cambio")
        expected = ["alpha.mp3", "beat.wav", "zebra.mp3"]  # sorted
        self.assertEqual(result, expected)

    def test_scan_ignores_non_audio_files(self):
        """Scan should only return supported audio extensions."""
        # Add a non-audio file
        with open(os.path.join(self.music_base, "cambio", "notes.txt"), "w") as fh:
            fh.write("")
        library = MusicLibrary(self.music_base)
        result = library.scan("cambio")
        # Should only have the 3 audio files, not notes.txt
        self.assertEqual(len(result), 3)
        self.assertNotIn("notes.txt", result)

    def test_scan_all_supported_extensions(self):
        """Scan should detect all supported audio formats."""
        extensions = [".mp3", ".wav", ".flac", ".ogg", ".mp4", ".m4a"]
        for i, ext in enumerate(extensions):
            with open(os.path.join(self.music_base, "cambio", f"song{i}{ext}"), "w") as fh:
                fh.write("")
        library = MusicLibrary(self.music_base)
        result = library.scan("cambio")
        # Should have 3 original + 6 new = 9 files
        self.assertEqual(len(result), 9)

    def test_scan_empty_folder_raises_musicfolerro(self):
        """Spec scenario: Empty folder raises MusicFolderError."""
        # Create empty folder
        empty_folder = os.path.join(self.music_base, "entrada")
        os.makedirs(empty_folder)
        library = MusicLibrary(self.music_base)
        with self.assertRaises(MusicFolderError) as cm:
            library.scan("entrada")
        self.assertIn("empty or no audio files", str(cm.exception))

    def test_scan_missing_folder_raises_musicfolerro(self):
        """Spec scenario: Missing folder raises MusicFolderError."""
        library = MusicLibrary(self.music_base)
        with self.assertRaises(MusicFolderError) as cm:
            library.scan("nonexistent")
        self.assertIn("empty or no audio files", str(cm.exception))


class TestMusicLibraryValidateFolder(unittest.TestCase):
    """Test MusicLibrary.validate_folder() method."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        os.makedirs(os.path.join(self.music_base, "cambio"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_validate_folder_with_audio_files_returns_true(self):
        """validate_folder returns True when folder has audio files."""
        with open(os.path.join(self.music_base, "cambio", "test.mp3"), "w") as fh:
            fh.write("")
        library = MusicLibrary(self.music_base)
        self.assertTrue(library.validate_folder("cambio"))

    def test_validate_folder_empty_returns_false(self):
        """validate_folder returns False when folder is empty."""
        library = MusicLibrary(self.music_base)
        self.assertFalse(library.validate_folder("cambio"))

    def test_validate_folder_missing_returns_false(self):
        """validate_folder returns False when folder doesn't exist."""
        library = MusicLibrary(self.music_base)
        self.assertFalse(library.validate_folder("nonexistent"))


if __name__ == "__main__":
    unittest.main()
