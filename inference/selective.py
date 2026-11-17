"""Conditional two-sided normal test on the frozen selection event.

The frozen event fixes the ordered winning splits. Along the line
y(z) = u + eta z / q every candidate gain is a rational quadratic in z,
so the set S of z reproducing the same ordered winners is an exact union
of intervals whose endpoints are rational or real quadratic algebraic.
"""
from dataclasses import dataclass
from fractions import Fraction
from functools import cmp_to_key
import math

from sampling.validation import identity

MIN_MASS = 1e-8


@dataclass(frozen=True)
class QuadRoot:
    """The root-th real root of poly[0] z^2 + poly[1] z + poly[2] = 0."""
    poly: tuple
    root: int


@dataclass(frozen=True)
class SupportInterval:
    lo: object
    hi: object
    lo_closed: bool
    hi_closed: bool


@dataclass(frozen=True)
class SelectiveReport:
    selection_id: str
    left_leaf: int
    z: Fraction
    variance: Fraction
    support: tuple
    p: float


# Exact endpoint arithmetic -------------------------------------------------

def _vertex(poly):
    a, b, _ = poly
    return Fraction(-b, 2 * a)


def _eval_poly(poly, t):
    a, b, c = poly
    return a * t * t + b * t + c


def _isolation(quad):
    """Rational interval strictly enclosing the quad's root."""
    a, b, c = quad.poly
    bound = Fraction(1) + Fraction(max(abs(b), abs(c)), a)
    vertex = _vertex(quad.poly)
    return (-bound, vertex) if quad.root == 0 else (vertex, bound)


def _refine(quad, interval):
    lo, hi = interval
    mid = (lo + hi) / 2
    sign = _eval_poly(quad.poly, mid)
    if quad.root == 0:  # f(lo) > 0 > f(hi)
        return (mid, hi) if sign > 0 else (lo, mid)
    return (lo, mid) if sign > 0 else (mid, hi)  # f(lo) < 0 < f(hi)


def _compare_root_rational(quad, t):
    """Sign of (quad's root - t) for rational t."""
    value = _eval_poly(quad.poly, t)
    if value < 0:  # t lies strictly between the two roots r0 < t < r1
        return 1 if quad.root == 1 else -1
    # value > 0: roots are irrational, so t is outside them
    return 1 if t < _vertex(quad.poly) else -1


def compare_endpoints(first, second):
    """Total order on finite endpoints (Fraction or QuadRoot)."""
    if isinstance(first, Fraction) and isinstance(second, Fraction):
        return (first > second) - (first < second)
    if isinstance(first, QuadRoot) and isinstance(second, QuadRoot):
        if first.poly == second.poly:
            return (first.root > second.root) - (first.root < second.root)
        left, right = _isolation(first), _isolation(second)
        while True:
            if left[1] < right[0]:
                return -1
            if right[1] < left[0]:
                return 1
            left = _refine(first, left)
            right = _refine(second, right)
    if isinstance(first, QuadRoot):
        return _compare_root_rational(first, second)
    return -_compare_root_rational(second, first)


def _bounds(endpoint):
    if isinstance(endpoint, Fraction):
        return (endpoint, endpoint)
    return _isolation(endpoint)


def rational_between(first, second):
    """A rational strictly between two distinct ordered endpoints."""
    left, right = _bounds(first), _bounds(second)
    while not left[1] < right[0]:
        if isinstance(first, QuadRoot):
            left = _refine(first, left)
        if isinstance(second, QuadRoot):
            right = _refine(second, right)
    return (left[1] + right[0]) / 2


def rational_below(endpoint):
    if isinstance(endpoint, Fraction):
        return endpoint - 1
    return _isolation(endpoint)[0]


def rational_above(endpoint):
    if isinstance(endpoint, Fraction):
        return endpoint + 1
    return _isolation(endpoint)[1]


# Constraint algebra --------------------------------------------------------

def leaf_contrast(leaves, count, left_leaf):
    coefficients = [Fraction(0)] * count
    l, r = leaves[left_leaf]
    l2, r2 = leaves[left_leaf + 1]
    for i in range(l, r):
        coefficients[i] = Fraction(1, r - l)
    for i in range(l2, r2):
        coefficients[i] = Fraction(-1, r2 - l2)
    return tuple(coefficients)


def _gain_coeffs(prefix_u, prefix_w, l, c, r):
    """Gain of (l,c,r) along y(z) as (A, B, C) with gain = A z^2 + B z + C."""
    u1, u2, u3 = (prefix_u[c] - prefix_u[l], prefix_u[r] - prefix_u[c],
                  prefix_u[r] - prefix_u[l])
    w1, w2, w3 = (prefix_w[c] - prefix_w[l], prefix_w[r] - prefix_w[c],
                  prefix_w[r] - prefix_w[l])
    n1, n2, n3 = c - l, r - c, r - l
    a = w1 * w1 / n1 + w2 * w2 / n2 - w3 * w3 / n3
    b = 2 * (u1 * w1 / n1 + u2 * w2 / n2 - u3 * w3 / n3)
    c0 = u1 * u1 / n1 + u2 * u2 / n2 - u3 * u3 / n3
    return a, b, c0


