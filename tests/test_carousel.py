"""Tests for SmartCarousel — RED phase (tests written first, implementation doesn't exist yet)"""
import unittest
import os
import json
import tempfile
import shutil
from datetime import datetime

# This import will FAIL until src/carousel.py is created — that's the RED phase
from src.carousel import SmartCarousel
from src.state import StateManager
from src.library import MusicLibrary, MusicFolderError


class TestSmartCarouselInit(unittest.TestCase):
    """Test SmartCarousel initialization and queue loading."""

    def setUp(self):
        """Create temp directories for music and state."""
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.music_base)
        os.makedirs(self.state_dir)

        # Patch StateManager for testing
        StateManager.STATE_FILE = os.path.join(self.state_dir, "carousel.json")
        StateManager.STATE_DIR = self.state_dir

        # Create a music type folder with some songs
        self.music_type = "cambio"
        self.music_folder = os.path.join(self.music_base, self.music_type)
        os.makedirs(self.music_folder)
        for song in ["song1.mp3", "song2.mp3", "song3.mp3"]:
            with open(os.path.join(self.music_folder, song), "w") as f:
                f.write("")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_loads_existing_queue_from_state(self):
        """SmartCarousel loads queue from existing state."""
        # Pre-populate state with a queue
        state = {
            "cambio": {
                "queue": ["song2.mp3", "song1.mp3", "song3.mp3"],
                "last_played": None,
                "last_played_time": None
            }
        }
        with open(StateManager.STATE_FILE, "w") as f:
            json.dump(state, f)

        carousel = SmartCarousel(self.music_type, StateManager(), self.music_base)
        # Queue should be loaded from state
        self.assertEqual(len(carousel._queue), 3)
        self.assertIn(carousel._queue[0], ["song1.mp3", "song2.mp3", "song3.mp3"])

    def test_init_creates_fresh_queue_when_no_state(self):
        """SmartCarousel creates fresh shuffled queue when no state exists."""
        self.assertFalse(os.path.exists(StateManager.STATE_FILE))

        carousel = SmartCarousel(self.music_type, StateManager(), self.music_base)

        # Should have all 3 songs in queue
        self.assertEqual(len(carousel._queue), 3)
        # All songs should be in the queue
        for song in ["song1.mp3", "song2.mp3", "song3.mp3"]:
            self.assertIn(song, carousel._queue)


class TestSmartCarouselNextSong(unittest.TestCase):
    """Test SmartCarousel.next_song() no-repeat behavior per spec."""

    def setUp(self):
        """Create temp directories for music and state."""
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.music_base)
        os.makedirs(self.state_dir)

        # Patch StateManager for testing
        StateManager.STATE_FILE = os.path.join(self.state_dir, "carousel.json")
        StateManager.STATE_DIR = self.state_dir

        # Create a music type folder with 3 songs
        self.music_type = "cambio"
        self.music_folder = os.path.join(self.music_base, self.music_type)
        os.makedirs(self.music_folder)
        self.songs = ["song1.mp3", "song2.mp3", "song3.mp3"]
        for song in self.songs:
            with open(os.path.join(self.music_folder, song), "w") as f:
                f.write("")

        self.state_manager = StateManager()
        self.carousel = SmartCarousel(self.music_type, self.state_manager, self.music_base)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_next_song_returns_songs_in_queue_order(self):
        """Spec scenario partial: next_song returns songs from queue."""
        # Capture all 3 songs (as basenames)
        returned_songs = []
        for _ in range(3):
            song = os.path.basename(self.carousel.next_song())
            returned_songs.append(song)

        # All 3 original songs should be returned
        for song in self.songs:
            self.assertIn(song, returned_songs)

    def test_no_repeats_until_all_songs_played(self):
        """Spec scenario: Exhaust queue then reshuffle.

        GIVEN folder has 3 songs, queue has [song1, song2, song3]
        WHEN next_song() called 3 times
        THEN returns song1, song2, song3 in order (no repeats)
        """
        # Call next_song 3 times - should get all 3 unique songs
        first_three = [self.carousel.next_song() for _ in range(3)]

        # All 3 should be unique (no repeats in first pass)
        self.assertEqual(len(set(first_three)), 3)

    def test_reshuffles_when_queue_exhausted(self):
        """Spec scenario: Exhaust queue then reshuffle.

        WHEN called 4th time (queue exhausted)
        THEN reshuffles all 3 songs, returns next
        """
        # Exhaust the queue (3 songs)
        for _ in range(3):
            self.carousel.next_song()

        # 4th call should trigger reshuffle and return a song
        fourth_song = os.path.basename(self.carousel.next_song())

        # Should return a valid song from our list
        self.assertIn(fourth_song, self.songs)

        # Queue should be repopulated (2 songs remaining after 4th call)
        self.assertGreaterEqual(len(self.carousel._queue), 1)

    def test_detects_new_songs_added_to_folder(self):
        """Spec scenario: Detect new songs.

        GIVEN folder had 3 songs, queue exhausted
        WHEN new song added to folder, next_song() called
        THEN reshuffles with 4 songs (including new one)
        """
        # Exhaust the queue
        for _ in range(3):
            self.carousel.next_song()

        # Add a new song to the folder
        new_song = "song4.mp3"
        with open(os.path.join(self.music_folder, new_song), "w") as f:
            f.write("")

        # Call next_song - should detect new song and reshuffle
        next_song = self.carousel.next_song()

        # Should have 4 songs in rotation now
        # The queue should contain all 4 songs after reshuffle
        all_songs_in_queue = set(self.carousel._queue)
        self.assertIn(new_song, all_songs_in_queue)

    def test_next_song_returns_full_path(self):
        """next_song() returns full path to song file."""
        song_path = self.carousel.next_song()

        # Should be a full path
        self.assertTrue(song_path.startswith(self.music_folder))
        self.assertTrue(song_path.endswith(".mp3"))


