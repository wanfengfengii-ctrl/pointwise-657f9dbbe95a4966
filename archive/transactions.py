from typing import Callable
from archive.codec import encode_artifact
from archive.schema import CorruptArtifact

PublicationFaultHook = Callable[[str, str], None]


class PublicationCoordinator:
    def __init__(self, store, fault_hook: PublicationFaultHook | None = None):
        self.store = store
        self.fault_hook = fault_hook

    def checkpoint(self, stage, kind):
        if self.fault_hook is not None:
            self.fault_hook(stage, kind)

    def publish(self, envelope, link_namespace, link_key, check_parent, read_existing):
        with self.store.transaction():
            check_parent()
            existing = self.store.lookup(link_namespace, link_key)
            if existing is not None:
                prior = read_existing(existing)
                if (prior.kind != envelope.kind or prior.parent_id != envelope.parent_id or
                        prior.data != envelope.data):
                    raise CorruptArtifact("publication key conflicts with fixed content")
                return existing
            self.checkpoint("before_insert", envelope.kind)
            self.store.insert("artifact", envelope.artifact_id, encode_artifact(envelope))
            self.checkpoint("after_insert", envelope.kind)
            self.store.link(link_namespace, link_key, envelope.artifact_id)
            self.checkpoint("before_commit", envelope.kind)
        return envelope.artifact_id
