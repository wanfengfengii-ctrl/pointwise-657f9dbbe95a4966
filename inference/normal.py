from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import math


@dataclass(frozen=True)
class NormalSummary:
    variance: Fraction
    standard_error: str
    p: float


def two_sided_normal_p(z, variance):
    if not isinstance(z, Fraction) or not isinstance(variance, Fraction) or variance <= 0:
        raise ValueError("exact contrast and positive variance required")
    if not z:
        return 1.0
    squared_argument = z * z / (2 * variance)
    if squared_argument > 800:
        return 0.0
    return min(1.0, max(0.0, math.erfc(math.sqrt(float(squared_argument)))))


def known_variance_summary(z, variance):
    p = two_sided_normal_p(z, variance)
    with localcontext() as context:
        context.prec = 40
        context.Emax = 999999999
        context.Emin = -999999999
        se = (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
    return NormalSummary(variance, str(se), p)