def _constraints(event, prefix_u, prefix_w):
    """(A, B, C, strict) with D(z) = A z^2 + B z + C = winner - candidate."""
    result = []
    for stage in event.stages:
        winner = stage.winner
        aw, bw, cw = _gain_coeffs(prefix_u, prefix_w, *winner)
        for candidate in stage.candidates:
            if candidate == winner:
                continue
            a, b, c = _gain_coeffs(prefix_u, prefix_w, *candidate)
            result.append((aw - a, bw - b, cw - c, candidate < winner))
    return result


def _roots(a, b, c):
    """Real roots of a z^2 + b z + c as exact endpoints."""
    if a == 0:
        return () if b == 0 else (Fraction(-c, b),)
    disc = b * b - 4 * a * c
    if disc < 0:
        return ()
    if disc == 0:
        return (Fraction(-b, 2 * a),)
    lcm = math.lcm(a.denominator, b.denominator, c.denominator)
    ai, bi, ci = int(a * lcm), int(b * lcm), int(c * lcm)
    g = math.gcd(math.gcd(abs(ai), abs(bi)), abs(ci))
    ai, bi, ci = ai // g, bi // g, ci // g
    if ai < 0:
        ai, bi, ci = -ai, -bi, -ci
    di = bi * bi - 4 * ai * ci
    root = math.isqrt(di)
    if root * root == di:
        return (Fraction(-bi - root, 2 * ai), Fraction(-bi + root, 2 * ai))
    return (QuadRoot((ai, bi, ci), 0), QuadRoot((ai, bi, ci), 1))


def _ok_at_rational(a, b, c, strict, t):
    value = a * t * t + b * t + c
    return value > 0 if strict else value >= 0


def _ok_at_root(a, b, c, strict, quad):
    """Exact sign of a z^2 + b z + c at the quadratic endpoint."""
    pa, pb, pc = quad.poly
    alpha = b - a * Fraction(pb, pa)
    beta = c - a * Fraction(pc, pa)
    if alpha == 0:
        return beta > 0 if strict else beta >= 0
    # D(root) = alpha * (root - t) with rational t; root != t (irrational),
    # so D(root) != 0 and both strict and non-strict reduce to sign > 0.
    sign = (1 if alpha > 0 else -1) * _compare_root_rational(quad, -beta / alpha)
    return sign > 0


def _dedup_sorted(points):
    ordered = sorted(points, key=cmp_to_key(compare_endpoints))
    result = []
    for point in ordered:
        if result and compare_endpoints(result[-1], point) == 0:
            continue
        result.append(point)
    return result


def build_support(constraints):
    """Exact maximal connected components of the intersection set S."""
    points = _dedup_sorted([root for a, b, c, _ in constraints
                            for root in _roots(a, b, c)])
    pieces = []
    previous = None
    for point in points:
        pieces.append(("interval", previous, point))
        pieces.append(("point", point, point))
        previous = point
    pieces.append(("interval", previous, None))
    inside = []
    for kind, lo, hi in pieces:
        if kind == "point":
            inside.append(all(
                _ok_at_root(a, b, c, strict, lo) if isinstance(lo, QuadRoot)
                else _ok_at_rational(a, b, c, strict, lo)
                for a, b, c, strict in constraints))
        else:
            if lo is None and hi is None:
                probe = Fraction(0)
            elif lo is None:
                probe = rational_below(hi)
            elif hi is None:
                probe = rational_above(lo)
            else:
                probe = rational_between(lo, hi)
            inside.append(all(
                _ok_at_rational(a, b, c, strict, probe)
                for a, b, c, strict in constraints))
    components = []
    index = 0
    while index < len(pieces):
        if not inside[index]:
            index += 1
            continue
        end = index
        while end + 1 < len(pieces) and inside[end + 1]:
            end += 1
        first, last = pieces[index], pieces[end]
        lo, lo_closed = ((first[1], True) if first[0] == "point"
                         else (first[1], False))
        hi, hi_closed = ((last[1], True) if last[0] == "point"
                         else (last[2], False))
        components.append(SupportInterval(lo, hi, lo_closed, hi_closed))
        index = end + 1
    return tuple(components)


# Conditional probability ---------------------------------------------------

def _endpoint_float(endpoint):
    if isinstance(endpoint, Fraction):
        return float(endpoint)
    a, b, c = endpoint.poly
    disc = math.sqrt(float(b * b - 4 * a * c))
    if b >= 0:
        q = -(b + disc) / 2.0
        small, large = q / a, c / q
    else:
        q = (-b + disc) / 2.0
        small, large = c / q, q / a
    return small if endpoint.root == 0 else large


