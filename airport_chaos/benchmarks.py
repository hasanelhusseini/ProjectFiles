import os
import platform
import random
import sys
import time

from .bst import RunwayBST
from .flight import Flight
from .hashtable import UniversalHashTable
from .matrix import classical_multiply, matrices_equal, random_matrix, strassen_multiply
from .sorting import counting_sort, merge_sort, radix_sort_int, radix_sort_strings

QUICK = {
    "repeats": 3,
    "hash_capacity": 4096,
    "load_factors": (0.1, 0.25, 0.5, 0.7, 0.8, 0.9, 0.95),
    "bst_sizes": (250, 500, 1000, 2000),
    "sort_sizes": (1000, 5000, 20000),
    "matrix_sizes": (8, 16, 32, 64),
}
FULL = {
    "repeats": 5,
    "hash_capacity": 16384,
    "load_factors": (0.1, 0.25, 0.5, 0.7, 0.8, 0.9, 0.95),
    "bst_sizes": (500, 1000, 2000, 4000),
    "sort_sizes": (1000, 10000, 50000, 100000),
    "matrix_sizes": (8, 16, 32, 64, 128),
}


def environment_lines():
    return [
        f"python   : {sys.version.split()[0]} ({platform.python_implementation()})",
        f"platform : {platform.platform()}",
        f"machine  : {platform.machine()}, cpus={os.cpu_count()}",
        f"time     : {time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]


def _timed(fn, repeats):
    best = None
    total = 0.0
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - started
        total += elapsed
        if best is None or elapsed < best:
            best = elapsed
    return best, total / repeats, result


def _random_ids(count, rng):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    seen = set()
    ids = []
    while len(ids) < count:
        fid = rng.choice(letters) + rng.choice(letters + "0123456789") + str(rng.randrange(10000, 99999))
        if fid not in seen:
            seen.add(fid)
            ids.append(fid)
    return ids


def bench_hash(config, log):
    rng = random.Random(1)
    m = config["hash_capacity"]
    rows = []
    log(f"hash table, capacity m={m}, linear probing, repeats={config['repeats']}")
    log(f"{'alpha':>6} {'n':>6} {'avg ins':>8} {'hit probes':>11} {'miss probes':>12} {'theory hit':>11} {'theory miss':>12} {'us/lookup':>10}")
    for alpha in config["load_factors"]:
        n = int(alpha * m)
        ids = _random_ids(2 * n, rng)
        present, absent = ids[:n], ids[n:]
        table = UniversalHashTable(capacity=m, seed=7, auto_resize=False)
        for fid in present:
            table.insert(fid, fid)

        def run_hits():
            total = 0
            for fid in present:
                table.get(fid)
                total += table.last_probes
            return total

        def run_misses():
            total = 0
            for fid in absent:
                table.get(fid)
                total += table.last_probes
            return total

        best, mean, hit_probes = _timed(run_hits, config["repeats"])
        _, _, miss_probes = _timed(run_misses, 1)
        hit_avg = hit_probes / n if n else 0
        miss_avg = miss_probes / n if n else 0
        theory_hit = 0.5 * (1 + 1 / (1 - alpha))
        theory_miss = 0.5 * (1 + 1 / (1 - alpha) ** 2)
        per_lookup = best / n * 1e6 if n else 0
        rows.append((alpha, n, table.average_insert_probes(), hit_avg, miss_avg, theory_hit, theory_miss, per_lookup))
        log(f"{alpha:>6.2f} {n:>6} {table.average_insert_probes():>8.3f} {hit_avg:>11.3f} {miss_avg:>12.3f} {theory_hit:>11.3f} {theory_miss:>12.3f} {per_lookup:>10.3f}")
    return ("alpha", "n", "avg_insert_probes", "avg_hit_probes", "avg_miss_probes", "theory_hit", "theory_miss", "us_per_lookup"), rows


def _make_flights(n, sorted_keys, rng):
    starts = list(range(0, n * 10, 10))
    if not sorted_keys:
        rng.shuffle(starts)
    return [Flight(f"F{i:06d}", "XX", "AAA", "BBB", "R1", s, s + 5, 1) for i, s in enumerate(starts)]


def bench_bst(config, log):
    rng = random.Random(2)
    rows = []
    log(f"unbalanced BST, sorted vs shuffled insertion order, repeats={config['repeats']}")
    log(f"{'order':>9} {'n':>6} {'height':>7} {'insert ms':>10} {'search ms':>10} {'us/search':>10}")
    for n in config["bst_sizes"]:
        for label, sorted_keys in (("sorted", True), ("shuffled", False)):
            flights = _make_flights(n, sorted_keys, rng)

            def build():
                tree = RunwayBST("B")
                for f in flights:
                    tree.insert(f)
                return tree

            best_insert, _, tree = _timed(build, config["repeats"])
            queries = list(flights)
            rng.shuffle(queries)

            def search_all():
                for f in queries:
                    tree.search(f.start, f.flight_id)

            best_search, _, _ = _timed(search_all, config["repeats"])
            height = tree.height()
            rows.append((label, n, height, best_insert * 1000, best_search * 1000, best_search / n * 1e6))
            log(f"{label:>9} {n:>6} {height:>7} {best_insert * 1000:>10.2f} {best_search * 1000:>10.2f} {best_search / n * 1e6:>10.3f}")
    return ("order", "n", "height", "insert_ms", "search_ms", "us_per_search"), rows


def bench_sort(config, log):
    rng = random.Random(3)
    rows = []
    log(f"non-comparison sorts vs merge sort baseline (own implementation), repeats={config['repeats']}")
    log(f"{'n':>7} {'count P':>9} {'merge P':>9} {'radix int':>10} {'merge int':>10} {'radix str':>10} {'merge str':>10}  (ms)")
    for n in config["sort_sizes"]:
        priorities = [rng.randint(1, 3) for _ in range(n)]
        ints = [rng.randrange(0, 1 << 40) for _ in range(n)]
        ids = _random_ids(n, rng)
        r = config["repeats"]
        t_count, _, out1 = _timed(lambda: counting_sort(priorities, low=1, high=3), r)
        t_merge_p, _, out2 = _timed(lambda: merge_sort(priorities), r)
        t_radix, _, out3 = _timed(lambda: radix_sort_int(ints), r)
        t_merge_i, _, out4 = _timed(lambda: merge_sort(ints), r)
        t_radix_s, _, out5 = _timed(lambda: radix_sort_strings(ids), r)
        t_merge_s, _, out6 = _timed(lambda: merge_sort(ids), r)
        if out1 != out2 or out3 != out4 or out5 != out6:
            raise AssertionError("sort outputs disagree")
        values = (t_count, t_merge_p, t_radix, t_merge_i, t_radix_s, t_merge_s)
        rows.append((n,) + tuple(v * 1000 for v in values))
        log(f"{n:>7} " + " ".join(f"{v * 1000:>9.2f} " for v in values))
    return ("n", "counting_priority_ms", "merge_priority_ms", "radix_int_ms", "merge_int_ms", "radix_string_ms", "merge_string_ms"), rows


def bench_matrix(config, log):
    rng = random.Random(4)
    rows = []
    cutoffs = (1, 16, 32)
    log(f"classical vs Strassen (zero padded), cutoffs {cutoffs}, repeats={config['repeats']}")
    log(f"{'n':>5} {'classical':>10} " + " ".join(f"{'cut ' + str(c):>10}" for c in cutoffs) + "  (ms)  equal")
    for n in config["matrix_sizes"]:
        a = random_matrix(n, n, rng)
        b = random_matrix(n, n, rng)
        r = config["repeats"] if n <= 64 else max(1, config["repeats"] // 2)
        t_classic, _, expected = _timed(lambda: classical_multiply(a, b), r)
        times = []
        ok = True
        for c in cutoffs:
            reps = 1 if (c == 1 and n >= 64) else r
            t, _, got = _timed(lambda: strassen_multiply(a, b, cutoff=c), reps)
            times.append(t)
            ok = ok and matrices_equal(expected, got)
        rows.append((n, t_classic * 1000) + tuple(t * 1000 for t in times) + (ok,))
        log(f"{n:>5} {t_classic * 1000:>10.2f} " + " ".join(f"{t * 1000:>10.2f}" for t in times) + f"        {ok}")
    return ("n", "classical_ms") + tuple(f"strassen_cutoff_{c}_ms" for c in cutoffs) + ("equal",), rows


SUITES = (("HASH", bench_hash), ("BST", bench_bst), ("SORT", bench_sort), ("MATRIX", bench_matrix))


def run(which="ALL", quick=True, log=print, out_dir=None):
    config = QUICK if quick else FULL
    which = which.upper()
    names = [name for name, _ in SUITES]
    if which != "ALL" and which not in names:
        raise ValueError(f"unknown benchmark '{which}' (choose {', '.join(names)} or ALL)")
    for line in environment_lines():
        log(line)
    results = []
    for name, fn in SUITES:
        if which in ("ALL", name):
            log("")
            log(f"--- {name} ---")
            header, rows = fn(config, log)
            results.append((name, header, rows))
            if out_dir is not None:
                write_csv(os.path.join(out_dir, f"{name.lower()}.csv"), header, rows)
    if out_dir is not None:
        with open(os.path.join(out_dir, "environment.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(environment_lines()) + "\n")
            handle.write(f"mode     : {'quick' if quick else 'full'}\n")
    return results


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in row) + "\n")
