import io
import os
import random
import tempfile
import unittest

from helpers import synthetic_csv

from airport_chaos.cli import CommandRunner, run_batch, tokenize
from airport_chaos.dnc import max_subarray_brute, max_subarray_dc
from airport_chaos.engine import AirportSystem
from airport_chaos.flight import Flight
from airport_chaos.hashtable import encode_id
from airport_chaos.matrix import classical_multiply, matrices_equal, random_matrix, strassen_multiply
from airport_chaos.perfect_hash import RULE_IDS, PerfectHashTable
from airport_chaos.sorting import (counting_sort, counting_sort_priority, merge_sort, radix_sort_int,
                                   radix_sort_strings, sort_flights_by_numeric_id, sort_for_recovery)


def flight(fid, priority, start=0):
    return Flight(fid, "AA", "JFK", "BOS", "R1", start, start + 5, priority)


class SortingTests(unittest.TestCase):
    def test_counting_sort_is_stable(self):
        items = [flight(f"F{i}", p) for i, p in enumerate((2, 1, 3, 1, 2, 3, 1, 2))]
        ordered = counting_sort_priority(items)
        self.assertEqual([f.priority for f in ordered], [1, 1, 1, 2, 2, 2, 3, 3])
        self.assertEqual([f.flight_id for f in ordered], ["F1", "F3", "F6", "F0", "F4", "F7", "F2", "F5"])

    def test_radix_sort_int_is_stable_and_correct(self):
        rng = random.Random(5)
        pairs = [(rng.randrange(0, 50), i) for i in range(2000)] + [(rng.randrange(0, 1 << 50), -1) for _ in range(500)]
        self.assertEqual(radix_sort_int(pairs, key=lambda t: t[0]), sorted(pairs, key=lambda t: t[0]))
        self.assertEqual(radix_sort_int([0, 0, 3]), [0, 0, 3])
        with self.assertRaises(ValueError):
            radix_sort_int([3, -1])

    def test_string_radix_sort_matches_lexicographic_order(self):
        rng = random.Random(6)
        alphabet = "AB9az0Z"
        ids = ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 7))) for _ in range(3000)]
        self.assertEqual(radix_sort_strings(ids), sorted(ids))
        self.assertEqual(radix_sort_strings(["B6", "B", "AA1", "AA", "b"]), ["AA", "AA1", "B", "B6", "b"])

    def test_numeric_id_order_breaks_ties_by_exact_id(self):
        items = [flight(fid, 1) for fid in ("Z9", "A1", "M5", "B2")]
        ordered = sort_flights_by_numeric_id(items, encoder=lambda s: 1 if s in ("Z9", "B2") else 0)
        self.assertEqual([f.flight_id for f in ordered], ["A1", "M5", "B2", "Z9"])
        real = sort_flights_by_numeric_id(items, encode_id)
        keys = [encode_id(f.flight_id) for f in real]
        self.assertEqual(keys, sorted(keys))

    def test_recovery_order(self):
        items = [flight("C", 2, 10), flight("B", 1, 20), flight("A", 1, 20), flight("D", 1, 5), flight("E", 3, 0)]
        self.assertEqual([f.flight_id for f in sort_for_recovery(items)], ["D", "A", "B", "C", "E"])

    def test_merge_sort_baseline(self):
        rng = random.Random(8)
        values = [rng.randrange(100) for _ in range(777)]
        self.assertEqual(merge_sort(values), sorted(values))
        self.assertEqual(counting_sort(values), sorted(values))

    def test_engine_sort_commands(self):
        system = AirportSystem()
        system.load(synthetic_csv())
        self.assertTrue(system.sort_priority(0).stable)
        ids = [f.flight_id for f in system.sort_id("EXACT", 0).ordered]
        self.assertEqual(ids, sorted(ids))


