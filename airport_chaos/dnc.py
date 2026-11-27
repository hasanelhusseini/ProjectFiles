def _better(x, y):
    if x[0] != y[0]:
        return x[0] > y[0]
    if x[2] - x[1] != y[2] - y[1]:
        return x[2] - x[1] < y[2] - y[1]
    return x[1] < y[1]


def _best_of(*candidates):
    best = candidates[0]
    for c in candidates[1:]:
        if _better(c, best):
            best = c
    return best


def max_crossing(values, lo, mid, hi):
    total = 0
    left_best = None
    left_index = mid
    for i in range(mid, lo - 1, -1):
        total += values[i]
        if left_best is None or total > left_best:
            left_best = total
            left_index = i
    total = 0
    right_best = None
    right_index = mid + 1
    for j in range(mid + 1, hi + 1):
        total += values[j]
        if right_best is None or total > right_best:
            right_best = total
            right_index = j
    return (left_best + right_best, left_index, right_index)


def _solve(values, lo, hi):
    if lo == hi:
        return (values[lo], lo, lo)
    mid = (lo + hi) // 2
    left = _solve(values, lo, mid)
    right = _solve(values, mid + 1, hi)
    cross = max_crossing(values, lo, mid, hi)
    return _best_of(left, right, cross)


def max_subarray_dc(values):
    if not values:
        return (0, -1, -1)
    return _solve(values, 0, len(values) - 1)


def max_subarray_brute(values):
    if not values:
        return (0, -1, -1)
    best = None
    n = len(values)
    for i in range(n):
        total = 0
        for j in range(i, n):
            total += values[j]
            candidate = (total, i, j)
            if best is None or _better(candidate, best):
                best = candidate
    return best
