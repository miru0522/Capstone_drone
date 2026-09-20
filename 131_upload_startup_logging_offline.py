#!/usr/bin/env python3
"""카메라를 열지 않고 분석 업로드 기동 로그 계약을 검증한다."""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import main


class UploadStartupLoggingTests(unittest.TestCase):
    def test_mode_b_logs_info_once_without_warning(self):
        with mock.patch.object(main.logger, "info") as info_log, \
                mock.patch.object(main.logger, "warning") as warning_log:
            main.log_upload_configuration("B", "http://server/analyze-video", "DR-01")

        info_log.assert_called_once_with(
            "분석 업로드 설정: mode=%s, drone_id=%s, url=%s",
            "B",
            "DR-01",
            "http://server/analyze-video",
        )
        warning_log.assert_not_called()

    def test_mode_a_logs_video_only_warning(self):
        with mock.patch.object(main.logger, "info") as info_log, \
                mock.patch.object(main.logger, "warning") as warning_log:
            main.log_upload_configuration("A", "http://server/analyze-video", "DR-01")

        warning_log.assert_called_once_with(
            "분석 업로드 설정: mode=%s, drone_id=%s, url=%s "
            "(영상 전용 구버전 호환 모드)",
            "A",
            "DR-01",
            "http://server/analyze-video",
        )
        info_log.assert_not_called()

    def test_invalid_mode_fails_during_import_before_runtime_initialization(self):
        env = os.environ.copy()
        env["UPLOAD_MODE"] = "invalid"
        result = subprocess.run(
            [sys.executable, "-c", "import uploader"],
            cwd=Path(__file__).resolve().parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "UPLOAD_MODE는 A 또는 B여야 함",
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
