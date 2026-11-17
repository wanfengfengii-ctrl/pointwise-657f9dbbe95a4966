from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class LeafSpan:
    l: int
    r: int


def validate_partition(leaves, n, min_leaf=1):
    if type(n) is not int or n < 1 or type(min_leaf) is not int or min_leaf < 1:
        raise ValueError("invalid partition size")
    cursor = 0
    if not leaves:
        raise ValueError("empty partition")
    for leaf in leaves:
        if type(leaf.l) is not int or type(leaf.r) is not int:
            raise ValueError("integer boundaries required")
        if leaf.l != cursor or leaf.r - leaf.l < min_leaf:
            raise ValueError("leaves must cover in order without overlaps or gaps")
        cursor = leaf.r
    if cursor != n:
        raise ValueError("partition does not cover input")
    return tuple(leaves)


def initial_partition(n, min_leaf):
    return validate_partition((LeafSpan(0, n),), n, min_leaf)


def apply_split(leaves, l, c, r, min_leaf):
    n = leaves[-1].r
    validate_partition(leaves, n, min_leaf)
    old = LeafSpan(l, r)
    if old not in leaves or not l + min_leaf <= c <= r - min_leaf:
        raise ValueError("split is not legal in the active partition")
    result = []
    for leaf in leaves:
        result.extend((LeafSpan(l, c), LeafSpan(c, r)) if leaf == old else (leaf,))
    return validate_partition(tuple(result), n, min_leaf)
