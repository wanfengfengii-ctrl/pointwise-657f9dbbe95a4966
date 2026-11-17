from dataclasses import dataclass
from fractions import Fraction
from inference.contrasts import (ContrastVector, contrast_value,
                                coefficient_norm_squared)
from inference.normal import NormalSummary, known_variance_summary


@dataclass(frozen=True)
class UnadjustedResult:
    vector: ContrastVector
    z: Fraction
    norm_squared: Fraction
    normal: NormalSummary


def compute_unadjusted(vector, values, noise_variance):
    norm = coefficient_norm_squared(vector)
    if norm <= 0 or not isinstance(noise_variance, Fraction) or noise_variance <= 0:
        raise ValueError("nonzero contrast and positive known noise variance required")
    z = contrast_value(vector, values)
    return UnadjustedResult(vector, z, norm,
                            known_variance_summary(z, noise_variance * norm))
