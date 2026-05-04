"""Tests for bell.py CLI — RED phase (tests written first)"""
import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import argparse


class TestBellCLIParseArgs(unittest.TestCase):
    """Test CLI argument parsing."""

    def test_parse_args_valid_music_type_entrada(self):
        """CLI accepts 'entrada' as positional arg."""
        from bell import parse_args

        args = parse_args(["entrada"])

        self.assertEqual(args.type, "entrada")
        self.assertFalse(args.setup_cron)
        self.assertFalse(args.remove_cron)
        self.assertFalse(args.status)

    def test_parse_args_valid_music_type_cambio(self):
        """CLI accepts 'cambio' as positional arg."""
        from bell import parse_args

        args = parse_args(["cambio"])

        self.assertEqual(args.type, "cambio")

    def test_parse_args_valid_music_type_recreo(self):
        """CLI accepts 'recreo' as positional arg."""
        from bell import parse_args

        args = parse_args(["recreo"])

        self.assertEqual(args.type, "recreo")

    def test_parse_args_valid_music_type_salida(self):
        """CLI accepts 'salida' as positional arg."""
        from bell import parse_args

        args = parse_args(["salida"])

        self.assertEqual(args.type, "salida")

    def test_parse_args_invalid_music_type_exits(self):
        """CLI rejects invalid music type."""
        from bell import parse_args

        # Should raise SystemExit due to invalid choice
        with self.assertRaises(SystemExit):
            parse_args(["invalid"])

    def test_parse_args_setup_cron_flag(self):
        """CLI accepts --setup-cron flag."""
        from bell import parse_args

        args = parse_args(["--setup-cron"])

        self.assertTrue(args.setup_cron)
        self.assertIsNone(args.type)

    def test_parse_args_remove_cron_flag(self):
        """CLI accepts --remove-cron flag."""
        from bell import parse_args

        args = parse_args(["--remove-cron"])

        self.assertTrue(args.remove_cron)

    def test_parse_args_status_flag(self):
        """CLI accepts --status flag."""
        from bell import parse_args

        args = parse_args(["--status"])

        self.assertTrue(args.status)

    def test_parse_args_help_flag(self):
        """CLI accepts --help flag."""
        from bell import parse_args

        with self.assertRaises(SystemExit):
            parse_args(["--help"])


class TestBellCLIWeekendCheck(unittest.TestCase):
    """Test weekend skip logic per spec requirement."""

    def test_is_weekend_saturday_returns_true(self):
        """Saturday should be detected as weekend."""
        from bell import is_weekend
        from datetime import datetime

        # Pass Saturday directly
        saturday = datetime(2026, 5, 9)  # Saturday May 9, 2026
        result = is_weekend(today=saturday)
        self.assertTrue(result)

    def test_is_weekend_sunday_returns_true(self):
        """Sunday should be detected as weekend."""
        from bell import is_weekend
        from datetime import datetime

        # Pass Sunday directly
        sunday = datetime(2026, 5, 10)  # Sunday May 10, 2026
        result = is_weekend(today=sunday)
        self.assertTrue(result)

    def test_is_weekend_friday_returns_false(self):
        """Friday should NOT be detected as weekend."""
        from bell import is_weekend
        from datetime import datetime

        # Pass Friday directly
        friday = datetime(2026, 5, 8)  # Friday May 8, 2026
        result = is_weekend(today=friday)
        self.assertFalse(result)

    def test_is_weekend_monday_returns_false(self):
        """Monday should NOT be detected as weekend."""
        from bell import is_weekend
        from datetime import datetime

        # Pass Monday directly
        monday = datetime(2026, 5, 4)  # Monday May 4, 2026 (today)
        result = is_weekend(today=monday)
        self.assertFalse(result)


class TestBellCLIMainFlow(unittest.TestCase):
    """Test main flow with weekend check and playback."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.music_base = os.path.join(self.temp_dir, "musica")
        os.makedirs(self.music_base)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch('bell.is_weekend')
    @patch('bell.MusicPlayer')
    def test_main_weekend_skip_logs_message(self, mock_player_class, mock_is_weekend):
        """On weekend, main() skips playback and logs 'Weekend - no bell'."""
        from bell import main
        from bell import logger

        mock_is_weekend.return_value = True

        with patch.object(logger, 'info') as mock_info:
            main(["cambio"])

            # Should log weekend skip message
            mock_info.assert_called_with("Weekend - no bell")

    @patch('bell.is_weekend')
    @patch('bell.MusicPlayer')
    def test_main_weekend_does_not_play(self, mock_player_class, mock_is_weekend):
        """On weekend, main() does NOT call player.play()."""
        from bell import main

        mock_is_weekend.return_value = True
        mock_player = MagicMock()
        mock_player_class.return_value = mock_player

        main(["cambio"])

        # Should NOT play
        mock_player.play.assert_not_called()

    @patch('bell.is_weekend')
    @patch('bell.MusicPlayer')
    def test_main_weekday_calls_play(self, mock_player_class, mock_is_weekend):
        """On weekday, main() calls player.play() with music type."""
        from bell import main

        mock_is_weekend.return_value = False
        mock_player = MagicMock()
        mock_player_class.return_value = mock_player

        main(["cambio"])

        # Should play
        mock_player.play.assert_called_once_with("cambio")

    @patch('bell.CronHelper')
    def test_main_setup_cron_calls_helper(self, mock_helper_class):
        """--setup-cron calls CronHelper.setup()."""
        from bell import main

        mock_helper = MagicMock()
        mock_helper_class.return_value = mock_helper

        main(["--setup-cron"])

        mock_helper.setup.assert_called_once()

    @patch('bell.CronHelper')
    def test_main_remove_cron_calls_helper(self, mock_helper_class):
        """--remove-cron calls CronHelper.remove()."""
        from bell import main

        mock_helper = MagicMock()
        mock_helper_class.return_value = mock_helper

        main(["--remove-cron"])

        mock_helper.remove.assert_called_once()


class TestBellCLIStatus(unittest.TestCase):
    """Test --status command."""

    @patch('bell.StateManager')
    @patch('bell.MusicLibrary')
    def test_status_shows_last_played_and_next(self, mock_library_class, mock_state_class):
        """--status prints last played and next queued per type."""
        from bell import main

        # Mock state
        mock_state = MagicMock()
        mock_state.get_folder_state.return_value = {
            "last_played": "song1.mp3",
            "last_played_time": "2026-05-04T10:00:00",
            "queue": ["song2.mp3", "song3.mp3"]
        }
        mock_state_class.return_value = mock_state

        # Mock library
        mock_library = MagicMock()
        mock_library.scan.return_value = ["song1.mp3", "song2.mp3", "song3.mp3"]
        mock_library_class.return_value = mock_library

        with patch('builtins.print') as mock_print:
            main(["--status"])

            # Should print something for each type
            self.assertTrue(mock_print.called)


if __name__ == "__main__":
    unittest.main()
