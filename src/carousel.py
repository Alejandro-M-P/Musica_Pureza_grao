"""SmartCarousel — shuffle queue that plays all songs before repeating."""

import os
import random
from datetime import datetime


class SmartCarousel:
    """Shuffle queue that plays all songs before repeating.

    Guarantees no repeats until all songs played.
    Reshuffles when queue exhausted.
    Detects new songs added to folder.
    """

    def __init__(self, music_type: str, state_manager, music_base: str):
        self.music_type = music_type
        self.state = state_manager
        self.music_base = music_base
        self._queue: list[str] = []
        self._load_or_init_queue()

    def _load_or_init_queue(self) -> None:
        """Load queue from state or initialize fresh shuffle."""
        folder_state = self.state.get_folder_state(self.music_type)
        saved_queue = folder_state.get("queue", [])

        if saved_queue:
            # Use saved queue from state
            self._queue = saved_queue
        else:
            # Fresh start — scan folder and shuffle
            self._reshuffle_from_folder()

    def _reshuffle_from_folder(self) -> None:
        """Scan folder for songs and reshuffle queue."""
        folder = os.path.join(self.music_base, self.music_type)
        if not os.path.isdir(folder):
            self._queue = []
            return

        # Scan for audio files
        audio_extensions = {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".m4a"}
        songs = []
        for entry in os.listdir(folder):
            _, ext = os.path.splitext(entry)
            if ext.lower() in audio_extensions:
                songs.append(entry)

        if songs:
            self._reshuffle(songs)
        else:
            self._queue = []

    def _reshuffle(self, all_songs: list[str]) -> None:
        """Shuffle all songs into queue, save state."""
        shuffled = all_songs.copy()
        random.shuffle(shuffled)
        self._queue = shuffled

        # Save state
        self.state.update_folder_state(
            self.music_type,
            queue=self._queue,
            last_played=None,
            last_played_time=None
        )

    def next_song(self) -> str:
        """Return next song path. Reshuffles if queue empty.

        Detects new songs added to folder on reshuffle.
        """
        # If queue is empty, reshuffle from folder (detects new songs)
        if not self._queue:
            self._reshuffle_from_folder()

        # Pop first song from queue
        song = self._queue.pop(0)

        # Update state with last played
        self.state.update_folder_state(
            self.music_type,
            queue=self._queue,
            last_played=song,
            last_played_time=datetime.now().isoformat()
        )

        # Return full path
        return os.path.join(self.music_base, self.music_type, song)
