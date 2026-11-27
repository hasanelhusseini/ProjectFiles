from .tracing import tracer


def _identity(x):
    return x


def counting_sort(items, key=_identity, low=None, high=None, label="counting"):
    n = len(items)
    if n == 0:
        return []
    keys = [0] * n
    for i in range(n):
        keys[i] = key(items[i])
    if low is None or high is None:
        low = keys[0]
        high = keys[0]
        for k in keys:
            if k < low:
                low = k
            if k > high:
                high = k
    span = high - low + 1
    counts = [0] * span
    for k in keys:
        if k < low or k > high:
            raise ValueError(f"key {k} outside range [{low}, {high}]")
        counts[k - low] += 1
    if tracer.active and span <= 16:
        tracer.log(f"{label}: counts for keys {low}..{high} = {counts}")
    total = 0
    for i in range(span):
        c = counts[i]
        counts[i] = total
        total += c
    if tracer.active and span <= 16:
        tracer.log(f"{label}: starting positions = {counts}")
    output = [None] * n
    for i in range(n):
        slot = keys[i] - low
        output[counts[slot]] = items[i]
        counts[slot] += 1
    return output


def counting_sort_priority(flights):
    return counting_sort(flights, key=_priority_of, low=1, high=3, label="counting sort priority")


def _priority_of(flight):
    return flight.priority


def radix_sort_int(items, key=_identity, base=256):
    n = len(items)
    if n == 0:
        return []
    keys = [0] * n
    largest = 0
    for i in range(n):
        k = key(items[i])
        if k < 0:
            raise ValueError("radix sort needs nonnegative integer keys")
        keys[i] = k
        if k > largest:
            largest = k
    current = list(items)
    current_keys = keys
    exp = 1
    passes = 0
    while largest // exp > 0 or passes == 0:
        counts = [0] * base
        for k in current_keys:
            counts[(k // exp) % base] += 1
        total = 0
        for d in range(base):
            c = counts[d]
            counts[d] = total
            total += c
        output = [None] * n
        output_keys = [0] * n
        for i in range(n):
            digit = (current_keys[i] // exp) % base
            output[counts[digit]] = current[i]
            output_keys[counts[digit]] = current_keys[i]
            counts[digit] += 1
        current = output
        current_keys = output_keys
        passes += 1
        if tracer.active:
            preview = ", ".join(str(k) for k in current_keys[:6])
            tracer.log(f"radix pass {passes} (digit base {base}, exp {exp}): first keys {preview}")
        exp *= base
    return current


def radix_sort_strings(items, key=_identity):
    n = len(items)
    if n == 0:
        return []
    texts = [""] * n
    longest = 0
    alphabet = 0
    for i in range(n):
        s = key(items[i])
        texts[i] = s
        if len(s) > longest:
            longest = len(s)
        for ch in s:
            if ord(ch) + 1 > alphabet:
                alphabet = ord(ch) + 1
    buckets = alphabet + 1
    current = list(range(n))
    for pos in range(longest - 1, -1, -1):
        counts = [0] * buckets
        for idx in current:
            s = texts[idx]
            counts[ord(s[pos]) + 1 if pos < len(s) else 0] += 1
        total = 0
        for d in range(buckets):
            c = counts[d]
            counts[d] = total
            total += c
        output = [0] * n
        for idx in current:
            s = texts[idx]
            digit = ord(s[pos]) + 1 if pos < len(s) else 0
            output[counts[digit]] = idx
            counts[digit] += 1
        current = output
        if tracer.active:
            preview = ", ".join(texts[i] for i in current[:6])
            tracer.log(f"string radix pass on character {pos}: first ids {preview}")
    result = [None] * n
    for i in range(n):
        result[i] = items[current[i]]
    return result


def merge_sort(items, key=_identity):
    n = len(items)
    if n <= 1:
        return list(items)
    src = list(items)
    src_keys = [key(x) for x in src]
    dst = [None] * n
    dst_keys = [None] * n
    width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid = min(lo + width, n)
            hi = min(lo + 2 * width, n)
            i, j, k = lo, mid, lo
            while i < mid and j < hi:
                if src_keys[j] < src_keys[i]:
                    dst[k] = src[j]
                    dst_keys[k] = src_keys[j]
                    j += 1
                else:
                    dst[k] = src[i]
                    dst_keys[k] = src_keys[i]
                    i += 1
                k += 1
            while i < mid:
                dst[k] = src[i]
                dst_keys[k] = src_keys[i]
                i += 1
                k += 1
            while j < hi:
                dst[k] = src[j]
                dst_keys[k] = src_keys[j]
                j += 1
                k += 1
        src, dst = dst, src
        src_keys, dst_keys = dst_keys, src_keys
        width *= 2
    return src


def sort_for_recovery(flights):
    if not flights:
        return []
    base = flights[0].original_start
    for f in flights:
        if f.original_start < base:
            base = f.original_start
    with tracer.suspend():
        by_id = radix_sort_strings(flights, key=_flight_id_of)
        by_start = radix_sort_int(by_id, key=lambda f: f.original_start - base)
        return counting_sort_priority(by_start)


def _flight_id_of(flight):
    return flight.flight_id


def sort_flights_by_id_exact(flights):
    return radix_sort_strings(flights, key=_flight_id_of)


def sort_flights_by_numeric_id(flights, encoder):
    exact = radix_sort_strings(flights, key=_flight_id_of)
    return radix_sort_int(exact, key=lambda f: encoder(f.flight_id))


def unique_sorted_strings(values):
    ordered = radix_sort_strings(values)
    result = []
    for v in ordered:
        if not result or result[-1] != v:
            result.append(v)
    return result


def binary_search(sorted_values, target):
    lo = 0
    hi = len(sorted_values) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if sorted_values[mid] == target:
            return mid
        if sorted_values[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
