"""StateManager — persistent JSON state with atomic writes and corruption recovery."""

import json
import os
import shutil
import tempfile
import time


class StateManager:
    """Persistent state storage in JSON format."""

    STATE_DIR = "/home/admins/colegio/state"
    STATE_FILE = f"{STATE_DIR}/carousel.json"

    def load(self) -> dict:
        """Load state dict. Returns empty dict if missing/corrupt.

        On corruption: backups corrupt file, returns empty dict.
        """
        if not os.path.exists(self.STATE_FILE):
            return {}

        try:
            with open(self.STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            # Backup corrupt file
            timestamp = int(time.time())
            backup_path = f"{self.STATE_FILE}.corrupt.{timestamp}"
            shutil.copy2(self.STATE_FILE, backup_path)
            # Remove the corrupt file so save() can create a fresh one
            os.remove(self.STATE_FILE)
            return {}

    def save(self, state: dict) -> None:
        """Write state atomically (write-temp, rename)."""
        os.makedirs(self.STATE_DIR, exist_ok=True)

        # Write to temp file first
        temp_file = f"{self.STATE_FILE}.tmp.{int(time.time() * 1000000)}"
        try:
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)

            # Atomic rename (replace destination)
            os.replace(temp_file, self.STATE_FILE)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    def get_folder_state(self, music_type: str) -> dict:
        """Get state for specific folder.

        Returns dict with queue, last_played, last_played_time.
        """
        state = self.load()
        return state.get(music_type, {
            "queue": [],
            "last_played": None,
            "last_played_time": None
        })

    def update_folder_state(self, music_type: str, **kwargs) -> None:
        """Update state fields for folder and persist."""
        state = self.load()
        if music_type not in state:
            state[music_type] = {
                "queue": [],
                "last_played": None,
                "last_played_time": None
            }

        state[music_type].update(kwargs)
        self.save(state)

    # Schedule management (horarios de timbre)
    DEFAULT_SCHEDULE = {
        "entrada": ["08:05", "15:15"],
        "cambio": ["09:00", "09:55", "12:00", "12:55", "16:10"],
        "recreo": ["10:45", "11:05"],
        "salida": ["13:50", "17:05"],
    }

    def get_schedule(self) -> dict:
        """Get full schedule (music_type -> list of times)."""
        state = self.load()
        schedule = state.get("schedule")
        if not schedule:
            # Initialize with defaults if not present
            schedule = self.DEFAULT_SCHEDULE.copy()
            self.update_schedule(schedule)
        return schedule

    def get_schedule_times(self, music_type: str) -> list[str]:
        """Get times for a specific music type."""
        schedule = self.get_schedule()
        return schedule.get(music_type, [])

    def update_schedule(self, new_schedule: dict) -> None:
        """Update full schedule and persist."""
        state = self.load()
        state["schedule"] = new_schedule
        self.save(state)

    def update_schedule_times(self, music_type: str, times: list[str]) -> None:
        """Update times for specific music type."""
        schedule = self.get_schedule()
        schedule[music_type] = times
        self.update_schedule(schedule)
