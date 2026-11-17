from uuid import uuid4
from sampling.types import SeriesRevision
from sampling.validation import normalize_import
from archive.codec import (encode_import_payload, encode_revision, decode_revision,
                           canonical_json)
from archive.schema import CorruptArtifact


class ConflictError(ValueError):
    pass


class UnknownRevision(LookupError):
    pass


class RevisionRepository:
    def __init__(self, store):
        self.store = store

    def put(self, payload):
        payload = normalize_import(payload.series_id, payload.source_version,
                                   payload.unit, payload.rows, payload.correction_parent)
        key = canonical_json([payload.series_id, payload.source_version])
        with self.store.transaction():
            existing = self.store.lookup("source", key)
            if existing is not None:
                old = self.get(existing)
                if encode_import_payload(old.payload) != encode_import_payload(payload):
                    raise ConflictError("source version already has another payload")
                return existing
            if payload.correction_parent is not None:
                try:
                    parent = self.get(payload.correction_parent)
                except UnknownRevision as exc:
                    raise ValueError("unknown correction parent") from exc
                if parent.payload.series_id != payload.series_id:
                    raise ValueError("correction parent belongs to another series")
                if parent.payload.source_version == payload.source_version:
                    raise ValueError("correction requires a new source version")
            revision_id = "rev-" + uuid4().hex
            revision = SeriesRevision(revision_id, payload)
            self.store.insert("revision", revision_id, encode_revision(revision))
            self.store.link("source", key, revision_id)
            return revision_id

    def get(self, revision_id):
        body = self.store.get("revision", revision_id)
        if body is None:
            raise UnknownRevision(revision_id)
        revision = decode_revision(body)
        if revision.revision_id != revision_id:
            raise CorruptArtifact("revision record identity mismatch")
        return revision
