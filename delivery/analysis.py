from selection.greedy import run_greedy
from archive.schema import CorruptArtifact
from sampling.revisions import UnknownRevision


class AnalysisCoordinator:
    def __init__(self, tasks, revisions, results):
        self.tasks, self.revisions, self.results = tasks, revisions, results

    def execute_analysis(self, task_id):
        task = self.tasks.get(task_id)
        existing = self.results.find_analysis(task_id)
        if existing is not None:
            return existing
        try:
            revision = self.revisions.get(task.revision_id)
        except UnknownRevision as exc:
            raise CorruptArtifact("fixed task revision is missing") from exc
        result = run_greedy(revision, task.request)
        return self.results.publish_analysis(task_id, result)
