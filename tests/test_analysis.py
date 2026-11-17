from fractions import Fraction
import json
import subprocess
import sys
from tests.reference import AppCase, DAY, rows, snapshot, independent_greedy
from archive.schema import UnknownTask
from sampling.revisions import UnknownRevision


class TestDailyAnalysis(AppCase):
    def test_exact_two_splits(self):
        revision, task, artifact = self.day()
        result = self.app.read_result(artifact)
        expected_steps, expected_leaves = independent_greedy(DAY, 2, 2)
        actual = result["data"]
        self.assertEqual(actual["steps"], tuple(expected_steps))
        self.assertEqual(actual["leaves"], tuple(expected_leaves))
        self.assertEqual([step["gain"] for step in actual["steps"]], [Fraction(169, 2), 4])
        self.assertEqual([leaf["sse"] for leaf in actual["leaves"]], [1, 0, 0])
        self.assertEqual(self.app.execute_analysis(task), artifact)
        self.assertEqual(result["parent_id"], task)
        self.assertEqual(actual["revision_id"], revision)
        shifted = [value + 10**16 for value in DAY]
        _, _, shifted_id = self.day(shifted, version="shifted")
        shifted_data = self.app.read_result(shifted_id)["data"]
        reference_steps, reference_leaves = independent_greedy(shifted, 2, 2)
        self.assertEqual(shifted_data["steps"], tuple(reference_steps))
        self.assertEqual(shifted_data["leaves"], tuple(reference_leaves))
        self.assertEqual(shifted_data["steps"], actual["steps"])
        report = self.app.report_contrast(artifact, 0)
        z = self.app.read_result(report)["data"]["result"]["z"]
        self.assertEqual(z, Fraction(-11, 2))
        print("POINTWISE_SCENARIO " + json.dumps({
            "case_id": "v1.reference_day", "input": DAY,
            "expected": {"splits": [[0,4,8],[4,6,8]], "gains": ["169/2","4"]},
            "actual": {"splits": [[s["l"],s["c"],s["r"]] for s in actual["steps"]],
                       "gains": [str(s["gain"]) for s in actual["steps"]]},
            "downstream_expected": {"z": "-11/2"}, "downstream_actual": {"z": str(z)},
            "code_paths": ["selection/statistics.py", "selection/candidates.py",
                           "selection/greedy.py", "inference/contrasts.py"],
            "oracle": "independent direct squared deviations; exhaustive current-leaf candidates"
        }, sort_keys=True))

    def test_independent_finite_sequences(self):
        from itertools import product
        for values in product((-1, 0, 2), repeat=5):
            revision = self.app.put_series("finite", str(values), "mg/L", rows(values))
            task = self.app.create_analysis(revision, "1/3", 1, 2)
            result = self.app.read_result(self.app.execute_analysis(task))["data"]
            steps, leaves = independent_greedy(values, 1, 2)
            self.assertEqual(result["steps"], tuple(steps))
            self.assertEqual(result["leaves"], tuple(leaves))

    def test_run_entry(self):
        process = subprocess.run([sys.executable, "-B", "-m", "delivery.app", "demo"],
                                 text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        markers = [line for line in process.stdout.splitlines()
                   if line.startswith("POINTWISE_SCENARIO ")]
        self.assertEqual(len(markers), 1)
        marker = json.loads(markers[0].split(" ", 1)[1])
        self.assertEqual(marker["expected"], marker["actual"])
        self.assertEqual(marker["downstream_expected"], marker["downstream_actual"])


class TestAnalysis(AppCase):
    def test_minimum_leaf_and_ties(self):
        revision = self.app.put_series("constant", "v1", "mg/L", rows([5]*8))
        task = self.app.create_analysis(revision, 1, 2, 2)
        actual = self.app.read_result(self.app.execute_analysis(task))["data"]
        self.assertEqual([(s["l"],s["c"],s["r"]) for s in actual["steps"]],
                         [(0,2,8),(2,4,8)])
        self.assertEqual([s["gain"] for s in actual["steps"]], [0,0])
        bad = self.app.put_series("blocked", "v1", "mg/L", rows([0,0,0,10,10,10,10,10]))
        before = snapshot(self.app)
        with self.assertRaises(ValueError):
            self.app.create_analysis(bad, 1, 2, 3)
        self.assertEqual(snapshot(self.app), before)
        for noise, length, splits in ((0,2,2),(-1,2,2),(True,2,2),(1.0,2,2),
                                      (1,True,2),(1,0,2),(1,2,True),(1,2,-1),(1,2,1.5)):
            with self.subTest(noise=noise, length=length, splits=splits):
                with self.assertRaises(ValueError):
                    self.app.create_analysis(revision, noise, length, splits)
                self.assertEqual(snapshot(self.app), before)
        zero = self.app.create_analysis(revision, "2/3", 8, 0)
        result = self.app.read_result(self.app.execute_analysis(zero))["data"]
        self.assertEqual(result["steps"], ())
        self.assertEqual([(leaf["l"],leaf["r"]) for leaf in result["leaves"]], [(0,8)])
        with self.assertRaises(UnknownRevision):
            self.app.create_analysis("absent", 1, 1, 0)
        with self.assertRaises(UnknownTask):
            self.app.execute_analysis("absent")
