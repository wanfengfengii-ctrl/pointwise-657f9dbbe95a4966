from fractions import Fraction
import math
import unittest
from delivery.app import WaterQualityApp

DAY = [1, 1, 2, 2, 7, 7, 9, 9]


def rows(values):
    return [{"row_no": index, "value": value} for index, value in enumerate(values)]


def direct_stats(values, l, r):
    block = [Fraction(value) for value in values[l:r]]
    total = sum(block, Fraction(0))
    mean = total / len(block)
    return {"l": l, "r": r, "count": len(block), "total": total,
            "sum_squares": sum((value * value for value in block), Fraction(0)),
            "mean": mean, "sse": sum(((value - mean) ** 2 for value in block), Fraction(0))}


def independent_greedy(values, min_leaf, splits):
    leaves, chosen = [(0, len(values))], []
    for _ in range(splits):
        candidates = []
        for l, r in leaves:
            parent = direct_stats(values, l, r)["sse"]
            for c in range(l + min_leaf, r - min_leaf + 1):
                gain = parent - direct_stats(values, l, c)["sse"] - direct_stats(values, c, r)["sse"]
                candidates.append((gain, (l, c, r)))
        if not candidates:
            raise ValueError("independent enumeration has no candidates")
        gain, (l, c, r) = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
        chosen.append({"l": l, "c": c, "r": r, "gain": gain})
        leaves.remove((l, r))
        leaves.extend(((l, c), (c, r)))
        leaves.sort()
    return chosen, [direct_stats(values, l, r) for l, r in leaves]


def independent_contrast(values, leaves, left, noise):
    coefficients = [Fraction(0)] * len(values)
    for sign, leaf in ((1, leaves[left]), (-1, leaves[left + 1])):
        for i in range(leaf["l"], leaf["r"]):
            coefficients[i] = Fraction(sign, leaf["r"] - leaf["l"])
    z = sum((a * Fraction(b) for a, b in zip(coefficients, values)), Fraction(0))
    variance = Fraction(noise) * sum((a*a for a in coefficients), Fraction(0))
    return tuple(coefficients), z, variance, math.erfc(abs(float(z)) / math.sqrt(2*float(variance)))


def snapshot(app):
    return (app.store.connection.execute(
        "SELECT namespace,id,payload,digest FROM records ORDER BY namespace,id").fetchall(),
        app.store.connection.execute(
        "SELECT namespace,key,target FROM links ORDER BY namespace,key").fetchall())


class AppCase(unittest.TestCase):
    def setUp(self):
        self.app = WaterQualityApp.open(":memory:")
        self.addCleanup(self.app.close)

    def day(self, values=DAY, noise=4, version="v1", series="water"):
        revision = self.app.put_series(series, version, "mg/L", rows(values))
        task = self.app.create_analysis(revision, noise, 2, 2)
        analysis = self.app.execute_analysis(task)
        return revision, task, analysis
