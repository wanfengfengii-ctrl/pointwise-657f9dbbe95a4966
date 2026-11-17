from inference.contrasts import build_contrast
from inference.report import ReportRequest, build_report
from archive.schema import UnknownResult


class ReportCoordinator:
    def __init__(self, revisions, tasks, results):
        self.revisions, self.tasks, self.results = revisions, tasks, results

    def report_contrast(self, analysis_id, left_leaf):
        analysis = self.results.get(analysis_id)
        if analysis.kind != "analysis":
            raise UnknownResult("expected a published analysis: " + analysis_id)
        task = self.tasks.get(analysis.parent_id)
        revision = self.revisions.get(task.revision_id)
        build_contrast(analysis.data.leaves, len(revision.values), left_leaf)
        existing = self.results.find_report(analysis_id, left_leaf)
        if existing is not None:
            return existing
        report = build_report(ReportRequest(analysis_id, left_leaf), analysis.data, revision)
        return self.results.publish_report(analysis_id, report)
