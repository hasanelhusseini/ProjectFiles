import random

from .tracing import tracer

PRIME_P = (1 << 61) - 1
ENCODE_BASE = 257


def encode_id(text):
    code = 0
    for ch in text:
        code = (code * ENCODE_BASE + ord(ch)) % PRIME_P
    return code


class DuplicateKeyError(KeyError):
    pass


class _Tombstone:
    def __repr__(self):
        return "<TOMBSTONE>"


TOMBSTONE = _Tombstone()


class UniversalHashTable:
    def __init__(self, capacity=16, max_load=0.5, seed=310, encoder=encode_id, auto_resize=True):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if not 0 < max_load < 1:
            raise ValueError("max_load must be in (0, 1)")
        self.p = PRIME_P
        self.max_load = max_load
        self.auto_resize = auto_resize
        self.encoder = encoder
        self._rng = random.Random(seed)
        self.m = capacity
        self.a = 1
        self.b = 0
        self._choose_parameters()
        self._keys = [None] * self.m
        self._values = [None] * self.m
        self.size = 0
        self.tombstones = 0
        self.resizes = 0
        self.insert_count = 0
        self.insert_probes = 0
        self.home_collisions = 0
        self.probe_collisions = 0
        self.lookup_count = 0
        self.lookup_probes = 0
        self.last_probes = 0

    def _choose_parameters(self):
        self.a = self._rng.randrange(1, self.p)
        self.b = self._rng.randrange(0, self.p)

    def hash_code(self, code):
        return ((self.a * code + self.b) % self.p) % self.m

    def home_slot(self, key):
        return self.hash_code(self.encoder(key))

    @property
    def load_factor(self):
        return self.size / self.m

    @property
    def occupied_factor(self):
        return (self.size + self.tombstones) / self.m

    def __len__(self):
        return self.size

    def __contains__(self, key):
        return self.get(key) is not None

    def _locate(self, key):
        code = self.encoder(key)
        index = self.hash_code(code)
        tracer.log(f"hash '{key}': k={code}, h(k)=((a*k+b) mod p) mod {self.m} = {index}")
        probes = 0
        first_tomb = -1
        for step in range(self.m):
            slot = (index + step) % self.m
            probes += 1
            stored = self._keys[slot]
            if stored is None:
                tracer.log(f"  probe {probes}: slot {slot} EMPTY")
                return -1, slot if first_tomb < 0 else first_tomb, probes
            if stored is TOMBSTONE:
                tracer.log(f"  probe {probes}: slot {slot} TOMBSTONE")
                if first_tomb < 0:
                    first_tomb = slot
                continue
            if stored == key:
                tracer.log(f"  probe {probes}: slot {slot} MATCH '{stored}'")
                return slot, first_tomb, probes
            tracer.log(f"  probe {probes}: slot {slot} occupied by '{stored}'")
        return -1, first_tomb, probes

    def insert(self, key, value):
        if not isinstance(key, str) or key == "":
            raise ValueError("key must be a non-empty string")
        if self.auto_resize and (self.size + self.tombstones + 1) / self.m > self.max_load:
            self._rehash()
        found, free_slot, probes = self._locate(key)
        if found >= 0:
            self.last_probes = probes
            raise DuplicateKeyError(key)
        if free_slot < 0:
            raise OverflowError("hash table is full")
        self.insert_count += 1
        self.insert_probes += probes
        self.last_probes = probes
        if probes > 1:
            self.home_collisions += 1
            self.probe_collisions += probes - 1
        if self._keys[free_slot] is TOMBSTONE:
            self.tombstones -= 1
        self._keys[free_slot] = key
        self._values[free_slot] = value
        self.size += 1
        return probes

    def get(self, key):
        found, _, probes = self._locate(key)
        self.lookup_count += 1
        self.lookup_probes += probes
        self.last_probes = probes
        if found < 0:
            return None
        return self._values[found]

    def lookup(self, key):
        value = self.get(key)
        return value, self.last_probes

    def delete(self, key):
        found, _, probes = self._locate(key)
        self.last_probes = probes
        if found < 0:
            return None
        value = self._values[found]
        self._keys[found] = TOMBSTONE
        self._values[found] = None
        self.size -= 1
        self.tombstones += 1
        tracer.log(f"  slot {found} marked TOMBSTONE")
        return value

    def _rehash(self):
        old_keys = self._keys
        old_values = self._values
        if (self.size + 1) / self.m > self.max_load / 2:
            new_m = self.m * 2
        else:
            new_m = self.m
        while (self.size + 1) / new_m > self.max_load:
            new_m *= 2
        tracer.log(f"rehash: m {self.m} -> {new_m}, dropping {self.tombstones} tombstones")
        self.m = new_m
        self._choose_parameters()
        self._keys = [None] * self.m
        self._values = [None] * self.m
        self.size = 0
        self.tombstones = 0
        self.resizes += 1
        with tracer.suspend():
            for i in range(len(old_keys)):
                stored = old_keys[i]
                if stored is not None and stored is not TOMBSTONE:
                    self._place_without_resize(stored, old_values[i])

    def _place_without_resize(self, key, value):
        index = self.hash_code(self.encoder(key))
        for step in range(self.m):
            slot = (index + step) % self.m
            if self._keys[slot] is None:
                self._keys[slot] = key
                self._values[slot] = value
                self.size += 1
                return
        raise OverflowError("hash table is full during rehash")

    def keys(self):
        result = []
        for stored in self._keys:
            if stored is not None and stored is not TOMBSTONE:
                result.append(stored)
        return result

    def values(self):
        result = []
        for i in range(self.m):
            stored = self._keys[i]
            if stored is not None and stored is not TOMBSTONE:
                result.append(self._values[i])
        return result

    def slot_state(self, slot):
        stored = self._keys[slot]
        if stored is None:
            return "EMPTY"
        if stored is TOMBSTONE:
            return "TOMBSTONE"
        return stored

    def average_insert_probes(self):
        return self.insert_probes / self.insert_count if self.insert_count else 0.0

    def average_lookup_probes(self):
        return self.lookup_probes / self.lookup_count if self.lookup_count else 0.0

    def max_cluster(self):
        longest = 0
        run = 0
        for i in range(2 * self.m):
            if self._keys[i % self.m] is None:
                run = 0
            else:
                run += 1
                if run > longest:
                    longest = run
        return min(longest, self.m)

    def stats_lines(self):
        return [
            f"universal hash  : h(k) = ((a*k + b) mod p) mod m",
            f"p               : {self.p} (2^61 - 1, prime)",
            f"a, b            : {self.a}, {self.b}",
            f"m (capacity)    : {self.m}",
            f"size / tombs    : {self.size} / {self.tombstones}",
            f"load factor     : {self.load_factor:.3f} (with tombstones {self.occupied_factor:.3f}, max {self.max_load})",
            f"resizes         : {self.resizes}",
            f"inserts         : {self.insert_count}, avg probes {self.average_insert_probes():.3f}",
            f"collisions      : {self.home_collisions} inserts hit an occupied home slot, {self.probe_collisions} extra probes",
            f"lookups         : {self.lookup_count}, avg probes {self.average_lookup_probes():.3f}",
            f"longest cluster : {self.max_cluster()}",
        ]
