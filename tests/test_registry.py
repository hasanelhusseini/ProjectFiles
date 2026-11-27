import os
import unittest

from helpers import row, temp_csv

from airport_chaos.engine import AirportSystem, CommandError
from airport_chaos.hashtable import PRIME_P, DuplicateKeyError, UniversalHashTable, encode_id


class CsvParsingTests(unittest.TestCase):
    def tearDown(self):
        for path in getattr(self, "paths", []):
            os.remove(path)

    def load(self, rows, header=None):
        path = temp_csv(rows) if header is None else temp_csv(rows, header)
        self.paths = getattr(self, "paths", []) + [path]
        system = AirportSystem()
        return system, system.load(path)

    def test_valid_rows_are_parsed(self):
        system, report = self.load([
            row("B610505", "R1", "2026-11-27 09:00", "2026-11-27 09:05", "1"),
            row("B610506", "R1", "2026-11-27 09:05", "2026-11-27 09:10", "3"),
            row("aa1", "R2", "2026-11-27 09:00", "2026-11-27 09:07", "2"),
        ])
        self.assertEqual(report.loaded, 3)
        self.assertEqual(report.errors, [])
        flight = system.find("B610505")
        self.assertEqual((flight.runway, flight.priority, flight.duration), ("R1", 1, 5))
        self.assertEqual(system.find("aa1").duration, 7)
        self.assertIsNone(system.find("AA1"))

    def test_duplicate_ids_are_rejected(self):
        system, report = self.load([
            row("B610505", "R1", "2026-11-27 09:00", "2026-11-27 09:05"),
            row("B610505", "R2", "2026-11-27 10:00", "2026-11-27 10:05"),
        ])
        self.assertEqual(report.loaded, 1)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("duplicate", report.errors[0])
        self.assertEqual(system.find("B610505").runway, "R1")
        self.assertEqual(system.validate(), [])

    def test_malformed_timestamps_are_rejected(self):
        system, report = self.load([
            row("A1", "R1", "2026-11-27 9:00", "2026-11-27 09:05"),
            row("A2", "R1", "2026/11/27 09:00", "2026-11-27 09:05"),
            row("A3", "R1", "2026-02-30 09:00", "2026-02-30 09:05"),
            row("A4", "R1", "2026-11-27 24:00", "2026-11-27 09:05"),
            row("A5", "R1", "2026-11-27 09:10", "2026-11-27 09:05"),
            row("A6", "R1", "2026-11-27 09:10", "2026-11-27 09:10"),
            row("A7", "R1", "2026-11-27T09:10", "2026-11-27 09:15"),
            row("OK1", "R1", "2026-11-27 09:10", "2026-11-27 09:15"),
        ])
        self.assertEqual(report.loaded, 1)
        self.assertEqual(len(report.errors), 7)
        self.assertIsNotNone(system.find("OK1"))

    def test_other_invalid_fields(self):
        _, report = self.load([
            row("A1", "R1", "2026-11-27 09:00", "2026-11-27 09:05", "4"),
            row("A2", "X1", "2026-11-27 09:00", "2026-11-27 09:05"),
            row("A-3", "R1", "2026-11-27 09:00", "2026-11-27 09:05"),
            row("A4", "R1", "2026-11-27 09:00", "2026-11-27 09:05", status="LOST"),
        ])
        self.assertEqual(report.loaded, 0)
        self.assertEqual(len(report.errors), 4)

    def test_missing_column_and_missing_file(self):
        path = temp_csv([("A1", "AA")], header=("flight_id", "airline"))
        self.paths = [path]
        with self.assertRaises(CommandError):
            AirportSystem().load(path)
        with self.assertRaises(CommandError):
            AirportSystem().load("does_not_exist.csv")


class HashTableTests(unittest.TestCase):
    def test_parameters_are_valid(self):
        table = UniversalHashTable(seed=1)
        self.assertEqual(table.p, PRIME_P)
        self.assertTrue(1 <= table.a < table.p)
        self.assertTrue(0 <= table.b < table.p)
        self.assertTrue(0 <= encode_id("B610505") < table.p)
        self.assertEqual(encode_id("AB"), ord("A") * 257 + ord("B"))

    def test_forced_collisions_compare_full_strings(self):
        table = UniversalHashTable(capacity=8, seed=3, encoder=lambda s: 42, auto_resize=False)
        for key in ("X1", "X2", "X3", "X4"):
            table.insert(key, key.lower())
        self.assertEqual(table.home_collisions, 3)
        self.assertEqual(table.probe_collisions, 1 + 2 + 3)
        self.assertEqual(table.get("X3"), "x3")
        self.assertEqual(table.last_probes, 3)
        self.assertIsNone(table.get("X9"))
        self.assertEqual(table.last_probes, 5)
        with self.assertRaises(DuplicateKeyError):
            table.insert("X2", "again")

    def test_tombstones_keep_probe_chains(self):
        table = UniversalHashTable(capacity=8, seed=3, encoder=lambda s: 7, auto_resize=False)
        for key in ("A", "B", "C"):
            table.insert(key, key)
        self.assertEqual(table.delete("B"), "B")
        self.assertEqual(table.tombstones, 1)
        self.assertEqual(table.get("C"), "C")
        self.assertIsNone(table.get("B"))
        self.assertIsNone(table.delete("B"))
        table.insert("D", "D")
        self.assertEqual(table.tombstones, 0)
        self.assertEqual(table.get("D"), "D")
        self.assertEqual(sorted(table.keys()), ["A", "C", "D"])

    def test_resize_keeps_every_key(self):
        table = UniversalHashTable(capacity=4, max_load=0.5, seed=9)
        keys = [f"K{i}" for i in range(500)]
        for k in keys:
            table.insert(k, k)
        for k in keys[::3]:
            table.delete(k)
        self.assertGreater(table.resizes, 5)
        self.assertLessEqual(table.occupied_factor, 0.5)
        for i, k in enumerate(keys):
            self.assertEqual(table.get(k), None if i % 3 == 0 else k)
        self.assertEqual(len(table), 500 - len(keys[::3]))


if __name__ == "__main__":
    unittest.main()
