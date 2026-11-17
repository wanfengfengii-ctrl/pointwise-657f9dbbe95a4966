from fractions import Fraction
from tests.reference import AppCase, rows, snapshot
from sampling.revisions import ConflictError, UnknownRevision
from sampling.types import SampleRow


class TestSampling(AppCase):
    def test_invalid_batch_is_atomic(self):
        revision, _, _ = self.day()
        before = snapshot(self.app)
        for tail in ("1/0", None, True, 1.5, "NaN", "Infinity", {}, ""):
            with self.subTest(tail=tail):
                with self.assertRaises(ValueError):
                    self.app.put_series("bad", "retry", "mg/L", rows([1,2,tail]))
                self.assertEqual(snapshot(self.app), before)
        for invalid in ([], [{"row_no":1,"value":0}],
                        [{"row_no":0,"value":0},{"row_no":0,"value":1}],
                        [{"row_no":0,"value":0},{"row_no":2,"value":1}],
                        [{"row_no":True,"value":0}]):
            with self.assertRaises(ValueError):
                self.app.put_series("bad", "retry", "mg/L", invalid)
            self.assertEqual(snapshot(self.app), before)
        with self.assertRaises(ValueError):
            self.app.put_series("bad", "retry", "ug/L", rows([1,2]))
        self.assertEqual(snapshot(self.app), before)
        good = self.app.put_series("bad", "retry", "mg/L", rows([-1,2]))
        self.assertEqual(self.app.revisions.get(good).values, (Fraction(-1), Fraction(2)))
        self.assertEqual(self.app.revisions.get(revision).values[4], 7)

    def test_replay_and_conflict(self):
        supplied = rows(["1/2", 2])
        first = self.app.put_series("fraction", "v1", "mg/L", supplied)
        supplied[0]["value"] = 999
        self.assertEqual(self.app.revisions.get(first).values[0], Fraction(1,2))
        before = snapshot(self.app)
        self.assertEqual(self.app.put_series("fraction", "v1", "mg/L",
                         (SampleRow(0,Fraction(2,4)), SampleRow(1,Fraction(2)))), first)
        self.assertEqual(snapshot(self.app), before)
        with self.assertRaises(ConflictError):
            self.app.put_series("fraction", "v1", "mg/L", rows(["3/4",2]))
        with self.assertRaises(ConflictError):
            self.app.put_series("fraction", "v1", "mg/L", rows(["1/2",2]), first)
        self.assertEqual(snapshot(self.app), before)
        corrected = self.app.put_series("fraction", "v2", "mg/L", rows(["3/4",2]), first)
        self.assertEqual(self.app.revisions.get(corrected).payload.correction_parent, first)
        other = self.app.put_series("other", "v1", "mg/L", rows([0]))
        for parent in ("absent", other):
            before = snapshot(self.app)
            with self.assertRaises(ValueError):
                self.app.put_series("fraction", "bad", "mg/L", rows([1]), parent)
            self.assertEqual(snapshot(self.app), before)
        with self.assertRaises(UnknownRevision):
            self.app.revisions.get("absent")
