from dataclasses import asdict
from uuid import uuid4
from sampling.revisions import UnknownRevision
from selection.statistics import PrefixStatistics, loss_drop
from selection.partition import LeafSpan
from selection.event import build_selection_event
from inference.contrasts import build_contrast, contrast_value
from inference.selective import leaf_contrast
from archive.schema import (ArtifactEnvelope, UnknownResult, UnknownTask,
                            CorruptArtifact)
from archive.codec import decode_artifact, canonical_json


class ResultRepository:
    def __init__(self, store, revisions, tasks, publications):
        self.store, self.revisions = store, revisions
        self.tasks, self.publications = tasks, publications

    def _analysis_context(self, task_id, data):
        try:
            task = self.tasks.get(task_id)
            revision = self.revisions.get(task.revision_id)
        except (UnknownTask, UnknownRevision) as exc:
            raise CorruptArtifact("analysis parent is missing") from exc
        if data.revision_id != task.revision_id or data.request != task.request:
            raise CorruptArtifact("analysis fixed input mismatch")
        prefix = PrefixStatistics.from_values(revision.values)
        if data.leaves[-1].r != len(revision.values):
            raise CorruptArtifact("analysis coverage mismatch")
        for leaf in data.leaves:
            if prefix.segment(leaf.l, leaf.r) != leaf:
                raise CorruptArtifact("analysis statistics mismatch")
        for step in data.steps:
            if loss_drop(prefix, step.l, step.c, step.r) != step.gain:
                raise CorruptArtifact("stored split gain mismatch")
        return task, revision

    def _report_context(self, analysis_id, report):
        parent = self.get(analysis_id, expected_kind="analysis")
        if parent.kind != "analysis" or report.analysis_id != analysis_id:
            raise CorruptArtifact("report does not reference an analysis")
        task, revision = self._analysis_context(parent.parent_id, parent.data)
        if (report.revision_id != revision.revision_id or
                report.noise_variance != task.request.noise_variance):
            raise CorruptArtifact("report fixed input mismatch")
        vector = build_contrast(parent.data.leaves, len(revision.values), report.left_leaf)
        if report.result.vector != vector or report.result.z != contrast_value(vector, revision.values):
            raise CorruptArtifact("report coefficients or contrast mismatch")
        return parent, task, revision

    def _selection_context(self, analysis_id, event):
        parent = self.get(analysis_id, expected_kind="analysis")
        if parent.kind != "analysis" or event.analysis_id != analysis_id:
            raise CorruptArtifact("selection does not reference an analysis")
        task, revision = self._analysis_context(parent.parent_id, parent.data)
        if event != build_selection_event(analysis_id, revision, parent.data):
            raise CorruptArtifact("selection event mismatch")
        return parent, task, revision

    def _selective_report_context(self, selection_id, report):
        parent = self.get(selection_id, expected_kind="selection")
        if parent.kind != "selection" or report.selection_id != selection_id:
            raise CorruptArtifact("report does not reference a selection")
        event = parent.data
        eta = leaf_contrast(event.leaves, len(event.values), report.left_leaf)
        z = sum((e * y for e, y in zip(eta, event.values)), 0)
        q = sum((e * e for e in eta), 0)
        if (report.z != z or
                report.variance != event.request.noise_variance * q):
            raise CorruptArtifact("selective report arithmetic mismatch")
        return parent

    def get(self, artifact_id, expected_kind=None):
        body = self.store.get("artifact", artifact_id)
        if body is None:
            raise UnknownResult(artifact_id)
        envelope = decode_artifact(body)
        if expected_kind is not None and envelope.kind != expected_kind:
            raise CorruptArtifact("unexpected parent artifact kind")
        if envelope.artifact_id != artifact_id:
            raise CorruptArtifact("artifact record identity mismatch")
        try:
            if envelope.kind == "analysis":
                if self.store.lookup("analysis", envelope.parent_id) != artifact_id:
                    raise CorruptArtifact("analysis publication association mismatch")
                self._analysis_context(envelope.parent_id, envelope.data)
            elif envelope.kind == "report":
                key = canonical_json([envelope.parent_id, envelope.data.left_leaf])
                if self.store.lookup("report", key) != artifact_id:
                    raise CorruptArtifact("report publication association mismatch")
                self._report_context(envelope.parent_id, envelope.data)
            elif envelope.kind == "selection":
                if self.store.lookup("selection", envelope.parent_id) != artifact_id:
                    raise CorruptArtifact("selection publication association mismatch")
                self._selection_context(envelope.parent_id, envelope.data)
            elif envelope.kind == "selective_report":
                key = canonical_json([envelope.parent_id, envelope.data.left_leaf])
                if self.store.lookup("selective_report", key) != artifact_id:
                    raise CorruptArtifact("selective report publication association mismatch")
                self._selective_report_context(envelope.parent_id, envelope.data)
            else:
                raise CorruptArtifact("unknown artifact kind")
        except (ValueError, UnknownResult, UnknownTask, UnknownRevision) as exc:
            if isinstance(exc, CorruptArtifact):
                raise
            raise CorruptArtifact("invalid artifact parent chain") from exc
        return envelope

    def read_result(self, artifact_id):
        return asdict(self.get(artifact_id))

    def find_analysis(self, task_id):
        self.tasks.get(task_id)
        artifact_id = self.store.lookup("analysis", task_id)
        if artifact_id is not None:
            self.get(artifact_id)
        return artifact_id

    def find_report(self, analysis_id, left_leaf):
        key = canonical_json([analysis_id, left_leaf])
        artifact_id = self.store.lookup("report", key)
        if artifact_id is not None:
            self.get(artifact_id)
        return artifact_id

    def find_selection(self, analysis_id):
        artifact_id = self.store.lookup("selection", analysis_id)
        if artifact_id is not None:
            self.get(artifact_id)
        return artifact_id

    def find_selective_report(self, selection_id, left_leaf):
        key = canonical_json([selection_id, left_leaf])
        artifact_id = self.store.lookup("selective_report", key)
        if artifact_id is not None:
            self.get(artifact_id)
        return artifact_id

    def publish_analysis(self, task_id, result):
        def check():
            self._analysis_context(task_id, result)
        envelope = ArtifactEnvelope("analysis-" + uuid4().hex, "analysis", task_id, result)
        return self.publications.publish(envelope, "analysis", task_id, check, self.get)

    def publish_report(self, analysis_id, report):
        def check():
            self._report_context(analysis_id, report)
        envelope = ArtifactEnvelope("report-" + uuid4().hex, "report", analysis_id, report)
        key = canonical_json([analysis_id, report.left_leaf])
        return self.publications.publish(envelope, "report", key, check, self.get)

    def publish_selection(self, analysis_id, event):
        def check():
            self._selection_context(analysis_id, event)
        envelope = ArtifactEnvelope("selection-" + uuid4().hex, "selection",
                                    analysis_id, event)
        return self.publications.publish(envelope, "selection", analysis_id, check, self.get)

    def publish_selective_report(self, selection_id, report):
        def check():
            self._selective_report_context(selection_id, report)
        envelope = ArtifactEnvelope("selective-report-" + uuid4().hex,
                                    "selective_report", selection_id, report)
        key = canonical_json([selection_id, report.left_leaf])
        return self.publications.publish(envelope, "selective_report", key, check, self.get)
