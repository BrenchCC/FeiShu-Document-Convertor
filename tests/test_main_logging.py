import os
import time
import tempfile
import unittest

from main import _cleanup_old_log_files
from main import _new_run_log_path


class TestMainLogging(unittest.TestCase):
    """Tests for runtime log file utilities."""

    def test_new_run_log_path_contains_prefix_and_pid(self) -> None:
        """Generated log path should include prefix and process id.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            first = _new_run_log_path(
                log_dir = temp_dir,
                log_prefix = "knowledge_generator"
            )
            time.sleep(0.001)
            second = _new_run_log_path(
                log_dir = temp_dir,
                log_prefix = "knowledge_generator"
            )

            self.assertTrue(
                os.path.basename(first).startswith("knowledge_generator_")
            )
            self.assertTrue(
                os.path.basename(first).endswith(f"_{os.getpid()}.log")
            )
            self.assertNotEqual(first, second)

    def test_cleanup_old_log_files_keeps_latest_eight(self) -> None:
        """Cleanup should keep only the latest files under same prefix.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            kept_indexes = set()
            for index in range(10):
                path = os.path.join(
                    temp_dir,
                    f"knowledge_generator_20260219_120000_{index}.log"
                )
                with open(path, "w", encoding = "utf-8") as file_obj:
                    file_obj.write("x")
                mtime = 1000 + index
                os.utime(path, (mtime, mtime))
                if index >= 2:
                    kept_indexes.add(index)

            other_path = os.path.join(temp_dir, "another_program.log")
            with open(other_path, "w", encoding = "utf-8") as file_obj:
                file_obj.write("y")

            _cleanup_old_log_files(
                log_dir = temp_dir,
                log_prefix = "knowledge_generator",
                max_files = 8
            )

            remaining = sorted(
                filename
                for filename in os.listdir(temp_dir)
                if filename.startswith("knowledge_generator_")
                and filename.endswith(".log")
            )
            self.assertEqual(len(remaining), 8)
            remaining_indexes = {
                int(filename.rsplit("_", 1)[-1].replace(".log", ""))
                for filename in remaining
            }
            self.assertEqual(remaining_indexes, kept_indexes)
            self.assertTrue(os.path.exists(other_path))


if __name__ == "__main__":
    unittest.main()
