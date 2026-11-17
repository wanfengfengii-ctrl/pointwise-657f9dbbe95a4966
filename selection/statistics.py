from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class SegmentStatistics:
    l: int
    r: int
    count: int
    total: Fraction
    sum_squares: Fraction
    mean: Fraction
    sse: Fraction


@dataclass(frozen=True)
class PrefixStatistics:
    sums: tuple[Fraction, ...]
    squares: tuple[Fraction, ...]

    @classmethod
    def from_values(cls, values):
        sums, squares = [Fraction(0)], [Fraction(0)]
        for value in values:
            if not isinstance(value, Fraction):
                raise ValueError("statistics require normalized Fraction values")
            sums.append(sums[-1] + value)
            squares.append(squares[-1] + value * value)
        return cls(tuple(sums), tuple(squares))

    def segment(self, l, r):
        if type(l) is not int or type(r) is not int or not 0 <= l < r < len(self.sums):
            raise ValueError("invalid half-open segment")
        count = r - l
        total = self.sums[r] - self.sums[l]
        squares = self.squares[r] - self.squares[l]
        return SegmentStatistics(l, r, count, total, squares, total / count,
                                 squares - total * total / count)


def loss_drop(prefix, l, c, r):
    left, right, parent = (prefix.segment(l, c), prefix.segment(c, r),
                           prefix.segment(l, r))
    return parent.sse - left.sse - right.sse
