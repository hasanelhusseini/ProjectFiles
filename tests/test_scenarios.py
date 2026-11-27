import os
import unittest

from helpers import datasets, fresh, reference_closure, row, temp_csv

from airport_chaos.engine import AirportSystem
from airport_chaos.timeutil import parse_ts

CLOSURE = ("R1", "2026-11-27 09:00", "2026-11-27 11:00")
EMERGENCY = ("EM90001", "EM", "JFK", "BOS", "R1", "2026-11-27 09:00", "2026-11-27 09:05", "1")
MASS = ("2026-11-27 14:00", "2026-11-27 15:00")


class ScenarioATests(unittest.TestCase):
    def test_matches_independent_reference(self):
        for path in datasets():
            system = fresh(path)
            expected = reference_closure(system, *CLOSURE)
            before = {f.flight_id: (f.runway, f.start, f.end, f.status) for f in system.flights}
            report = system.runway_closure(*CLOSURE)
            self.assertEqual(report.totals[0], len(expected), path)
            delay = 0
            for f in system.flights:
                if f.flight_id in expected:
                    status, start = expected[f.flight_id]
                    self.assertEqual(f.status, status, f.flight_id)
                    if start is not None:
                        self.assertEqual(f.start, start)
                        self.assertEqual(f.end - f.start, before[f.flight_id][2] - before[f.flight_id][1])
                        self.assertLessEqual(f.start - f.original_start, 120)
                        self.assertGreaterEqual(f.start, parse_ts(CLOSURE[2]))
                        delay += f.start - f.original_start
                else:
                    self.assertEqual((f.runway, f.start, f.end, f.status), before[f.flight_id])
            self.assertEqual(report.totals[3], delay)
            self.assertEqual(report.totals[1] + report.totals[2], report.totals[0])
            self.assertEqual(system.validate(), [])

    def test_priority_order_and_cancellation_rule(self):
        path = temp_csv([
            row("C3", "R1", "2026-11-27 09:00", "2026-11-27 09:05", "3"),
            row("B1", "R1", "2026-11-27 10:00", "2026-11-27 10:05", "1"),
            row("A1", "R2", "2026-11-27 10:00", "2026-11-27 10:05", "1"),
            row("X1", "R1", "2026-11-27 11:00", "2026-11-27 11:05", "2"),
            row("A2", "R1", "2026-11-27 10:30", "2026-11-27 10:40", "1"),
        ])
        system = AirportSystem()
        system.load(path)
        os.remove(path)
        report = system.runway_closure(*CLOSURE)
        self.assertEqual(report.totals[0], 3)
        self.assertEqual(system.find("B1").start, parse_ts("2026-11-27 11:05"))
        self.assertEqual(system.find("A2").start, parse_ts("2026-11-27 11:10"))
        self.assertEqual(system.find("A2").duration, 10)
        self.assertEqual(system.find("C3").status, "CANCELLED")
        self.assertEqual(system.find("X1").start, parse_ts("2026-11-27 11:00"))
        self.assertEqual(system.find("A1").status, "SCHEDULED")
        self.assertEqual(report.totals, (3, 2, 1, 65 + 40))


class ScenarioBTests(unittest.TestCase):
    def test_conflict_reported_and_later_slot_offered(self):
        for path in datasets():
            system = fresh(path)
            start = parse_ts(EMERGENCY[5])
            blockers = [n.flight_id for n in system.conflicts("R1", start, start + 5)]
            before = system.snapshot()
            report = system.emergency_insert(*EMERGENCY, accept=False)
            self.assertEqual(report.conflicts, blockers)
            if blockers:
                self.assertEqual(system.snapshot(), before)
                self.assertFalse(report.inserted)
                slot = report.suggestion
                self.assertGreater(slot, start)
                self.assertEqual((slot - start) % 5, 0)
                self.assertEqual(system.conflicts("R1", slot, slot + 5), [])
                for t in range(start + 5, slot, 5):
                    self.assertNotEqual(system.conflicts("R1", t, t + 5), [])
                report = system.emergency_insert(*EMERGENCY, accept=True)
                self.assertTrue(report.inserted)
                self.assertEqual(system.find("EM90001").start, slot)
            else:
                self.assertTrue(report.inserted)
            self.assertEqual(system.find("EM90001").priority, 1)
            self.assertEqual(len(system.flights), len(before) + 1)
            self.assertEqual(system.validate(), [])

    def test_free_slot_is_inserted_directly(self):
        path = temp_csv([row("A1", "R1", "2026-11-27 09:05", "2026-11-27 09:10")])
        system = AirportSystem()
        system.load(path)
        os.remove(path)
        report = system.emergency_insert(*EMERGENCY)
        self.assertTrue(report.inserted)
        self.assertEqual(report.conflicts, [])
        self.assertEqual(system.find("EM90001").start, parse_ts("2026-11-27 09:00"))


class ScenarioCTests(unittest.TestCase):
    def test_cancels_starts_in_window_on_all_runways(self):
        for path in datasets():
            system = fresh(path)
            s, e = parse_ts(MASS[0]), parse_ts(MASS[1])
            expected = sorted(f.flight_id for f in system.flights if f.is_active and s <= f.start < e)
            before = {f.flight_id: (f.start, f.status) for f in system.flights}
            report = system.mass_cancel(*MASS)
            self.assertEqual(sorted(report.cancelled), expected)
            for f in system.flights:
                if f.flight_id in expected:
                    self.assertEqual(f.status, "CANCELLED")
                    self.assertIs(system.find(f.flight_id), f)
                else:
                    self.assertEqual((f.start, f.status), before[f.flight_id])
            self.assertEqual(len(system.registry), len(before))
            self.assertEqual(system.validate(), [])

    def test_flight_starting_before_window_is_kept(self):
        path = temp_csv([
            row("A1", "R1", "2026-11-27 13:58", "2026-11-27 14:03"),
            row("A2", "R2", "2026-11-27 14:00", "2026-11-27 14:05"),
            row("A3", "R3", "2026-11-27 14:55", "2026-11-27 15:00"),
            row("A4", "R3", "2026-11-27 15:00", "2026-11-27 15:05"),
        ])
        system = AirportSystem()
        system.load(path)
        os.remove(path)
        report = system.mass_cancel(*MASS)
        self.assertEqual(sorted(report.cancelled), ["A2", "A3"])


class FreshLoadRegressionTests(unittest.TestCase):
    def run_scenario(self, path, name):
        system = fresh(path)
        if name == "A":
            totals = system.runway_closure(*CLOSURE).totals
        elif name == "B":
            totals = system.emergency_insert(*EMERGENCY, accept=True).suggestion
        else:
            totals = len(system.mass_cancel(*MASS).cancelled)
        return totals, system.snapshot()

    def test_each_scenario_is_reproducible_from_fresh_load(self):
        for path in datasets():
            for name in ("A", "B", "C"):
                first = self.run_scenario(path, name)
                self.run_scenario(path, "C" if name != "C" else "A")
                second = self.run_scenario(path, name)
                self.assertEqual(first, second, f"{name} on {path}")

    def test_reload_resets_state(self):
        for path in datasets():
            system = fresh(path)
            original = system.snapshot()
            system.runway_closure(*CLOSURE)
            system.mass_cancel(*MASS)
            system.emergency_insert(*EMERGENCY, accept=True)
            system.load(path)
            self.assertEqual(system.snapshot(), original)
            self.assertIsNone(system.find("EM90001"))


if __name__ == "__main__":
    unittest.main()