def _mass(lo, hi, scale):
    if not lo < hi:
        return 0.0
    return 0.5 * (math.erfc(lo / scale) - math.erfc(hi / scale))


def conditional_probability(support, z0, variance):
    """P(|Z| >= |z0| and Z in S) / P(Z in S) for Z ~ N(0, variance)."""
    scale = math.sqrt(2.0 * float(variance))
    limit = abs(float(z0))
    denominator = 0.0
    numerator = 0.0
    for component in support:
        lo = -math.inf if component.lo is None else _endpoint_float(component.lo)
        hi = math.inf if component.hi is None else _endpoint_float(component.hi)
        denominator += _mass(lo, hi, scale)
        numerator += (_mass(lo, min(hi, -limit), scale) +
                      _mass(max(lo, limit), hi, scale))
    if denominator < MIN_MASS:
        raise ValueError("conditional selection mass is below 1e-8")
    return min(1.0, max(0.0, numerator / denominator))


def compute_selective_report(selection_id, event, left_leaf):
    values = tuple(event.values)
    count = len(values)
    eta = leaf_contrast(event.leaves, count, left_leaf)
    q = sum((e * e for e in eta), Fraction(0))
    z0 = sum((e * y for e, y in zip(eta, values)), Fraction(0))
    w = [e / q for e in eta]
    u = [y - wi * z0 for y, wi in zip(values, w)]
    prefix_u, prefix_w = [Fraction(0)], [Fraction(0)]
    for i in range(count):
        prefix_u.append(prefix_u[-1] + u[i])
        prefix_w.append(prefix_w[-1] + w[i])
    support = build_support(_constraints(event, prefix_u, prefix_w))
    variance = event.request.noise_variance * q
    p = conditional_probability(support, z0, variance)
    return SelectiveReport(selection_id, left_leaf, z0, variance, support, p)


# Structural validation ------------------------------------------------------

def validate_quad_root(quad):
    poly = quad.poly
    if (type(poly) is not tuple or len(poly) != 3 or
            any(type(coefficient) is not int for coefficient in poly)):
        raise ValueError("invalid quadratic polynomial")
    a, b, c = poly
    if a <= 0 or math.gcd(math.gcd(abs(a), abs(b)), abs(c)) != 1:
        raise ValueError("quadratic polynomial must be primitive with a>0")
    disc = b * b - 4 * a * c
    if disc <= 0 or math.isqrt(disc) ** 2 == disc:
        raise ValueError("quadratic roots must be irrational")
    if type(quad.root) is not int or quad.root not in (0, 1):
        raise ValueError("invalid quadratic root index")
    return quad


def _validate_endpoint(endpoint):
    if endpoint is None or isinstance(endpoint, Fraction):
        return
    if isinstance(endpoint, QuadRoot):
        validate_quad_root(endpoint)
        return
    raise ValueError("invalid support endpoint")


def validate_support_interval(interval):
    if type(interval.lo_closed) is not bool or type(interval.hi_closed) is not bool:
        raise ValueError("invalid interval closure flags")
    _validate_endpoint(interval.lo)
    _validate_endpoint(interval.hi)
    if interval.lo is None and interval.lo_closed:
        raise ValueError("infinite lower end cannot be closed")
    if interval.hi is None and interval.hi_closed:
        raise ValueError("infinite upper end cannot be closed")
    if interval.lo is not None and interval.hi is not None:
        order = compare_endpoints(interval.lo, interval.hi)
        if order > 0:
            raise ValueError("interval ends are out of order")
        if order == 0 and not (interval.lo_closed and interval.hi_closed):
            raise ValueError("degenerate interval must be a closed point")
    return interval


def validate_selective_report(report):
    identity(report.selection_id, "selection_id")
    if type(report.left_leaf) is not int or report.left_leaf not in (0, 1):
        raise ValueError("left_leaf must be the integer 0 or 1")
    if type(report.z) is not Fraction:
        raise ValueError("invalid exact contrast")
    if type(report.variance) is not Fraction or report.variance <= 0:
        raise ValueError("invalid contrast variance")
    if (type(report.p) is not float or not math.isfinite(report.p) or
            not 0 <= report.p <= 1):
        raise ValueError("invalid conditional probability")
    if type(report.support) is not tuple:
        raise ValueError("invalid support")
    previous = None
    for interval in report.support:
        if type(interval) is not SupportInterval:
            raise ValueError("invalid support interval")
        validate_support_interval(interval)
        if previous is not None:
            if previous.hi is None or interval.lo is None:
                raise ValueError("support intervals are not ordered")
            order = compare_endpoints(previous.hi, interval.lo)
            if order > 0:
                raise ValueError("support intervals overlap")
            if order == 0 and (previous.hi_closed or interval.lo_closed):
                raise ValueError("adjacent intervals must be merged")
        previous = interval
    return report
