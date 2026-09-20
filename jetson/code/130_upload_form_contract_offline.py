#!/usr/bin/env python3
"""실제 HTTP 요청 없이 VadCLIP 점수 multipart 계약을 검증한다."""

import os
import unittest

os.environ["UPLOAD_MODE"] = "B"

import uploader


class UploadFormContractTests(unittest.TestCase):
    def test_runtime_mode_is_b(self):
        self.assertEqual(uploader.UPLOAD_MODE, "B")

    def test_none_omits_anomaly_score(self):
        self.assertEqual(
            uploader._build_form_data(None),
            {"drone_id": uploader.DRONE_ID},
        )

    def test_real_zero_is_preserved(self):
        self.assertEqual(
            uploader._build_form_data(0.0),
            {"drone_id": uploader.DRONE_ID, "anomaly_score": "0.0"},
        )

    def test_vadclip_score_is_preserved(self):
        self.assertEqual(
            uploader._build_form_data(0.4073)["anomaly_score"],
            "0.4073",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
