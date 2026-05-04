"""MusicPlayer — orchestrates playback for school bell system."""

import subprocess
import logging

from src.library import MusicLibrary, MusicFolderError
from src.carousel import SmartCarousel
from src.state import StateManager

# Configure logger
logger = logging.getLogger(__name__)


class MusicPlayer:
    """Orchestrates music playback for school bell system."""

    def __init__(self, music_base: str = "/home/admins/musica"):
        self.music_base = music_base
        self.library = MusicLibrary(music_base)
        self.state = StateManager()
        self.carousels: dict[str, SmartCarousel] = {}

    def play(self, music_type: str) -> None:
        """Play next song for given music type."""
        try:
            # Validate folder first
            if not self.library.validate_folder(music_type):
                logger.warning(f"Folder missing or empty: {music_type}")
                return

            # Get carousel for this type (lazy-load)
            carousel = self._get_carousel(music_type)

            # Get next song
            song_path = carousel.next_song()

            # Play with mpv
            self._run_mpv(song_path)

            logger.info(f"Played {music_type}/{song_path.split('/')[-1]}")

        except MusicFolderError as e:
            logger.warning(f"Music folder error for {music_type}: {e}")
        except Exception as e:
            logger.error(f"Error playing {music_type}: {e}")

    def _get_carousel(self, music_type: str) -> SmartCarousel:
        """Lazy-load or return cached carousel for music type."""
        if music_type not in self.carousels:
            self.carousels[music_type] = SmartCarousel(
                music_type, self.state, self.music_base
            )
        return self.carousels[music_type]

    def _run_mpv(self, file_path: str) -> int:
        """Execute mpv subprocess with proper args.

        Returns exit code from mpv.
        """
        try:
            result = subprocess.run(
                [
                    "mpv",
                    "--length=35",
                    "--no-terminal",
                    "--really-quiet",
                    file_path,
                ],
                check=False,
                timeout=40,
            )
            return result.returncode
        except FileNotFoundError:
            logger.error("mpv not found in PATH")
            return 1
        except subprocess.TimeoutExpired:
            logger.error(f"mpv timeout for {file_path}")
            return 1
        except Exception as e:
            logger.error(f"mpv failed: {e}")
            return 1
