from uuid import uuid4
from selection.request import validate_request
from selection.greedy import run_greedy
from archive.schema import FixedTask, UnknownTask, CorruptArtifact
from archive.codec import encode_task, decode_task


class TaskRepository:
    def __init__(self, store, revisions):
        self.store, self.revisions = store, revisions

    def create_analysis(self, revision_id, noise_variance, min_leaf, splits):
        revision = self.revisions.get(revision_id)
        request = validate_request(noise_variance, min_leaf, splits)
        run_greedy(revision, request)
        task = FixedTask("task-" + uuid4().hex, revision_id, request)
        with self.store.transaction():
            self.store.insert("task", task.task_id, encode_task(task))
        return task.task_id

    def get(self, task_id):
        body = self.store.get("task", task_id)
        if body is None:
            raise UnknownTask(task_id)
        task = decode_task(body)
        if task.task_id != task_id:
            raise CorruptArtifact("task record identity mismatch")
        return task