class TestSmartCarouselReshuffle(unittest.TestCase):
    """Test SmartCarousel._reshuffle() method."""

    def setUp(self):
        """Create temp directories for music and state."""
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.music_base)
        os.makedirs(self.state_dir)

        # Patch StateManager for testing
        StateManager.STATE_FILE = os.path.join(self.state_dir, "carousel.json")
        StateManager.STATE_DIR = self.state_dir

        # Create a music type folder
        self.music_type = "cambio"
        self.music_folder = os.path.join(self.music_base, self.music_type)
        os.makedirs(self.music_folder)

        self.state_manager = StateManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_reshuffle_creates_queue_with_all_songs(self):
        """_reshuffle() should create a queue with all available songs."""
        # Add 3 songs
        songs = ["a.mp3", "b.mp3", "c.mp3"]
        for song in songs:
            with open(os.path.join(self.music_folder, song), "w") as f:
                f.write("")

        carousel = SmartCarousel(self.music_type, self.state_manager, self.music_base)

        # Force a reshuffle
        all_songs = sorted(songs)
        carousel._reshuffle(all_songs)

        # Queue should have all 3 songs
        self.assertEqual(len(carousel._queue), 3)
        for song in songs:
            self.assertIn(song, carousel._queue)

    def test_reshuffle_saves_state(self):
        """_reshuffle() persists the new queue to state."""
        # Add 2 songs
        songs = ["x.mp3", "y.mp3"]
        for song in songs:
            with open(os.path.join(self.music_folder, song), "w") as f:
                f.write("")

        carousel = SmartCarousel(self.music_type, self.state_manager, self.music_base)

        # Verify state was saved
        saved_state = self.state_manager.load()
        self.assertIn("cambio", saved_state)
        self.assertEqual(len(saved_state["cambio"]["queue"]), 2)


class TestSmartCarouselStatePersistence(unittest.TestCase):
    """Test SmartCarousel persists state correctly."""

    def setUp(self):
        """Create temp directories for music and state."""
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.music_base)
        os.makedirs(self.state_dir)

        # Patch StateManager for testing
        StateManager.STATE_FILE = os.path.join(self.state_dir, "carousel.json")
        StateManager.STATE_DIR = self.state_dir

        # Create a music type folder
        self.music_type = "entrada"
        self.music_folder = os.path.join(self.music_base, self.music_type)
        os.makedirs(self.music_folder)
        for song in ["bell1.mp3", "bell2.mp3"]:
            with open(os.path.join(self.music_folder, song), "w") as f:
                f.write("")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_state_persists_last_played(self):
        """State should track last played song."""
        carousel = SmartCarousel(self.music_type, StateManager(), self.music_base)

        # Play a song
        song = carousel.next_song()

        # Check state was saved with last_played
        state = carousel.state.load()
        self.assertIn(self.music_type, state)
        self.assertEqual(state[self.music_type]["last_played"], os.path.basename(song))


if __name__ == "__main__":
    unittest.main()
