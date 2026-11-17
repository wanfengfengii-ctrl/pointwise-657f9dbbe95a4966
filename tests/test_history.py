from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from tests.reference import DAY, rows, snapshot
from delivery.app import WaterQualityApp


class TestHistory(unittest.TestCase):
    def test_correction_reopen_and_object_isolation(self):
        with TemporaryDirectory(prefix="quality-history-") as directory:
            database = Path(directory) / "history.sqlite"
            with WaterQualityApp.open(database) as app:
                supplied = rows(DAY)
                revision = app.put_series("water", "v1", "mg/L", supplied)
                task = app.create_analysis(revision, 4, 2, 2)
                analysis = app.execute_analysis(task)
                report = app.report_contrast(analysis, 0)
                old_analysis = app.read_result(analysis)
                old_report = app.read_result(report)
                old_package = app.export_report(report)
                supplied[4]["value"] = 999
                altered = app.read_result(analysis)
                altered["data"]["leaves"][0]["total"] = -999
                altered["data"]["request"]["noise_variance"] = 100
                altered_report = app.read_result(report)
                altered_report["data"]["result"]["vector"]["coefficients"] = ()
                altered_package = app.export_report(report)
                altered_package["manifest"]["revision_id"] = "changed"
                self.assertEqual(app.read_result(analysis), old_analysis)
                self.assertEqual(app.read_result(report), old_report)
                self.assertEqual(app.export_report(report), old_package)
                correction = DAY.copy()
                correction[4] = 8
                child = app.put_series("water", "v2", "mg/L", rows(correction), revision)
                child_task = app.create_analysis(child, 1, 2, 2)
                app.execute_analysis(child_task)
                before_reopen = snapshot(app)
                app.store.initialize()
                self.assertEqual(snapshot(app), before_reopen)
            with WaterQualityApp.open(database) as app:
                self.assertEqual(snapshot(app), before_reopen)
                self.assertEqual(app.revisions.get(child).values[4], 8)
                self.assertEqual(app.revisions.get(revision).values[4], 7)
                previous = sys.getprofile()
                def prohibit_recalculation(frame, event, arg):
                    if event == "call" and frame.f_code.co_name in {
                            "run_greedy", "build_report", "compute_unadjusted",
                            "two_sided_normal_p"}:
                        raise AssertionError("historical read attempted recalculation")
                sys.setprofile(prohibit_recalculation)
                try:
                    self.assertEqual(app.read_result(analysis), old_analysis)
                    self.assertEqual(app.read_result(report), old_report)
                finally:
                    sys.setprofile(previous)
                self.assertEqual(app.execute_analysis(task), analysis)
                self.assertEqual(app.report_contrast(analysis,0), report)
                self.assertEqual(app.export_report(report), old_package)
