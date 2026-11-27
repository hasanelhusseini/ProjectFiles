import os
import random
import unittest

from helpers import row, synthetic_csv, temp_csv

from airport_chaos.bst import RunwayBST
from airport_chaos.engine import AirportSystem, CommandError
from airport_chaos.flight import Flight
from airport_chaos.timeutil import parse_ts


def make(fid, start, end=None):
    return Flight(fid, "AA", "JFK", "BOS", "R1", start, start + 5 if end is None else end, 1)


class BSTTests(unittest.TestCase):
    def build(self, starts):
        tree = RunwayBST("R1")
        for s in starts:
            tree.insert(make(f"F{s}", s))
        return tree

    def keys(self, tree):
        return [n.start for n in tree.inorder()]

    def test_root_deletion_two_children(self):
        tree = self.build([50, 20, 80, 10, 30, 70, 90, 75])
        self.assertIsNotNone(tree.delete(50, "F50"))
        self.assertEqual(tree.root.start, 70)
        self.assertEqual(self.keys(tree), [10, 20, 30, 70, 75, 80, 90])
        self.assertEqual(tree.check_invariants(), [])

    def test_root_deletion_one_child_and_leaf(self):
        tree = self.build([50, 80, 90])
        tree.delete(50, "F50")
        self.assertEqual(tree.root.start, 80)
        self.assertIsNone(tree.root.parent)
        tree.delete(80, "F80")
        tree.delete(90, "F90")
        self.assertIsNone(tree.root)
        self.assertEqual(len(tree), 0)

    def test_two_child_deletion_when_successor_is_direct_child(self):
        tree = self.build([50, 20, 60, 70])
        tree.delete(50, "F50")
        self.assertEqual(tree.root.start, 60)
        self.assertEqual(self.keys(tree), [20, 60, 70])
        self.assertEqual(tree.check_invariants(), [])

    def test_predecessor_and_successor(self):
        tree = self.build([50, 20, 80, 10, 30, 70, 90, 25, 35])
        node = tree.search(30, "F30")
        self.assertEqual(RunwayBST.predecessor(node).start, 25)
        self.assertEqual(RunwayBST.successor(node).start, 35)
        self.assertEqual(RunwayBST.successor(tree.search(35, "F35")).start, 50)
        self.assertEqual(RunwayBST.predecessor(tree.search(70, "F70")).start, 50)
        self.assertIsNone(RunwayBST.predecessor(tree.search(10, "F10")))
        self.assertIsNone(RunwayBST.successor(tree.search(90, "F90")))

    def test_range_search(self):
        tree = self.build([50, 20, 80, 10, 30, 70, 90])
        self.assertEqual([n.start for n in tree.range_search(20, 71)], [20, 30, 50, 70])
        self.assertEqual(tree.range_search(91, 200), [])

    def test_same_start_different_ids_ordered_by_id(self):
        tree = RunwayBST("R9")
        tree.insert(make("B", 10, 15))
        tree.insert(make("A", 10, 15))
        self.assertEqual([n.flight_id for n in tree.inorder()], ["A", "B"])

    def test_random_delete_matches_reference(self):
        rng = random.Random(4)
        starts = rng.sample(range(0, 5000, 5), 300)
        tree = self.build(starts)
        alive = sorted(starts)
        for s in rng.sample(starts, 200):
            tree.delete(s, f"F{s}")
            alive.remove(s)
            self.assertEqual(self.keys(tree), alive)
        self.assertEqual(tree.check_invariants(), [])


