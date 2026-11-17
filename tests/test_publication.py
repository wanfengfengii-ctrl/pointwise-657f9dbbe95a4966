from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from delivery.app import WaterQualityApp
from tests.reference import DAY, rows, snapshot, independent_contrast
from archive.schema import UnknownResult


class TestPublication(unittest.TestCase):
    def test_failure_and_retry(self):
        for kind in ("analysis", "report"):
            for stage in ("before_insert", "after_insert", "before_commit"):
                with self.subTest(kind=kind,stage=stage), TemporaryDirectory() as directory:
                    database = Path(directory) / "publish.sqlite"
                    with WaterQualityApp.open(database) as app:
                        revision = app.put_series("water","v1","mg/L",rows(DAY))
                        old_task = app.create_analysis(revision,4,2,2)
                        old_analysis = app.execute_analysis(old_task)
                        old_report = app.report_contrast(old_analysis,0)
                        old_value = app.read_result(old_report)
                        task = app.create_analysis(revision,4,2,2)
                        analysis = app.execute_analysis(task) if kind == "report" else None
                        before = snapshot(app)
                        observed_ids = []
                        with WaterQualityApp.open(database) as observer:
                            def fail_at(actual_stage, actual_kind):
                                if actual_stage == stage and actual_kind == kind:
                                    self.assertEqual(snapshot(observer), before)
                                    staged = app.store.connection.execute(
                                        "SELECT id FROM records WHERE namespace='artifact'").fetchall()
                                    observed_ids.extend(record_id for (record_id,) in staged
                                                        if record_id not in {
                                                            row[1] for row in before[0]})
                                    raise RuntimeError("deterministic publication failure")
                            app.publications.fault_hook = fail_at
                            with self.assertRaisesRegex(RuntimeError, "publication failure"):
                                if kind == "analysis":
                                    app.execute_analysis(task)
                                else:
                                    app.report_contrast(analysis,1)
                        self.assertEqual(snapshot(app), before)
                        self.assertEqual(app.read_result(old_report), old_value)
                        for missing in observed_ids:
                            with self.assertRaises(UnknownResult):
                                app.read_result(missing)
                    with WaterQualityApp.open(database) as reopened:
                        self.assertEqual(snapshot(reopened), before)
                        self.assertEqual(reopened.read_result(old_report), old_value)
                        if kind == "analysis":
                            retry = reopened.execute_analysis(task)
                            self.assertEqual(reopened.read_result(retry)["data"],
                                             reopened.read_result(old_analysis)["data"])
                            self.assertEqual(reopened.execute_analysis(task), retry)
                        else:
                            retry = reopened.report_contrast(analysis,1)
                            value = reopened.read_result(retry)["data"]["result"]
                            leaves = reopened.read_result(analysis)["data"]["leaves"]
                            _, z, variance, p = independent_contrast(DAY,leaves,1,4)
                            self.assertEqual(value["z"],z)
                            self.assertEqual(value["normal"]["variance"],variance)
                            self.assertAlmostEqual(value["normal"]["p"],p,delta=1e-12)
                            self.assertEqual(reopened.report_contrast(analysis,1),retry)
                            self.assertTrue(reopened.export_report(retry))
