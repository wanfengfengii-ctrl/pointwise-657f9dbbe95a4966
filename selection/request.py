from dataclasses import dataclass
from fractions import Fraction
from sampling.validation import normalize_rational


@dataclass(frozen=True)
class AnalysisRequest:
    noise_variance: Fraction
    min_leaf: int
    splits: int


def validate_request(noise_variance, min_leaf, splits):
    variance = normalize_rational(noise_variance)
    if variance <= 0:
        raise ValueError("known noise variance must be positive")
    if type(min_leaf) is not int or min_leaf < 1:
        raise ValueError("min_leaf must be a positive integer")
    if type(splits) is not int or splits < 0:
        raise ValueError("splits must be a nonnegative integer")
    return AnalysisRequest(variance, min_leaf, splits)
