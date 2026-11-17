from dataclasses import dataclass
from typing import Any
from selection.request import AnalysisRequest

SCHEMA_VERSION = 1
SCHEMA_STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS records (namespace TEXT NOT NULL, id TEXT NOT NULL, "
    "payload TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(namespace,id))",
    "CREATE TABLE IF NOT EXISTS links (namespace TEXT NOT NULL, key TEXT NOT NULL, "
    "target TEXT NOT NULL, PRIMARY KEY(namespace,key))",
)


class UnknownTask(LookupError):
    pass


class UnknownResult(LookupError):
    pass


class CorruptArtifact(ValueError):
    pass


@dataclass(frozen=True)
class FixedTask:
    task_id: str
    revision_id: str
    request: AnalysisRequest


@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_id: str
    kind: str
    parent_id: str
    data: Any
