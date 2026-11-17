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


# Independent accounting: hand-derived oracles, never the production solver.
EXTRA_CASES = (
    {
        # Zero-gain ties on the observed data: every candidate gains 0, the
        # lexicographic rule decides. All constraints are tangents at z=0
        # sharing one endpoint (identity comparison), so S is the whole line
        # with both infinite tails and p = 1 exactly.
        "name": "constant",
        "values": (5, 5, 5, 5, 5, 5, 5, 5),
        "noise": 1, "left": 0,
        "steps": ((0, 2, 8), (2, 4, 8)),
        "z": F(0), "variance": F(1),
        "support": (interval(None, None),),
        "p": 1.0,
        "probes": ((-100, True), (-1, True), (0, True), (F(7, 2), True),
                   (100, True)),
    },
)

SINGLETON_CASE = {
    # S = {0}: the winner gain is identically zero and every competitor gain
    # is a positive multiple of z^2, so only z=0 keeps the sequence. The
    # conditional mass is zero, below 1e-8, and no report may be published.
    "name": "singleton",
    "values": (5, 5, 5, 5, 5, 5, 5, 5),
    "noise": 1, "left": 1,
    "steps": ((0, 2, 8), (2, 4, 8)),
    "probes": ((-2, False), (-1, False), (0, True), (1, False), (2, False)),
}

# Hand-computed solution sets for synthetic constraint lists (A, B, C, strict)
# with D(z) = A z^2 + B z + C required positive (strict) or nonnegative.
CONSTRAINT_ORACLES = (
    ("isolated_point",
     ((F(1), F(-4), F(3), False), (F(1), F(-8), F(15), False)),
     (interval(None, F(1), False, True),
      interval(F(3), F(3), True, True),
      interval(F(5), None, True, False))),
    ("strict_tangent",
     ((F(1), F(-4), F(4), True),),
     (interval(None, F(2)), interval(F(2), None))),
    ("nonstrict_tangent",
     ((F(1), F(-4), F(4), False),),
     (interval(None, None),)),
    ("identical_zero_strict", ((F(0), F(0), F(0), True),), ()),
    ("identical_zero_nonstrict", ((F(0), F(0), F(0), False),),
     (interval(None, None),)),
    ("linear_strict",
     ((F(0), F(2), F(-1), True),),
     (interval(F(1, 2), None),)),
    ("linear_nonstrict",
     ((F(0), F(-2), F(1), False),),
     (interval(None, F(1, 2), False, True),)),
    ("downward_tangent",
     ((F(-1), F(4), F(-4), False),),
     (interval(F(2), F(2), True, True),)),
    ("downward_two_roots",
     ((F(-1), F(4), F(-3), False),),
     (interval(F(1), F(3), True, True),)),
    ("upward_strict",
     ((F(1), F(-4), F(3), True),),
     (interval(None, F(1)), interval(F(3), None))),
    ("quadratic_irrational",
     ((F(8), F(-68), F(-289), False),),
     (interval(None, {"poly": (8, -68, -289), "root": 0}, False, True),
      interval({"poly": (8, -68, -289), "root": 1}, None, True, False))),
    # A rational endpoint lying strictly between the two irrational roots.
    ("quadratic_with_rational_between",
     ((F(8), F(-68), F(-289), False), (F(0), F(1), F(0), False)),
     (interval({"poly": (8, -68, -289), "root": 1}, None, True, False),)),
    ("quadratic_with_rational_inside_gap",
     ((F(8), F(-68), F(-289), False), (F(0), F(-1), F(5), False)),
     (interval(None, {"poly": (8, -68, -289), "root": 0}, False, True),)),
    ("no_real_root_positive", ((F(1), F(0), F(1), True),),
     (interval(None, None),)),
    ("no_real_root_negative", ((F(-1), F(0), F(-1), False),), ()),
)


def endpoint_minus_rational(endpoint, z):
    """Sign of (endpoint - z) for rational z; independent exact comparison."""
    if isinstance(endpoint, F):
        return (endpoint > z) - (endpoint < z)
    a, b, c = endpoint["poly"]
    value = a * z * z + b * z + c
    if value < 0:  # z lies strictly between the two roots
        return 1 if endpoint["root"] == 1 else -1
    # value > 0: roots are irrational, so z is outside them
    return 1 if z < F(-b, 2 * a) else -1


