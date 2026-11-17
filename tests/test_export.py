from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import sqlite3
import subprocess
import sys
from tests.reference import AppCase, DAY, independent_greedy, independent_contrast, snapshot
from delivery.app import WaterQualityApp
from delivery.verification import verify_export_package
from archive.codec import (canonical_json, artifact_digest, decode_revision, decode_artifact,
                           encode_task)
from archive.schema import CorruptArtifact, UnknownResult


class TestExport(AppCase):
    def _rewrite(self, app, namespace, record_id, mutate):
        raw = json.loads(app.store.get(namespace,record_id))
        mutate(raw)
        body = canonical_json(raw)
        with app.store.transaction():
            app.store.connection.execute(
                "UPDATE records SET payload=?,digest=? WHERE namespace=? AND id=?",
                (body,artifact_digest(body),namespace,record_id))

    def test_parent_chain_and_corruption(self):
        revision, task, analysis = self.day()
        report = self.app.report_contrast(analysis,0)
        package = self.app.export_report(report)
        self.assertTrue(verify_export_package(package).valid)
        data = decode_revision(canonical_json(package["revision"]))
        split = decode_artifact(canonical_json(package["analysis"]))
        ordinary = decode_artifact(canonical_json(package["report"]))
        expected_steps, expected_leaves = independent_greedy(data.values,2,2)
        self.assertEqual([vars(step) for step in split.data.steps],expected_steps)
        self.assertEqual([vars(leaf) for leaf in split.data.leaves],expected_leaves)
        coefficients,z,variance,p = independent_contrast(data.values,expected_leaves,0,4)
        self.assertEqual(ordinary.data.result.vector.coefficients,coefficients)
        self.assertEqual(ordinary.data.result.z,z)
        self.assertEqual(ordinary.data.result.normal.variance,variance)
        self.assertAlmostEqual(ordinary.data.result.normal.p,p,delta=1e-12)
        original = snapshot(self.app)
        with TemporaryDirectory(prefix="quality-export-") as directory:
            folder = Path(directory)
            good = folder / "good.json"
            good.write_text(json.dumps(package),encoding="utf-8")
            bad = folder / "bad.json"
            damaged = copy.deepcopy(package)
            damaged["manifest"]["revision_id"] = "wrong"
            bad.write_text(json.dumps(damaged),encoding="utf-8")
            for path, code in ((good,0),(bad,1)):
                process = subprocess.run([sys.executable,"-B","-m","delivery.app",
                                          "verify-package",str(path)],text=True,capture_output=True)
                self.assertEqual(process.returncode,code,process.stderr)
            for mode in ("missing_revision","missing_task","wrong_task","version",
                         "denominator","coverage","parent","report_cycle","digest"):
                with self.subTest(mode=mode):
                    database = folder / (mode+".sqlite")
                    target = sqlite3.connect(database)
                    self.app.store.connection.backup(target)
                    target.close()
                    with WaterQualityApp.open(database) as broken:
                        if mode.startswith("missing"):
                            namespace, key = ("revision",revision) if mode == "missing_revision" else ("task",task)
                            with broken.store.transaction():
                                broken.store.connection.execute(
                                    "DELETE FROM records WHERE namespace=? AND id=?",(namespace,key))
                        elif mode == "wrong_task":
                            fixed = broken.tasks.get(task)
                            body = encode_task(replace(fixed,revision_id="missing-revision"))
                            with broken.store.transaction():
                                broken.store.connection.execute(
                                    "UPDATE records SET payload=?,digest=? WHERE namespace='task' AND id=?",
                                    (body,artifact_digest(body),task))
                        elif mode == "version":
                            self._rewrite(broken,"artifact",analysis,
                                          lambda raw: raw.update(version=2))
                        elif mode == "denominator":
                            def denominator(raw):
                                raw["object"]["fields"]["data"]["fields"]["steps"]["$tuple"][0][
                                    "fields"]["gain"]["$fraction"][1] = 0
                            self._rewrite(broken,"artifact",analysis,denominator)
                        elif mode == "coverage":
                            def coverage(raw):
                                raw["object"]["fields"]["data"]["fields"]["leaves"]["$tuple"][0][
                                    "fields"]["l"] = 1
                            self._rewrite(broken,"artifact",analysis,coverage)
                        elif mode == "parent":
                            def parent(raw):
                                raw["object"]["fields"]["parent_id"] = "absent"
                            self._rewrite(broken,"artifact",report,parent)
                        elif mode == "report_cycle":
                            def cycle(raw):
                                raw["object"]["fields"]["parent_id"] = report
                                raw["object"]["fields"]["data"]["fields"]["analysis_id"] = report
                            self._rewrite(broken,"artifact",report,cycle)
                        else:
                            with broken.store.transaction():
                                broken.store.connection.execute(
                                    "UPDATE records SET digest='wrong' WHERE namespace='artifact' AND id=?",
                                    (report,))
                        with self.assertRaises(CorruptArtifact):
                            broken.export_report(report)
            self.assertEqual(snapshot(self.app),original)
        self.assertEqual(self.app.export_report(report),package)
        with self.assertRaises(UnknownResult):
            self.app.read_result("absent")

    def test_reject_unknown_database_version(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "incompatible.sqlite"
            with WaterQualityApp.open(database) as app:
                revision = app.put_series("one","v1","mg/L",[{"row_no":0,"value":1}])
                before = app.store.get("revision",revision)
                with app.store.transaction():
                    app.store.connection.execute(
                        "UPDATE metadata SET value='999' WHERE key='schema_version'")
            with self.assertRaises(CorruptArtifact):
                WaterQualityApp.open(database)
            connection = sqlite3.connect(database)
            try:
                stored = connection.execute(
                    "SELECT payload FROM records WHERE namespace='revision' AND id=?",
                    (revision,)).fetchone()[0]
                self.assertEqual(stored,before)
            finally:
                connection.close()
