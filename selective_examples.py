"""Finite public fixtures and API checks; no selection-event or support solver."""
import argparse
import copy
from fractions import Fraction as F
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from delivery.app import WaterQualityApp
from delivery.verification import verify_export_package
from tests.reference import independent_greedy, rows, snapshot


def interval(lo, hi, lc=False, hc=False):
    return {"lo": lo, "hi": hi, "lo_closed": lc, "hi_closed": hc}


CASES = (
    {
        "name": "disconnected",
        "values": (-3, -3, -3, -3, -3, -3, -1, -1),
        "noise": 1, "left": 1,
        "steps": ((0, 6, 8), (0, 2, 6)),
        "z": F(-2), "variance": F(3, 4),
        "support": (interval(None, F(-1, 2)), interval(F(1), None)),
        "p": 0.051535717653935,
        "probes": ((-3, True), (-2, True), (-1, True), (F(-1, 2), False),
                   (0, False), (1, False), (2, True)),
    },
    {
        "name": "day",
        "values": (1, 1, 2, 2, 7, 7, 9, 9),
        "noise": 4, "left": 0,
        "steps": ((0, 4, 8), (4, 6, 8)),
        "z": F(-11, 2), "variance": F(3),
        "support": (
            interval(None, F(-10)),
            interval(F(-7), {"poly": (8, -68, -289), "root": 0}, False, True),
            interval({"poly": (8, -68, -289), "root": 1}, None, True, False)),
        "p": 0.019931682837800,
        "probes": ((-11, True), (-10, False), (-9, False), (-7, False),
                   (-6, True), (-3, False), (0, False), (12, True)),
    },
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def reference_parts(case):
    values = tuple(map(F, case["values"]))
    steps, leaves = independent_greedy(values, 2, 2)
    eta = [F(0)] * len(values)
    for sign, leaf in ((1, leaves[case["left"]]), (-1, leaves[case["left"] + 1])):
        for index in range(leaf["l"], leaf["r"]):
            eta[index] = F(sign, leaf["r"] - leaf["l"])
    z = sum((e * y for e, y in zip(eta, values)), F(0))
    q = sum((e * e for e in eta), F(0))
    u = tuple(y - e * z / q for y, e in zip(values, eta))
    return steps, leaves, tuple(eta), z, q, u


def fixed_integral_check(case):
    # An independent finite-fixture quadrature, never used to solve for S.
    if case["name"] == "disconnected":
        spans = ((-12.0, -0.5), (1.0, 12.0))
    else:
        a = (17 - 17 * math.sqrt(3)) / 4
        b = (17 + 17 * math.sqrt(3)) / 4
        spans = ((-20.0, -10.0), (-7.0, a), (b, 20.0))
    v = float(case["variance"])
    density = lambda x: math.exp(-x*x/(2*v)) / math.sqrt(2*math.pi*v)
    def integrate(lo, hi):
        if lo >= hi:
            return 0.0
        n = 16384
        h = (hi - lo) / n
        return h/3 * (density(lo) + density(hi) + sum(
            (4 if i % 2 else 2) * density(lo + i*h) for i in range(1, n)))
    den = sum(integrate(lo, hi) for lo, hi in spans)
    limit = abs(float(case["z"]))
    num = sum(integrate(lo, min(hi, -limit)) + integrate(max(lo, limit), hi)
              for lo, hi in spans)
    require(abs(num/den - case["p"]) < 1e-10, "fixed integral differs")
    return den, num/den


def check_v1():
    for case in CASES:
        steps, leaves, eta, z, q, u = reference_parts(case)
        keys = tuple((s["l"], s["c"], s["r"]) for s in steps)
        require(keys == case["steps"], "independent winning sequence differs")
        require(z == case["z"] and q*case["noise"] == case["variance"],
                "independent contrast differs")
        with WaterQualityApp.open(":memory:") as app:
            revision = app.put_series(case["name"], "v1", "mg/L", rows(case["values"]))
            analysis = app.execute_analysis(app.create_analysis(revision, case["noise"], 2, 2))
            require(app.read_result(analysis)["data"]["steps"] == tuple(steps),
                    "V1 analysis differs")
            ordinary = app.read_result(app.report_contrast(analysis, case["left"]))["data"]
            require(ordinary["result"]["z"] == z, "V1 contrast differs")
        for probe, expected in case["probes"]:
            values = tuple(a + e * F(probe) / q for a, e in zip(u, eta))
            actual, _ = independent_greedy(values, 2, 2)
            same = tuple((s["l"], s["c"], s["r"]) for s in actual) == case["steps"]
            require(same == expected, "rational probe differs: " + str(probe))
        mass, probability = fixed_integral_check(case)
        print(json.dumps({"case": case["name"], "steps": keys,
                          "z": str(z), "variance": str(case["variance"]),
                          "fixed_support_mass": mass, "fixed_expected_p": probability},
                         ensure_ascii=False, sort_keys=True))


def check_event(event, case, analysis, revision):
    require(event["kind"] == "selection" and event["parent_id"] == analysis,
            "selection envelope differs")
    data = event["data"]
    require(data["analysis_id"] == analysis and data["revision_id"] == revision,
            "selection fixed identities differ")
    require(data["request"] == {"noise_variance": F(case["noise"]),
                               "min_leaf": 2, "splits": 2}, "selection request differs")
    require(data["values"] == tuple(map(F, case["values"])), "selection values differ")
    _, leaves, _, _, _, _ = reference_parts(case)
    require(data["leaves"] == tuple((s["l"], s["r"]) for s in leaves),
            "selection leaves differ")
    active = [(0, len(case["values"]))]
    require(len(data["stages"]) == 2, "two stages required")
    for stage, winner in zip(data["stages"], case["steps"]):
        candidates = tuple(sorted((l, c, r) for l, r in active
                                  for c in range(l+2, r-1)))
        require(stage["candidates"] == candidates and stage["winner"] == winner,
                "stage competition differs")
        l, c, r = winner
        active.remove((l, r))
        active.extend(((l, c), (c, r)))
        active.sort()


def check_report(report, case, selection):
    require(report["kind"] == "selective_report" and report["parent_id"] == selection,
            "selective report envelope differs")
    data = report["data"]
    require(data["selection_id"] == selection and data["left_leaf"] == case["left"],
            "selective request differs")
    require(type(data["z"]) is F and data["z"] == case["z"], "exact z differs")
    require(type(data["variance"]) is F and data["variance"] == case["variance"],
            "exact variance differs")
    require(data["support"] == case["support"], "complete exact support differs")
    require(type(data["p"]) is float and math.isfinite(data["p"]) and
            0 <= data["p"] <= 1 and abs(data["p"] - case["p"]) <= 1e-7,
            "conditional probability differs")


def expect_publish_failure(app, kind, callback):
    # A fixed representative checkpoint for each new publication kind.
    before = snapshot(app)
    def fail(stage, actual_kind):
        if stage == "after_insert" and actual_kind == kind:
            raise RuntimeError("fixture publication failure")
    app.publications.fault_hook = fail
    try:
        try:
            callback()
        except RuntimeError as exc:
            require(str(exc) == "fixture publication failure", "unexpected failure")
        else:
            raise AssertionError("publication failure was not triggered")
    finally:
        app.publications.fault_hook = None
    require(snapshot(app) == before, "partial publication survived failure")


def run_v2(demo=False):
    with TemporaryDirectory(prefix="selective-review-") as directory:
        database = Path(directory) / "review.sqlite"
        saved = []
        with WaterQualityApp.open(database) as app:
            for case in CASES:
                supplied = rows(case["values"])
                revision = app.put_series(case["name"], "v1", "mg/L", supplied)
                analysis = app.execute_analysis(app.create_analysis(revision, case["noise"], 2, 2))
                expect_publish_failure(app, "selection", lambda: app.freeze_selection(analysis))
                selection = app.freeze_selection(analysis)
                require(app.freeze_selection(analysis) == selection, "freeze replay differs")
                check_event(app.read_result(selection), case, analysis, revision)
                expect_publish_failure(
                    app, "selective_report", lambda: app.selective_test(selection, case["left"]))
                report = app.selective_test(selection, case["left"])
                require(app.selective_test(selection, case["left"]) == report, "test replay differs")
                original_event = app.read_result(selection)
                original_report = app.read_result(report)
                check_report(original_report, case, selection)
                package = app.export_report(report)
                require(package["version"] == 2, "new export version differs")
                require(verify_export_package(package).valid, "new package verification failed")
                damaged = copy.deepcopy(package)
                damaged["manifest"]["selection_id"] = "wrong"
                require(not verify_export_package(damaged).valid, "wrong parent accepted")
                # Input, read-object and package mutations must not affect history.
                supplied[0]["value"] = 999
                changed = app.read_result(selection)
                changed["data"]["values"] = ()
                changed = app.read_result(report)
                changed["data"]["support"] = ()
                damaged["selection"] = {}
                correction = list(case["values"])
                correction[0] += 1
                child = app.put_series(case["name"], "v2", "mg/L", rows(correction), revision)
                app.execute_analysis(app.create_analysis(child, case["noise"], 2, 2))
                require(app.read_result(selection) == original_event, "old event changed")
                require(app.read_result(report) == original_report, "old report changed")
                require(app.export_report(report) == package, "old package changed")
                saved.append((case, analysis, selection, report, original_event, original_report, package))
        with WaterQualityApp.open(database) as app:
            for case, analysis, selection, report, event, result, package in saved:
                require(app.read_result(selection) == event, "reopened event differs")
                require(app.read_result(report) == result, "reopened report differs")
                require(app.freeze_selection(analysis) == selection, "reopened freeze differs")
                require(app.selective_test(selection, case["left"]) == report,
                        "reopened test differs")
                require(app.export_report(report) == package, "reopened package differs")
                require(verify_export_package(package).valid, "reopened package invalid")
                if demo:
                    print(json.dumps({"case": case["name"], "selection": event,
                                      "selective_report": result,
                                      "old_revision_preserved_after_correction": True},
                                     ensure_ascii=False, sort_keys=True, default=str))
    if not demo:
        print("Selective fixtures, publication retry and historical handoff verified.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=("v1", "verify-all", "demo"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--v1", action="store_true")
    modes.add_argument("--verify-all", action="store_true")
    modes.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    mode = args.mode or ("verify-all" if args.verify_all else "demo" if args.demo else "v1")
    check_v1()
    if mode == "verify-all":
        suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
            return 1
        run_v2()
    elif mode == "demo":
        run_v2(demo=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
