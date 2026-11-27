import random

RULE_IDS = (101, 107, 113, 127, 131, 149, 157, 163, 173, 181,
            193, 211, 223, 227, 239, 251, 263, 269, 277, 283)
PERFECT_P = 10007


class _Bucket:
    __slots__ = ("keys", "size", "a", "b", "slots", "attempts")

    def __init__(self):
        self.keys = []
        self.size = 0
        self.a = 0
        self.b = 0
        self.slots = []
        self.attempts = 0


class PerfectHashTable:
    def __init__(self, keys=RULE_IDS, p=PERFECT_P, seed=310, space_limit_factor=4):
        unique = []
        for k in keys:
            if not isinstance(k, int) or k < 0:
                raise ValueError("keys must be nonnegative integers")
            for u in unique:
                if u == k:
                    raise ValueError(f"duplicate key {k}")
            unique.append(k)
            if k >= p:
                raise ValueError(f"key {k} must be smaller than prime p={p}")
        self.keys = unique
        self.n = len(unique)
        self.p = p
        self.m = max(1, self.n)
        self.rng = random.Random(seed)
        self.level1_attempts = 0
        self.space_limit = space_limit_factor * self.n
        self._build_level1()
        self._build_level2()

    def _h(self, a, b, m, k):
        return ((a * k + b) % self.p) % m

    def _build_level1(self):
        while True:
            self.level1_attempts += 1
            self.a = self.rng.randrange(1, self.p)
            self.b = self.rng.randrange(0, self.p)
            buckets = [_Bucket() for _ in range(self.m)]
            for k in self.keys:
                buckets[self._h(self.a, self.b, self.m, k)].keys.append(k)
            total = 0
            for bucket in buckets:
                bucket.size = len(bucket.keys)
                total += bucket.size * bucket.size
            if total <= self.space_limit:
                self.buckets = buckets
                self.second_level_slots = total
                return

    def _build_level2(self):
        for bucket in self.buckets:
            if bucket.size == 0:
                continue
            width = bucket.size * bucket.size
            while True:
                bucket.attempts += 1
                bucket.a = self.rng.randrange(1, self.p)
                bucket.b = self.rng.randrange(0, self.p)
                slots = [None] * width
                clean = True
                for k in bucket.keys:
                    j = self._h(bucket.a, bucket.b, width, k)
                    if slots[j] is not None:
                        clean = False
                        break
                    slots[j] = k
                if clean:
                    bucket.slots = slots
                    break

    def lookup(self, key):
        if not isinstance(key, int) or key < 0 or key >= self.p:
            return False, None, None
        i = self._h(self.a, self.b, self.m, key)
        bucket = self.buckets[i]
        if bucket.size == 0:
            return False, i, None
        j = self._h(bucket.a, bucket.b, bucket.size * bucket.size, key)
        return bucket.slots[j] == key, i, j

    def contains(self, key):
        return self.lookup(key)[0]

    def storage_cells(self):
        return self.m + self.second_level_slots

    def report_lines(self):
        lines = [
            f"static FKS perfect hashing of {self.n} rule IDs",
            f"prime p = {self.p}, level-1 size m = {self.m}",
            f"level-1 h(k) = ((a*k + b) mod p) mod m with a={self.a}, b={self.b} (attempts: {self.level1_attempts})",
            f"sum of s^2 over buckets = {self.second_level_slots} (limit {self.space_limit})",
            f"total storage = {self.m} level-1 cells + {self.second_level_slots} level-2 slots = {self.storage_cells()} cells,"
            f" plus 2 parameters per non-empty bucket",
        ]
        for i in range(self.m):
            bucket = self.buckets[i]
            if bucket.size == 0:
                lines.append(f"  bucket {i:>2}: empty")
                continue
            layout = " ".join("." if s is None else str(s) for s in bucket.slots)
            lines.append(
                f"  bucket {i:>2}: s={bucket.size}, table size {bucket.size * bucket.size}, "
                f"a={bucket.a}, b={bucket.b}, attempts={bucket.attempts}  [{layout}]"
            )
        return lines
