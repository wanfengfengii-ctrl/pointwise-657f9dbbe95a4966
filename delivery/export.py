from dataclasses import dataclass, asdict
import json
from archive.codec import (encode_revision, encode_task, encode_artifact, artifact_digest)
from archive.schema import CorruptArtifact, UnknownResult
from delivery.verification import verify_export_package


@dataclass(frozen=True)
class ExportManifest:
    revision_id: str
    task_id: str
    analysis_id: str
    report_id: str
    digests: dict


@dataclass(frozen=True)
class ExportPackage:
    version: int
    manifest: ExportManifest
    revision: dict
    task: dict
    analysis: dict
    report: dict


def _export_ordinary(results, report):
    analysis, task, revision = results._report_context(report.parent_id, report.data)
    bodies = {"revision": encode_revision(revision), "task": encode_task(task),
              "analysis": encode_artifact(analysis), "report": encode_artifact(report)}
    manifest = ExportManifest(revision.revision_id, task.task_id, analysis.artifact_id,
                              report.artifact_id,
                              {name: artifact_digest(body) for name, body in bodies.items()})
    return asdict(ExportPackage(1, manifest, **{
        name: json.loads(body) for name, body in bodies.items()}))


def _export_selective(results, tasks, revisions, report):
    selection = results.get(report.parent_id)
    if selection.kind != "selection":
        raise CorruptArtifact("selective report parent is not a selection")
    analysis = results.get(selection.parent_id)
    if analysis.kind != "analysis":
        raise CorruptArtifact("selection parent is not an analysis")
    task = tasks.get(analysis.parent_id)
    revision = revisions.get(task.revision_id)
    bodies = {"revision": encode_revision(revision), "task": encode_task(task),
              "analysis": encode_artifact(analysis), "selection": encode_artifact(selection),
              "report": encode_artifact(report)}
    manifest = {"revision_id": revision.revision_id, "task_id": task.task_id,
                "analysis_id": analysis.artifact_id, "selection_id": selection.artifact_id,
                "report_id": report.artifact_id,
                "digests": {name: artifact_digest(body) for name, body in bodies.items()}}
    return {"version": 2, "manifest": manifest,
            **{name: json.loads(body) for name, body in bodies.items()}}


def export_report(results, tasks, revisions, report_id):
    report = results.get(report_id)
    if report.kind == "report":
        package = _export_ordinary(results, report)
    elif report.kind == "selective_report":
        package = _export_selective(results, tasks, revisions, report)
    else:
        raise UnknownResult("expected a report")
    checked = verify_export_package(package)
    if not checked.valid:
        raise CorruptArtifact("; ".join(checked.errors))
    return package
