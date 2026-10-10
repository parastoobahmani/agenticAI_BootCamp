from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from problem2_part3.scenarios import main, run_all


class PracticalScenarioTests(unittest.TestCase):
    def test_all_ten_scenarios_pass_with_five_per_split(self):
        report = run_all()
        self.assertEqual(report["total"], 10)
        self.assertEqual(report["passed"], 10)
        self.assertEqual(report["dev_count"], 5)
        self.assertEqual(report["test_count"], 5)
        self.assertEqual({row["split"] for row in report["results"]}, {"dev", "test"})

    def test_report_is_reproducible_and_contains_no_api_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = main(path)
            self.assertTrue(path.is_file())
            self.assertEqual(report["api_calls"], 0)
            self.assertTrue(all(row["designed_followups"] for row in report["results"]))


if __name__ == "__main__":
    unittest.main()
