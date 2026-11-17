from dataclasses import dataclass
from archive.codec import (canonical_json, artifact_digest, decode_revision,
                           decode_task, decode_artifact)
from selection.greedy import run_greedy
from selection.event import build_selection_event
from inference.report import ReportRequest, build_report
from inference.selective import compute_selective_report


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    errors: tuple[str, ...]


def _verify_v1(package):
    if (not isinstance(package, dict) or
            set(package) != {"version", "manifest", "revision", "task", "analysis", "report"} or
            type(package["version"]) is not int or package["version"] != 1):
        raise ValueError("invalid export package")
    manifest = package["manifest"]
    names = ("revision", "task", "analysis", "report")
    if (not isinstance(manifest, dict) or
            set(manifest) != {"revision_id", "task_id", "analysis_id", "report_id", "digests"} or
            not isinstance(manifest["digests"], dict) or
            set(manifest["digests"]) != set(names)):
        raise ValueError("invalid export manifest")
    bodies = {name: canonical_json(package[name]) for name in names}
    if any(artifact_digest(bodies[name]) != manifest["digests"][name] for name in names):
        raise ValueError("package digest mismatch")
    revision = decode_revision(bodies["revision"])
    task = decode_task(bodies["task"])
    analysis = decode_artifact(bodies["analysis"])
    report = decode_artifact(bodies["report"])
    if (revision.revision_id != manifest["revision_id"] or
            task.task_id != manifest["task_id"] or
            analysis.artifact_id != manifest["analysis_id"] or
            report.artifact_id != manifest["report_id"] or
            task.revision_id != revision.revision_id or
            analysis.kind != "analysis" or analysis.parent_id != task.task_id or
            report.kind != "report" or report.parent_id != analysis.artifact_id):
        raise ValueError("package parent identities differ")
    recomputed = run_greedy(revision, task.request)
    if analysis.data != recomputed:
        raise ValueError("segmentation or fixed parameters differ")
    expected_report = build_report(
        ReportRequest(analysis.artifact_id, report.data.left_leaf), recomputed, revision)
    if report.data != expected_report:
        raise ValueError("ordinary report differs")
    return VerificationResult(True, ())


def _verify_v2(package):
    if (not isinstance(package, dict) or
            set(package) != {"version", "manifest", "revision", "task", "analysis",
                             "selection", "report"} or
            type(package["version"]) is not int or package["version"] != 2):
        raise ValueError("invalid export package")
    manifest = package["manifest"]
    names = ("revision", "task", "analysis", "selection", "report")
    if (not isinstance(manifest, dict) or
            set(manifest) != {"revision_id", "task_id", "analysis_id", "selection_id",
                              "report_id", "digests"} or
            not isinstance(manifest["digests"], dict) or
            set(manifest["digests"]) != set(names)):
        raise ValueError("invalid export manifest")
    bodies = {name: canonical_json(package[name]) for name in names}
    if any(artifact_digest(bodies[name]) != manifest["digests"][name] for name in names):
        raise ValueError("package digest mismatch")
    revision = decode_revision(bodies["revision"])
    task = decode_task(bodies["task"])
    analysis = decode_artifact(bodies["analysis"])
    selection = decode_artifact(bodies["selection"])
    report = decode_artifact(bodies["report"])
    if (revision.revision_id != manifest["revision_id"] or
            task.task_id != manifest["task_id"] or
            analysis.artifact_id != manifest["analysis_id"] or
            selection.artifact_id != manifest["selection_id"] or
            report.artifact_id != manifest["report_id"] or
            task.revision_id != revision.revision_id or
            analysis.kind != "analysis" or analysis.parent_id != task.task_id or
            selection.kind != "selection" or selection.parent_id != analysis.artifact_id or
            report.kind != "selective_report" or report.parent_id != selection.artifact_id):
        raise ValueError("package parent identities differ")
    recomputed = run_greedy(revision, task.request)
    if analysis.data != recomputed:
        raise ValueError("segmentation or fixed parameters differ")
    event = build_selection_event(analysis.artifact_id, revision, recomputed)
    if selection.data != event:
        raise ValueError("selection event differs")
    expected = compute_selective_report(selection.artifact_id, event,
                                        report.data.left_leaf)
    if report.data != expected:
        raise ValueError("selective report differs")
    return VerificationResult(True, ())


def verify_export_package(package):
    try:
        if not isinstance(package, dict) or type(package.get("version")) is not int:
            raise ValueError("invalid export package")
        if package["version"] == 1:
            return _verify_v1(package)
        if package["version"] == 2:
            return _verify_v2(package)
        raise ValueError("unsupported export version")
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, ArithmeticError) as exc:
        return VerificationResult(False, (str(exc),))
