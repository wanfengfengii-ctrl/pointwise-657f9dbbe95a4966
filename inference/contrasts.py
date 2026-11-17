from dataclasses import dataclass
from fractions import Fraction
from selection.partition import validate_partition


@dataclass(frozen=True)
class ContrastVector:
    left_leaf: int
    coefficients: tuple[Fraction, ...]


def build_contrast(leaves, n, left_leaf):
    validate_partition(leaves, n)
    if type(left_leaf) is not int or not 0 <= left_leaf < len(leaves) - 1:
        raise ValueError("left_leaf must identify two final adjacent leaves")
    left, right = leaves[left_leaf:left_leaf + 2]
    coefficients = [Fraction(0)] * n
    for index in range(left.l, left.r):
        coefficients[index] = Fraction(1, left.r - left.l)
    for index in range(right.l, right.r):
        coefficients[index] = -Fraction(1, right.r - right.l)
    return ContrastVector(left_leaf, tuple(coefficients))


def contrast_value(vector, values):
    if len(vector.coefficients) != len(values):
        raise ValueError("contrast and input dimensions differ")
    return sum((coefficient * value for coefficient, value
                in zip(vector.coefficients, values)), Fraction(0))


def coefficient_norm_squared(vector):
    return sum((value * value for value in vector.coefficients), Fraction(0))
