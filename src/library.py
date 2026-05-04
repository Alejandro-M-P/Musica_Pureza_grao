"""MusicLibrary — scans and validates music folders."""

import os


class MusicFolderError(Exception):
    """Raised when music folder is empty or missing."""
    pass


class MusicLibrary:
    """Scans and validates music folders."""

    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".m4a"}

    def __init__(self, base_dir: str = "/home/admins/musica"):
        self.base_dir = base_dir

    def scan(self, music_type: str) -> list[str]:
        """Return sorted list of audio files in folder.

        Raises MusicFolderError if folder empty or missing.
        """
        folder = os.path.join(self.base_dir, music_type)
        if not os.path.isdir(folder):
            raise MusicFolderError("Folder empty or no audio files")

        audio_files = []
        for entry in os.listdir(folder):
            _, ext = os.path.splitext(entry)
            if ext.lower() in self.SUPPORTED_EXTENSIONS:
                audio_files.append(entry)

        if not audio_files:
            raise MusicFolderError("Folder empty or no audio files")

        return sorted(audio_files)

    def validate_folder(self, music_type: str) -> bool:
        """Check folder exists and has audio files."""
        folder = os.path.join(self.base_dir, music_type)
        if not os.path.isdir(folder):
            return False

        for entry in os.listdir(folder):
            _, ext = os.path.splitext(entry)
            if ext.lower() in self.SUPPORTED_EXTENSIONS:
                return True

        return False
