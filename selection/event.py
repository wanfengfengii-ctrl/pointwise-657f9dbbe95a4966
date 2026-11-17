"""Frozen two-split selection events produced from a published analysis."""
from dataclasses import dataclass
from fractions import Fraction
from sampling.validation import identity
from selection.request import AnalysisRequest, validate_request

MIN_ROWS = 8
MAX_ROWS = 40
EVENT_MIN_LEAF = 2
EVENT_SPLITS = 2


@dataclass(frozen=True)
class StageRecord:
    winner: tuple
    candidates: tuple


@dataclass(frozen=True)
class SelectionEvent:
    analysis_id: str
    revision_id: str
    request: AnalysisRequest
    values: tuple
    leaves: tuple
    stages: tuple


def _triple(value, name):
    if (type(value) is not tuple or len(value) != 3 or
            any(type(item) is not int for item in value)):
        raise ValueError("invalid " + name)
    return value


def replay_stages(winners, count, min_leaf=EVENT_MIN_LEAF):
    """Replay ordered winning splits, enumerating every legal candidate per stage."""
    active = [(0, count)]
    stages = []
    for winner in winners:
        _triple(winner, "winner")
        candidates = tuple(sorted(
            (l, c, r) for l, r in active
            for c in range(l + min_leaf, r - min_leaf + 1)))
        if winner not in candidates:
            raise ValueError("winner is not a legal candidate at its stage")
        stages.append(StageRecord(winner, candidates))
        l, c, r = winner
        active.remove((l, r))
        active.extend(((l, c), (c, r)))
        active.sort()
    return tuple(stages), tuple(active)


def build_selection_event(analysis_id, revision, result):
    """Freeze the ordered winning sequence of a finished analysis as an event."""
    request = result.request
    values = tuple(revision.values)
    if (request.min_leaf != EVENT_MIN_LEAF or request.splits != EVENT_SPLITS or
            not MIN_ROWS <= len(values) <= MAX_ROWS):
        raise ValueError(
            "selective freezing requires 8..40 rows, min_leaf=2 and splits=2")
    stages, leaves = replay_stages(
        tuple((step.l, step.c, step.r) for step in result.steps), len(values))
    if leaves != tuple((leaf.l, leaf.r) for leaf in result.leaves):
        raise ValueError("analysis steps and final leaves differ")
    return SelectionEvent(analysis_id, revision.revision_id, request, values,
                          leaves, stages)


def validate_stage_record(stage):
    if type(stage.winner) is not tuple:
        raise ValueError("invalid stage winner")
    _triple(stage.winner, "winner")
    if type(stage.candidates) is not tuple or not stage.candidates:
        raise ValueError("invalid stage candidates")
    for candidate in stage.candidates:
        _triple(candidate, "candidate")
    if stage.candidates != tuple(sorted(set(stage.candidates))):
        raise ValueError("candidates must be sorted and distinct")
    if stage.winner not in stage.candidates:
        raise ValueError("winner missing from candidates")
    return stage


def validate_selection_event(event):
    identity(event.analysis_id, "analysis_id")
    identity(event.revision_id, "revision_id")
    if type(event.request) is not AnalysisRequest:
        raise ValueError("invalid selection request")
    if validate_request(event.request.noise_variance, event.request.min_leaf,
                        event.request.splits) != event.request:
        raise ValueError("invalid selection request")
    if (event.request.min_leaf != EVENT_MIN_LEAF or
            event.request.splits != EVENT_SPLITS):
        raise ValueError("selection events require min_leaf=2 and splits=2")
    values = event.values
    if (type(values) is not tuple or not values or
            not MIN_ROWS <= len(values) <= MAX_ROWS or
            any(type(value) is not Fraction for value in values)):
        raise ValueError("invalid selection values")
    leaves = event.leaves
    if type(leaves) is not tuple or len(leaves) != event.request.splits + 1:
        raise ValueError("invalid selection leaves")
    cursor = 0
    for leaf in leaves:
        if (type(leaf) is not tuple or len(leaf) != 2 or
                any(type(bound) is not int for bound in leaf)):
            raise ValueError("invalid selection leaf")
        l, r = leaf
        if l != cursor or r - l < event.request.min_leaf:
            raise ValueError("selection leaves must cover in order")
        cursor = r
    if cursor != len(values):
        raise ValueError("selection leaves do not cover the values")
    if type(event.stages) is not tuple or len(event.stages) != event.request.splits:
        raise ValueError("invalid selection stages")
    for stage in event.stages:
        if type(stage) is not StageRecord:
            raise ValueError("invalid stage record")
        validate_stage_record(stage)
    stages, final = replay_stages([stage.winner for stage in event.stages],
                                  len(values), event.request.min_leaf)
    if stages != event.stages or final != leaves:
        raise ValueError("stage candidates and leaves are inconsistent")
    return event
