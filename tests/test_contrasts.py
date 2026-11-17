from fractions import Fraction
import math
from tests.reference import AppCase, DAY, rows, snapshot, independent_contrast
from inference.normal import two_sided_normal_p


class TestContrasts(AppCase):
    def test_known_variance_report(self):
        _, _, analysis = self.day()
        _, _, second = self.day(noise=1)
        report_id = self.app.report_contrast(analysis, 0)
        report = self.app.read_result(report_id)["data"]
        leaves = self.app.read_result(analysis)["data"]["leaves"]
        coefficients, z, variance, p = independent_contrast(DAY, leaves, 0, 4)
        result = report["result"]
        self.assertEqual(result["vector"]["coefficients"], coefficients)
        self.assertEqual(coefficients, (Fraction(1,4),)*4 + (Fraction(-1,2),)*2 + (Fraction(0),)*2)
        self.assertEqual(result["z"], z)
        self.assertEqual(z, Fraction(-11,2))
        self.assertEqual(result["norm_squared"], Fraction(3,4))
        self.assertEqual(result["normal"]["variance"], variance)
        self.assertEqual(variance, 3)
        self.assertAlmostEqual(float(result["normal"]["standard_error"]), math.sqrt(3), places=14)
        self.assertAlmostEqual(result["normal"]["p"], p, delta=1e-12)
        self.assertAlmostEqual(p, 0.00149616428974555, delta=1e-15)
        self.assertIn("未校正选段", report["warning"])
        self.assertEqual(report["noise_variance"], 4)
        other = self.app.read_result(self.app.report_contrast(second, 0))["data"]
        self.assertEqual(other["result"]["normal"]["variance"], Fraction(3,4))
        self.assertEqual(self.app.report_contrast(analysis, 0), report_id)
        before = snapshot(self.app)
        for invalid in (-1,2,True,0.0,"0"):
            with self.assertRaises(ValueError):
                self.app.report_contrast(analysis, invalid)
        self.assertEqual(snapshot(self.app), before)
        # Composite Simpson integration of the standard normal density is an
        # independent probability check, without erfc or production helpers.
        x = 5.5 / math.sqrt(3)
        n = 4096
        h = x / n
        density = lambda t: math.exp(-t*t/2) / math.sqrt(2*math.pi)
        integral = h/3 * (density(0)+density(x)+sum(
            (4 if i % 2 else 2)*density(i*h) for i in range(1,n)))
        self.assertAlmostEqual(result["normal"]["p"], 1-2*integral, delta=1e-12)

    def test_zero_and_extreme_tail(self):
        revision = self.app.put_series("zero", "v1", "mg/L", rows([3]*8))
        task = self.app.create_analysis(revision, 1, 2, 2)
        report = self.app.read_result(self.app.report_contrast(self.app.execute_analysis(task),0))
        self.assertEqual(report["data"]["result"]["normal"]["p"], 1)
        for z, variance, expected in ((Fraction(0),Fraction(1),1),
                                      (Fraction(1000),Fraction(1),0),
                                      (Fraction(10**500),Fraction(1),0),
                                      (Fraction(1,10**500),Fraction(1),1)):
            self.assertEqual(two_sided_normal_p(z, variance), expected)
