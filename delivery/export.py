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


def export_report(results, tasks, revisions, report_id):
    report = results.get(report_id)
    if report.kind != "report":
        raise UnknownResult("expected an ordinary report")
    analysis, task, revision = results._report_context(report.parent_id, report.data)
    bodies = {"revision": encode_revision(revision), "task": encode_task(task),
              "analysis": encode_artifact(analysis), "report": encode_artifact(report)}
    manifest = ExportManifest(revision.revision_id, task.task_id, analysis.artifact_id,
                              report.artifact_id,
                              {name: artifact_digest(body) for name, body in bodies.items()})
    package = asdict(ExportPackage(1, manifest, **{
        name: json.loads(body) for name, body in bodies.items()}))
    checked = verify_export_package(package)
    if not checked.valid:
        raise CorruptArtifact("; ".join(checked.errors))
    return package
