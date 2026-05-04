"""Tests for CronHelper — RED phase (tests written first, implementation doesn't exist yet)"""
import unittest
import os
import tempfile
import shutil
import subprocess
from unittest.mock import patch, MagicMock


class TestCronHelperBELL_TIMES(unittest.TestCase):
    """Test BELL_TIMES mapping in CronHelper."""

    def test_bell_times_has_correct_structure(self):
        """BELL_TIMES dict has all 4 music types with correct times."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        bell_times = helper.BELL_TIMES

        # Check all 4 types exist
        self.assertIn("entrada", bell_times)
        self.assertIn("cambio", bell_times)
        self.assertIn("recreo", bell_times)
        self.assertIn("salida", bell_times)

    def test_bell_times_entrada_has_two_entries(self):
        """entrada plays at 8:05 and 15:15."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        entrada_times = helper.BELL_TIMES["entrada"]

        self.assertEqual(len(entrada_times), 2)
        self.assertIn("8:05", entrada_times)
        self.assertIn("15:15", entrada_times)

    def test_bell_times_cambio_has_five_entries(self):
        """cambio plays at 9:00, 9:55, 12:00, 12:55, 16:10."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        cambio_times = helper.BELL_TIMES["cambio"]

        self.assertEqual(len(cambio_times), 5)
        self.assertIn("9:00", cambio_times)
        self.assertIn("9:55", cambio_times)
        self.assertIn("12:00", cambio_times)
        self.assertIn("12:55", cambio_times)
        self.assertIn("16:10", cambio_times)

    def test_bell_times_recreo_has_two_entries(self):
        """recreo plays at 10:45 and 11:05."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        recreo_times = helper.BELL_TIMES["recreo"]

        self.assertEqual(len(recreo_times), 2)
        self.assertIn("10:45", recreo_times)
        self.assertIn("11:05", recreo_times)

    def test_bell_times_salida_has_two_entries(self):
        """salida plays at 13:50 and 17:05."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        salida_times = helper.BELL_TIMES["salida"]

        self.assertEqual(len(salida_times), 2)
        self.assertIn("13:50", salida_times)
        self.assertIn("17:05", salida_times)


class TestCronHelperGenerateCrontab(unittest.TestCase):
    """Test generate_crontab() returns correct 11 entries."""

    def test_generate_crontab_returns_string(self):
        """generate_crontab() returns a string."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        self.assertIsInstance(crontab, str)

    def test_generate_crontab_has_11_entries(self):
        """generate_crontab() returns exactly 11 cron entries (excluding comments/blank lines)."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        # Count only actual cron entries (lines starting with a digit for minute)
        lines = [line for line in crontab.strip().split('\n') if line.strip() and line.strip()[0].isdigit()]
        self.assertEqual(len(lines), 11)

    def test_generate_crontab_includes_display_and_xdg_vars(self):
        """Each entry includes DISPLAY=:0 and XDG_RUNTIME_DIR."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        self.assertIn("DISPLAY=:0", crontab)
        self.assertIn("XDG_RUNTIME_DIR=/run/user/1000", crontab)

    def test_generate_crontab_calls_bell_py_with_python3(self):
        """Each entry calls bell.py using python3."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        # Should call bell.py via python3
        self.assertIn("python3 bell.py", crontab)

    def test_generate_crontab_has_correct_time_format(self):
        """Cron entries have correct minute and hour format."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        # Check a few specific entries
        self.assertIn("5 8", crontab)    # 8:05
        self.assertIn("0 9", crontab)    # 9:00
        self.assertIn("55 9", crontab)   # 9:55
        self.assertIn("45 10", crontab)  # 10:45
        self.assertIn("5 11", crontab)   # 11:05
        self.assertIn("0 12", crontab)   # 12:00
        self.assertIn("55 12", crontab)  # 12:55
        self.assertIn("50 13", crontab)  # 13:50
        self.assertIn("15 15", crontab)  # 15:15
        self.assertIn("10 16", crontab)  # 16:10
        self.assertIn("5 17", crontab)   # 17:05

    def test_generate_crontab_calls_bell_with_correct_type(self):
        """Each entry calls bell.py with correct music type."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        crontab = helper.generate_crontab()

        self.assertIn("bell.py entrada", crontab)
        self.assertIn("bell.py cambio", crontab)
        self.assertIn("bell.py recreo", crontab)
        self.assertIn("bell.py salida", crontab)


class TestCronHelperSetup(unittest.TestCase):
    """Test setup() adds entries to crontab idempotently."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_crontab = ""

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.cron_helper.subprocess.run')
    def test_setup_calls_crontab_l_for_current_entries(self, mock_run):
        """setup() reads current crontab first."""
        from src.cron_helper import CronHelper

        # Mock: first call (crontab -l) fails (no existing crontab), second call succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, 'crontab', stderr="no crontab"),  # No existing crontab
            MagicMock(returncode=0),  # crontab - writes successfully
        ]

        helper = CronHelper()
        helper.setup()

        # Should have called crontab -l first
        self.assertGreaterEqual(mock_run.call_count, 1)
        first_call_args = mock_run.call_args_list[0][0][0]  # First positional arg list
        self.assertEqual(first_call_args[0], "crontab")
        self.assertEqual(first_call_args[1], "-l")

    @patch('src.cron_helper.subprocess.run')
    def test_setup_is_idempotent(self, mock_run):
        """Running setup() twice doesn't duplicate entries."""
        from src.cron_helper import CronHelper

        helper = CronHelper()

        # Mock: crontab -l returns our entries (already installed)
        # This should cause setup() to return early without writing
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="bell.py entrada\nbell.py cambio\n"
        )

        # Call setup twice
        helper.setup()
        helper.setup()

        # Count calls that WRITE to crontab (calls with a file path argument)
        crontab_write_calls = 0
        for call in mock_run.call_args_list:
            args = call[0][0]
            if args[0] == "crontab" and len(args) > 1 and not args[1] == "-l":
                # This is a write call (not -l)
                crontab_write_calls += 1

        # Should NOT have written to crontab (entries already exist)
        self.assertEqual(crontab_write_calls, 0)


class TestCronHelperRemove(unittest.TestCase):
    """Test remove() deletes only our entries from crontab."""

    @patch('src.cron_helper.subprocess.run')
    def test_remove_calls_crontab_l(self, mock_run):
        """remove() reads current crontab."""
        from src.cron_helper import CronHelper

        # Mock: crontab -l returns our entries
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="DISPLAY=:0\nXDG_RUNTIME_DIR=/run/user/1000\n5 8 * * 1-5 cd /home/admins/colegio && python3 bell.py entrada\n",
        )

        helper = CronHelper()
        helper.remove()

        # Should have called crontab -l at least once
        self.assertGreaterEqual(mock_run.call_count, 1)

        # Check first call was crontab -l
        first_call_args = mock_run.call_args_list[0][0][0]
        self.assertEqual(first_call_args[0], "crontab")
        self.assertEqual(first_call_args[1], "-l")

    def test_remove_method_exists(self):
        """remove() method exists and is callable."""
        from src.cron_helper import CronHelper

        helper = CronHelper()
        self.assertTrue(hasattr(helper, 'remove'))
        self.assertTrue(callable(getattr(helper, 'remove')))


if __name__ == "__main__":
    unittest.main()
