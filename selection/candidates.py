from dataclasses import dataclass
from fractions import Fraction
from selection.statistics import loss_drop


@dataclass(frozen=True)
class Candidate:
    l: int
    c: int
    r: int
    gain: Fraction

    @property
    def key(self):
        return self.l, self.c, self.r


def iter_candidates(prefix, leaves, min_leaf):
    for leaf in leaves:
        for cut in range(leaf.l + min_leaf, leaf.r - min_leaf + 1):
            yield Candidate(leaf.l, cut, leaf.r, loss_drop(prefix, leaf.l, cut, leaf.r))


def choose_candidate(candidates):
    winner = None
    for candidate in candidates:
        if (winner is None or candidate.gain > winner.gain or
                (candidate.gain == winner.gain and candidate.key < winner.key)):
            winner = candidate
    if winner is None:
        raise ValueError("requested split count cannot be completed")
    return winner
