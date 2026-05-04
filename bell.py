#!/usr/bin/env python3
"""School Bell System CLI — replaces musica.sh with Python application."""

import argparse
import logging
import sys
from datetime import datetime

from src.player import MusicPlayer
from src.cron_helper import CronHelper
from src.library import MusicLibrary
from src.state import StateManager

logger = logging.getLogger(__name__)


def setup_logging(log_file='/var/log/colegio-bell.log'):
    """Configure logging with fallback to project directory if no permission."""
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Try to use the specified log file, fallback to local if no permission
    try:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)
    except PermissionError:
        # Fallback: use state/ directory in project
        local_log = '/home/admins/colegio/state/colegio-bell.log'
        file_handler = logging.FileHandler(local_log)
        handlers.append(file_handler)
        print(f"Warning: No permission for {log_file}, using {local_log}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        handlers=handlers
    )

VALID_MUSIC_TYPES = ["entrada", "cambio", "recreo", "salida"]


def parse_args(args=None):
    """Parse CLI arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="School Bell System — plays music for bell schedule"
    )

    # Positional arg: music type (optional, only when not using flags)
    parser.add_argument(
        "type",
        nargs="?",
        choices=VALID_MUSIC_TYPES,
        help="Music type to play: entrada, cambio, recreo, salida"
    )

    # Optional flags
    parser.add_argument(
        "--setup-cron",
        action="store_true",
        help="Add crontab entries for bell schedule"
    )
    parser.add_argument(
        "--remove-cron",
        action="store_true",
        help="Remove bell system entries from crontab"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show last played and next queued song per type"
    )

    return parser.parse_args(args)


def is_weekend(today=None):
    """Check if today is weekend (Saturday=5, Sunday=6).

    Args:
        today: Optional datetime to check (for testing). If None, uses datetime.now().

    Returns:
        True if weekend, False if weekday.
    """
    if today is None:
        today = datetime.now()
    # weekday(): Monday=0, Sunday=6
    return today.weekday() >= 5


def show_status():
    """Show last played and next queued song per music type."""
    state = StateManager()
    library = MusicLibrary()

    print("=" * 60)
    print("School Bell System — Status")
    print("=" * 60)

    for music_type in VALID_MUSIC_TYPES:
        print(f"\n--- {music_type.upper()} ---")

        # Get state
        folder_state = state.get_folder_state(music_type)

        # Last played
        if folder_state.get("last_played"):
            last_time = folder_state.get("last_played_time", "unknown")
            print(f"  Last played: {folder_state['last_played']}")
            print(f"  Played at: {last_time}")
        else:
            print("  Last played: (none)")

        # Next queued
        queue = folder_state.get("queue", [])
        if queue:
            print(f"  Next in queue: {queue[0]} ({len(queue)} remaining)")
        else:
            # Check if folder has songs
            try:
                songs = library.scan(music_type)
                print(f"  Next in queue: (will reshuffle {len(songs)} songs)")
            except Exception:
                print("  Next in queue: (no songs in folder)")

    print("\n" + "=" * 60)


def main(args=None):
    """Main entry point for bell CLI.

    Args:
        args: Command-line arguments (for testing). If None, uses sys.argv.
    """
    setup_logging()  # Configure logging when main runs
    parsed = parse_args(args)

    # Handle --status
    if parsed.status:
        show_status()
        return

    # Handle --setup-cron
    if parsed.setup_cron:
        helper = CronHelper()
        helper.setup()
        return

    # Handle --remove-cron
    if parsed.remove_cron:
        helper = CronHelper()
        helper.remove()
        return

    # Handle music type playback
    if parsed.type:
        # Check weekend
        if is_weekend():
            logger.info("Weekend - no bell")
            print("Weekend - no bell")
            return

        # Play the music type
        player = MusicPlayer()
        player.play(parsed.type)
    else:
        # No argument provided
        print("Error: must specify music type or a flag", file=sys.stderr)
        parse_args(["--help"])
        sys.exit(1)


if __name__ == "__main__":
    main()
