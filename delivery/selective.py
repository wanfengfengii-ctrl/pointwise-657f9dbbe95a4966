from selection.event import build_selection_event
from inference.selective import compute_selective_report
from archive.schema import UnknownResult


class SelectiveCoordinator:
    def __init__(self, revisions, tasks, results):
        self.revisions, self.tasks, self.results = revisions, tasks, results

    def freeze_selection(self, analysis_id):
        envelope = self.results.get(analysis_id)
        if envelope.kind != "analysis":
            raise UnknownResult("expected a published analysis: " + analysis_id)
        existing = self.results.find_selection(analysis_id)
        if existing is not None:
            return existing
        task = self.tasks.get(envelope.parent_id)
        revision = self.revisions.get(task.revision_id)
        event = build_selection_event(analysis_id, revision, envelope.data)
        return self.results.publish_selection(analysis_id, event)

    def selective_test(self, selection_id, left_leaf):
        envelope = self.results.get(selection_id)
        if envelope.kind != "selection":
            raise UnknownResult("expected a frozen selection: " + selection_id)
        if type(left_leaf) is not int or left_leaf not in (0, 1):
            raise ValueError("left_leaf must be the non-boolean integer 0 or 1")
        existing = self.results.find_selective_report(selection_id, left_leaf)
        if existing is not None:
            return existing
        report = compute_selective_report(selection_id, envelope.data, left_leaf)
        return self.results.publish_selective_report(selection_id, report)
