from dataclasses import dataclass
from fractions import Fraction
from selection.request import AnalysisRequest, validate_request
from selection.statistics import PrefixStatistics, SegmentStatistics
from selection.partition import initial_partition, apply_split, validate_partition
from selection.candidates import iter_candidates, choose_candidate


@dataclass(frozen=True)
class SplitStep:
    l: int
    c: int
    r: int
    gain: Fraction


@dataclass(frozen=True)
class AnalysisResult:
    revision_id: str
    request: AnalysisRequest
    steps: tuple[SplitStep, ...]
    leaves: tuple[SegmentStatistics, ...]


def run_greedy(revision, request):
    checked = validate_request(request.noise_variance, request.min_leaf, request.splits)
    values = revision.values
    leaves = initial_partition(len(values), checked.min_leaf)
    if checked.splits > len(values) // checked.min_leaf - 1:
        raise ValueError("too many splits for input size")
    prefix = PrefixStatistics.from_values(values)
    steps = []
    for _ in range(checked.splits):
        winner = choose_candidate(iter_candidates(prefix, leaves, checked.min_leaf))
        steps.append(SplitStep(winner.l, winner.c, winner.r, winner.gain))
        leaves = apply_split(leaves, winner.l, winner.c, winner.r, checked.min_leaf)
    validate_partition(leaves, len(values), checked.min_leaf)
    return AnalysisResult(revision.revision_id, checked, tuple(steps),
                          tuple(prefix.segment(leaf.l, leaf.r) for leaf in leaves))