class MaxSubarrayTests(unittest.TestCase):
    def test_matches_reference_on_random_arrays(self):
        rng = random.Random(9)
        for _ in range(500):
            values = [rng.choice((0, 0, 0, 1, 2, 3, -2, -5)) for _ in range(rng.randint(1, 40))]
            self.assertEqual(max_subarray_dc(values), max_subarray_brute(values))

    def test_all_zero_and_known_cases(self):
        self.assertEqual(max_subarray_dc([0] * 288), (0, 0, 0))
        self.assertEqual(max_subarray_brute([0] * 288), (0, 0, 0))
        self.assertEqual(max_subarray_dc([0, 0, 2, 3, 0, 0, 1, 0]), (6, 2, 6))
        self.assertEqual(max_subarray_dc([0, 4, 0, 0, 4, 0]), (8, 1, 4))
        self.assertEqual(max_subarray_dc([]), (0, -1, -1))

    def test_disruption_analysis_after_mass_cancel(self):
        system = AirportSystem()
        system.load(synthetic_csv())
        zero = system.analyze_disruption()
        self.assertEqual(zero.best[0], 0)
        cancelled = len(system.mass_cancel("2026-11-27 14:00", "2026-11-27 15:00").cancelled)
        report = system.analyze_disruption()
        self.assertEqual(report.best[0], cancelled)
        self.assertEqual(len(report.loads), 288)
        self.assertGreaterEqual(report.best[1], 168)
        self.assertLessEqual(report.best[2], 179)


class MatrixTests(unittest.TestCase):
    def test_strassen_matches_classical_on_odd_and_even_sizes(self):
        rng = random.Random(10)
        for n in (1, 2, 3, 4, 5, 6, 7, 9, 12, 15, 17, 33):
            a = random_matrix(n, n, rng, -5, 9)
            b = random_matrix(n, n, rng, -5, 9)
            expected = classical_multiply(a, b)
            for cutoff in (1, 2, 8):
                self.assertTrue(matrices_equal(strassen_multiply(a, b, cutoff=cutoff), expected), (n, cutoff))

    def test_rectangular_and_identity(self):
        a = [[1, 2, 3], [4, 5, 6]]
        b = [[7, 8], [9, 10], [11, 12]]
        self.assertEqual(strassen_multiply(a, b, cutoff=1), [[58, 64], [139, 154]])
        identity = [[1 if i == j else 0 for j in range(5)] for i in range(5)]
        m = random_matrix(5, 5, random.Random(1))
        self.assertEqual(strassen_multiply(m, identity, cutoff=1), m)

    def test_route_matrix(self):
        system = AirportSystem()
        system.load(synthetic_csv())
        report = system.analyze_routes(cutoff=2)
        self.assertTrue(report.same)
        self.assertEqual(report.airports, sorted(report.airports))
        self.assertEqual(sum(sum(r) for r in report.matrix), len(system.flights))


class PerfectHashTests(unittest.TestCase):
    def test_all_rule_ids_found_and_absent_ids_rejected(self):
        table = PerfectHashTable(RULE_IDS)
        for k in RULE_IDS:
            self.assertTrue(table.contains(k))
        for k in (0, 1, 100, 102, 150, 284, 1000, 10006, 99999, -4):
            self.assertFalse(table.contains(k))
        self.assertLessEqual(table.second_level_slots, 4 * len(RULE_IDS))
        for bucket in table.buckets:
            self.assertEqual(len(bucket.slots), bucket.size * bucket.size)

    def test_other_seeds_are_collision_free(self):
        for seed in range(20):
            table = PerfectHashTable(RULE_IDS, seed=seed)
            self.assertTrue(all(table.contains(k) for k in RULE_IDS))


class CliTests(unittest.TestCase):
    def test_tokenizer_merges_unquoted_timestamps(self):
        self.assertEqual(tokenize('RUNWAY_CLOSURE R1 2026-11-27 09:00 "2026-11-27 11:00"'),
                         ["RUNWAY_CLOSURE", "R1", "2026-11-27 09:00", "2026-11-27 11:00"])

    def test_batch_runner(self):
        commands = "\n".join([
            f"LOAD {synthetic_csv()}",
            "STATS",
            'RUNWAY_CLOSURE R1 "2026-11-27 09:00" "2026-11-27 11:00"',
            "FIND NOT_THERE",
            "BOGUS",
            "VALIDATE",
        ])
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        with handle:
            handle.write(commands)
        buffer = io.StringIO()
        runner = CommandRunner(out=lambda text: buffer.write(text + "\n"))
        status = run_batch(handle.name, runner)
        os.remove(handle.name)
        output = buffer.getvalue()
        self.assertEqual(status, 1)
        self.assertIn("TOTALS: affected=", output)
        self.assertIn("unknown command", output)
        self.assertIn("registry and runway BSTs are consistent", output)
        self.assertIsNotNone(runner.system.find(runner.system.flights[0].flight_id))


if __name__ == "__main__":
    unittest.main()
