import random

DEFAULT_CUTOFF = 32


def zeros(rows, cols):
    return [[0] * cols for _ in range(rows)]


def classical_multiply(a, b):
    n = len(a)
    m = len(b)
    if n == 0 or m == 0:
        return []
    if len(a[0]) != m:
        raise ValueError("inner dimensions do not match")
    p = len(b[0])
    result = zeros(n, p)
    for i in range(n):
        row_a = a[i]
        row_r = result[i]
        for k in range(m):
            aik = row_a[k]
            if aik == 0:
                continue
            row_b = b[k]
            for j in range(p):
                row_r[j] += aik * row_b[j]
    return result


def _add(x, y):
    n = len(x)
    return [[x[i][j] + y[i][j] for j in range(n)] for i in range(n)]


def _sub(x, y):
    n = len(x)
    return [[x[i][j] - y[i][j] for j in range(n)] for i in range(n)]


def _split(x):
    h = len(x) // 2
    a11 = [row[:h] for row in x[:h]]
    a12 = [row[h:] for row in x[:h]]
    a21 = [row[:h] for row in x[h:]]
    a22 = [row[h:] for row in x[h:]]
    return a11, a12, a21, a22


def _join(c11, c12, c21, c22):
    top = [c11[i] + c12[i] for i in range(len(c11))]
    bottom = [c21[i] + c22[i] for i in range(len(c21))]
    return top + bottom


def _strassen_square(a, b, cutoff, counter):
    n = len(a)
    if n <= cutoff or n == 1:
        counter[0] += 1
        return classical_multiply(a, b)
    a11, a12, a21, a22 = _split(a)
    b11, b12, b21, b22 = _split(b)
    m1 = _strassen_square(_add(a11, a22), _add(b11, b22), cutoff, counter)
    m2 = _strassen_square(_add(a21, a22), b11, cutoff, counter)
    m3 = _strassen_square(a11, _sub(b12, b22), cutoff, counter)
    m4 = _strassen_square(a22, _sub(b21, b11), cutoff, counter)
    m5 = _strassen_square(_add(a11, a12), b22, cutoff, counter)
    m6 = _strassen_square(_sub(a21, a11), _add(b11, b12), cutoff, counter)
    m7 = _strassen_square(_sub(a12, a22), _add(b21, b22), cutoff, counter)
    c11 = _add(_sub(_add(m1, m4), m5), m7)
    c12 = _add(m3, m5)
    c21 = _add(m2, m4)
    c22 = _add(_sub(_add(m1, m3), m2), m6)
    return _join(c11, c12, c21, c22)


def next_power_of_two(n):
    size = 1
    while size < n:
        size *= 2
    return size


def pad(matrix, size):
    result = zeros(size, size)
    for i in range(len(matrix)):
        row = matrix[i]
        target = result[i]
        for j in range(len(row)):
            target[j] = row[j]
    return result


def strassen_multiply(a, b, cutoff=DEFAULT_CUTOFF, stats=None):
    if cutoff < 1:
        raise ValueError("cutoff must be at least 1")
    n = len(a)
    m = len(b)
    if n == 0 or m == 0:
        return []
    if len(a[0]) != m:
        raise ValueError("inner dimensions do not match")
    p = len(b[0])
    size = next_power_of_two(max(n, m, p))
    counter = [0]
    product = _strassen_square(pad(a, size), pad(b, size), cutoff, counter)
    if stats is not None:
        stats.append((size, counter[0]))
    return [row[:p] for row in product[:n]]


def random_matrix(rows, cols, rng, low=0, high=9):
    return [[rng.randint(low, high) for _ in range(cols)] for _ in range(rows)]


def matrices_equal(x, y):
    if len(x) != len(y):
        return False
    for i in range(len(x)):
        if len(x[i]) != len(y[i]):
            return False
        for j in range(len(x[i])):
            if x[i][j] != y[i][j]:
                return False
    return True


def self_check(sizes=(1, 2, 3, 5, 7, 8, 9, 16, 17), seed=7, cutoffs=(1, 2, 4)):
    rng = random.Random(seed)
    results = []
    for n in sizes:
        a = random_matrix(n, n, rng)
        b = random_matrix(n, n, rng)
        expected = classical_multiply(a, b)
        ok = True
        for c in cutoffs:
            if not matrices_equal(expected, strassen_multiply(a, b, cutoff=c)):
                ok = False
        results.append((n, ok))
    return results