def support_contains(support, z):
    for iv in support:
        lo, hi = iv["lo"], iv["hi"]
        if lo is not None:
            sign = endpoint_minus_rational(lo, z)
            if sign > 0 or (sign == 0 and not iv["lo_closed"]):
                continue
        if hi is not None:
            sign = endpoint_minus_rational(hi, z)
            if sign < 0 or (sign == 0 and not iv["hi_closed"]):
                continue
        return True
    return False


def check_constraint_oracles():
    from inference.selective import build_support

    def norm_endpoint(endpoint):
        if endpoint is None or isinstance(endpoint, F):
            return endpoint
        if isinstance(endpoint, dict):
            return ("poly", tuple(endpoint["poly"]), endpoint["root"])
        return ("poly", tuple(endpoint.poly), endpoint.root)

    for name, constraints, expected in CONSTRAINT_ORACLES:
        actual = build_support(tuple(constraints))
        want = tuple((norm_endpoint(iv["lo"]), norm_endpoint(iv["hi"]),
                      iv["lo_closed"], iv["hi_closed"]) for iv in expected)
        got = tuple((norm_endpoint(iv.lo), norm_endpoint(iv.hi),
                     iv.lo_closed, iv.hi_closed) for iv in actual)
        require(got == want, "constraint oracle differs: " + name)


def check_independent():
    check_constraint_oracles()
    for case in EXTRA_CASES:
        steps, leaves, eta, z, q, u = reference_parts(case)
        require(tuple((s["l"], s["c"], s["r"]) for s in steps) == case["steps"],
                "independent winning sequence differs: " + case["name"])
        require(z == case["z"] and q * case["noise"] == case["variance"],
                "independent contrast differs: " + case["name"])
        with WaterQualityApp.open(":memory:") as app:
            revision = app.put_series(case["name"], "v1", "mg/L", rows(case["values"]))
            analysis = app.execute_analysis(app.create_analysis(revision, case["noise"], 2, 2))
            event = app.read_result(app.freeze_selection(analysis))
            active = [(0, len(case["values"]))]
            for stage, winner in zip(event["data"]["stages"], case["steps"]):
                candidates = tuple(sorted((l, c, r) for l, r in active
                                          for c in range(l + 2, r - 1)))
                require(stage["candidates"] == candidates and stage["winner"] == winner,
                        "independent candidate enumeration differs: " + case["name"])
                l, c, r = winner
                active.remove((l, r))
                active.extend(((l, c), (c, r)))
                active.sort()
            data = app.read_result(app.selective_test(
                event["artifact_id"], case["left"]))["data"]
            require(data["support"] == case["support"],
                    "hand-derived support differs: " + case["name"])
            require(data["p"] == case["p"], "exact probability differs: " + case["name"])
            for probe, expected in case["probes"]:
                values = tuple(a + e * F(probe) / q for a, e in zip(u, eta))
                actual, _ = independent_greedy(values, 2, 2)
                same = tuple((s["l"], s["c"], s["r"]) for s in actual) == case["steps"]
                require(same == expected, "rational probe differs: " + case["name"])
                require(support_contains(data["support"], F(probe)) == expected,
                        "support membership differs: " + case["name"])
    case = SINGLETON_CASE
    steps, leaves, eta, z, q, u = reference_parts(case)
    require(tuple((s["l"], s["c"], s["r"]) for s in steps) == case["steps"],
            "independent winning sequence differs: " + case["name"])
    for probe, expected in case["probes"]:
        values = tuple(a + e * F(probe) / q for a, e in zip(u, eta))
        actual, _ = independent_greedy(values, 2, 2)
        same = tuple((s["l"], s["c"], s["r"]) for s in actual) == case["steps"]
        require(same == expected, "singleton probe differs")
    with WaterQualityApp.open(":memory:") as app:
        revision = app.put_series(case["name"], "v1", "mg/L", rows(case["values"]))
        analysis = app.execute_analysis(app.create_analysis(revision, case["noise"], 2, 2))
        selection = app.freeze_selection(analysis)
        before = snapshot(app)
        try:
            app.selective_test(selection, case["left"])
        except ValueError:
            pass
        else:
            raise AssertionError("zero conditional mass was not rejected")
        require(snapshot(app) == before, "rejected test left partial artifacts")
    print("Independent candidate, endpoint, interval and probability accounting verified.")


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
        check_independent()
    elif mode == "demo":
        run_v2(demo=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