class ConflictTests(unittest.TestCase):
    def setUp(self):
        self.path = temp_csv([
            row("A1", "R1", "2026-11-27 09:15", "2026-11-27 09:20"),
            row("A2", "R1", "2026-11-27 09:30", "2026-11-27 09:40"),
            row("B1", "R2", "2026-11-27 09:20", "2026-11-27 09:25"),
        ])
        self.system = AirportSystem()
        self.system.load(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_exact_boundary_is_not_a_conflict(self):
        self.assertEqual(self.system.conflicts("R1", parse_ts("2026-11-27 09:20"), parse_ts("2026-11-27 09:30")), [])
        self.assertEqual(self.system.conflicts("R1", parse_ts("2026-11-27 09:10"), parse_ts("2026-11-27 09:15")), [])
        report = self.system.add("N1", "AA", "JFK", "BOS", "R1", "2026-11-27 09:20", "2026-11-27 09:30", "1")
        self.assertTrue(report.inserted)
        hits = self.system.conflicts("R1", parse_ts("2026-11-27 09:19"), parse_ts("2026-11-27 09:31"))
        self.assertEqual([n.flight_id for n in hits], ["A1", "N1", "A2"])

    def test_cross_runway_independence(self):
        report = self.system.add("N2", "AA", "JFK", "BOS", "R2", "2026-11-27 09:15", "2026-11-27 09:20", "1")
        self.assertTrue(report.inserted)
        report = self.system.add("N3", "AA", "JFK", "BOS", "R3", "2026-11-27 09:15", "2026-11-27 09:20", "1")
        self.assertTrue(report.inserted)
        self.assertEqual(self.system.validate(), [])

    def test_conflicting_insert_is_rejected_without_changes(self):
        before = self.system.snapshot()
        report = self.system.add("N4", "AA", "JFK", "BOS", "R1", "2026-11-27 09:18", "2026-11-27 09:22", "1")
        self.assertFalse(report.inserted)
        self.assertIn("A1", " ".join(report.lines))
        self.assertIsNone(self.system.find("N4"))
        self.assertEqual(self.system.snapshot(), before)
        check = self.system.check_conflict("R1", "2026-11-27 09:32", "2026-11-27 09:37")
        self.assertEqual(check.conflicts, ["A2"])
        self.assertEqual(check.suggestion, parse_ts("2026-11-27 09:42"))

    def test_load_rejects_overlapping_rows(self):
        path = temp_csv([
            row("A1", "R1", "2026-11-27 09:15", "2026-11-27 09:20"),
            row("A2", "R1", "2026-11-27 09:19", "2026-11-27 09:24"),
        ])
        report = AirportSystem().load(path)
        os.remove(path)
        self.assertEqual(report.loaded, 1)
        self.assertIn("overlaps", report.errors[0])

    def test_reschedule_and_cancel_keep_sync(self):
        self.assertTrue(self.system.reschedule("A1", "2026-11-27 10:00").moved)
        self.assertEqual(self.system.find("A1").status, "DELAYED")
        self.assertFalse(self.system.reschedule("A1", "2026-11-27 09:35").moved)
        self.assertEqual(self.system.find("A1").start, parse_ts("2026-11-27 10:00"))
        self.system.cancel("A2")
        self.assertEqual(self.system.find("A2").status, "CANCELLED")
        self.assertEqual(self.system.validate(), [])
        with self.assertRaises(CommandError):
            self.system.reschedule("A2", "2026-11-27 11:00")


class ConsistencyTests(unittest.TestCase):
    def test_registry_and_bsts_stay_consistent_after_random_updates(self):
        system = AirportSystem()
        system.load(synthetic_csv(400, 4, 11))
        rng = random.Random(12)
        ids = [f.flight_id for f in system.flights]
        for step in range(300):
            action = rng.randrange(4)
            fid = rng.choice(ids)
            hour = rng.randrange(0, 23)
            minute = rng.randrange(0, 12) * 5
            stamp = f"2026-11-27 {hour:02d}:{minute:02d}"
            try:
                if action == 0:
                    system.cancel(fid)
                elif action == 1:
                    system.reschedule(fid, stamp, f"R{rng.randrange(1, 5)}")
                elif action == 2:
                    new_id = f"Z{step}"
                    end = f"2026-11-27 {hour:02d}:{minute + 5:02d}" if minute < 55 else f"2026-11-27 {hour + 1:02d}:00"
                    if system.add(new_id, "ZZ", "AAA", "BBB", "R2", stamp, end, "2").inserted:
                        ids.append(new_id)
                else:
                    system.runway_closure(f"R{rng.randrange(1, 5)}", stamp, f"2026-11-27 {hour + 1:02d}:{minute:02d}")
            except CommandError:
                pass
            self.assertEqual(system.validate(), [], f"step {step}")


if __name__ == "__main__":
    unittest.main()
