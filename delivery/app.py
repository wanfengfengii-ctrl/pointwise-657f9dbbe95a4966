import argparse
from dataclasses import asdict
from fractions import Fraction
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from sampling.importer import put_series
from sampling.revisions import RevisionRepository
from archive.storage import Store
from archive.tasks import TaskRepository
from archive.results import ResultRepository
from archive.transactions import PublicationCoordinator
from delivery.analysis import AnalysisCoordinator
from delivery.reports import ReportCoordinator
from delivery.export import export_report
from delivery.verification import verify_export_package


class WaterQualityApp:
    def __init__(self, path, fault_hook=None):
        self.store = Store(path)
        self.revisions = RevisionRepository(self.store)
        self.tasks = TaskRepository(self.store, self.revisions)
        self.publications = PublicationCoordinator(self.store, fault_hook)
        self.results = ResultRepository(self.store, self.revisions, self.tasks, self.publications)
        self.analysis = AnalysisCoordinator(self.tasks, self.revisions, self.results)
        self.reports = ReportCoordinator(self.revisions, self.tasks, self.results)

    @classmethod
    def open(cls, path, fault_hook=None):
        return cls(path, fault_hook)

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()

    def put_series(self, series_id, source_version, unit, rows, correction_parent=None):
        return put_series(self.revisions, series_id, source_version, unit, rows,
                          correction_parent)

    def create_analysis(self, revision_id, noise_variance, min_leaf, splits):
        return self.tasks.create_analysis(revision_id, noise_variance, min_leaf, splits)

    def execute_analysis(self, task_id):
        return self.analysis.execute_analysis(task_id)

    def report_contrast(self, analysis_id, left_leaf):
        return self.reports.report_contrast(analysis_id, left_leaf)

    def read_result(self, artifact_id):
        return self.results.read_result(artifact_id)

    def export_report(self, report_id):
        return export_report(self.results, self.tasks, self.revisions, report_id)


def _display(value):
    if isinstance(value, Fraction):
        return str(value)
    raise TypeError(type(value).__name__)


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=_display,
                     allow_nan=False))


def run_demo(sample_path):
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="water-day-") as directory:
        database = Path(directory) / "quality.sqlite"
        with WaterQualityApp.open(database) as app:
            revision_id = app.put_series(**sample)
            assert app.put_series(**sample) == revision_id
            task_id = app.create_analysis(revision_id, 4, 2, 2)
            analysis_id = app.execute_analysis(task_id)
            report_id = app.report_contrast(analysis_id, 0)
            before = app.read_result(report_id)
            analysis = app.read_result(analysis_id)
            splits = [[step["l"], step["c"], step["r"]] for step in analysis["data"]["steps"]]
            assert splits == [[0, 4, 8], [4, 6, 8]]
            assert before["data"]["result"]["z"] == Fraction(-11, 2)
            assert before["data"]["result"]["normal"]["variance"] == 3
            correction = dict(sample)
            correction["source_version"] = "day-1-corrected"
            correction["rows"] = [dict(row) for row in sample["rows"]]
            correction["rows"][4]["value"] = 8
            correction["correction_parent"] = revision_id
            corrected_id = app.put_series(**correction)
            corrected_task = app.create_analysis(corrected_id, 4, 2, 2)
            app.execute_analysis(corrected_task)
        with WaterQualityApp.open(database) as reopened:
            assert reopened.read_result(report_id) == before
            package = reopened.export_report(report_id)
            checked = verify_export_package(package)
            assert checked.valid, checked.errors
            fixed = reopened.revisions.get(package["manifest"]["revision_id"])
            assert fixed.values[4] == 7
            probability = before["data"]["result"]["normal"]["p"]
            expected = {"splits": [[0, 4, 8], [4, 6, 8]], "z": "-11/2",
                        "variance": "3"}
            actual = {"splits": splits, "z": str(before["data"]["result"]["z"]),
                      "variance": str(before["data"]["result"]["normal"]["variance"])}
            marker = {"case_id": "v1.run_entry", "input": sample,
                      "expected": expected, "actual": actual,
                      "downstream_expected": {"old_row_4": "7", "verified": True},
                      "downstream_actual": {"old_row_4": str(fixed.values[4]),
                                            "verified": checked.valid},
                      "code_paths": ["sampling/importer.py", "selection/greedy.py",
                                     "inference/report.py", "archive/results.py",
                                     "delivery/export.py"],
                      "oracle": "hand-summed eight-row example; exact contrast and old-row assertion"}
            print("POINTWISE_SCENARIO " + json.dumps(marker, ensure_ascii=False, sort_keys=True))
            _print({"analysis_id": analysis_id, "report_id": report_id,
                    "ordinary_p": probability, "warning": before["data"]["warning"],
                    "correction_preserved_old_report": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline water-quality review archive")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "import", "create", "execute", "report", "read", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("--db", required=True)
        if name == "import":
            sub.add_argument("input")
        elif name == "create":
            sub.add_argument("revision_id")
            sub.add_argument("--noise-variance", required=True)
            sub.add_argument("--min-leaf", type=int, required=True)
            sub.add_argument("--splits", type=int, required=True)
        elif name == "execute":
            sub.add_argument("task_id")
        elif name == "report":
            sub.add_argument("analysis_id")
            sub.add_argument("--left-leaf", type=int, required=True)
        elif name in ("read", "export"):
            sub.add_argument("artifact_id")
            if name == "export":
                sub.add_argument("--out", required=True)
    verifier = commands.add_parser("verify-package")
    verifier.add_argument("input")
    demo = commands.add_parser("demo")
    demo.add_argument("--sample", default="examples/day.json")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-package":
            checked = verify_export_package(json.loads(Path(args.input).read_text(encoding="utf-8")))
            _print(asdict(checked))
            return 0 if checked.valid else 1
        if args.command == "demo":
            run_demo(args.sample)
            return 0
        with WaterQualityApp.open(args.db) as app:
            if args.command == "init":
                _print({"schema_version": 1})
            elif args.command == "import":
                payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
                _print({"revision_id": app.put_series(**payload)})
            elif args.command == "create":
                _print({"task_id": app.create_analysis(args.revision_id, args.noise_variance,
                                                       args.min_leaf, args.splits)})
            elif args.command == "execute":
                _print({"analysis_id": app.execute_analysis(args.task_id)})
            elif args.command == "report":
                _print({"report_id": app.report_contrast(args.analysis_id, args.left_leaf)})
            elif args.command == "read":
                _print(app.read_result(args.artifact_id))
            elif args.command == "export":
                package = app.export_report(args.artifact_id)
                Path(args.out).write_text(json.dumps(package, ensure_ascii=False, sort_keys=True),
                                          encoding="utf-8")
                _print({"output": args.out, "verified": True})
        return 0
    except (ValueError, LookupError, OSError, TypeError, ArithmeticError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
