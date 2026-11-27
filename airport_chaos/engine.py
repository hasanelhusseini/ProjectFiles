import csv
import re
import time

from .bst import RunwayBST
from .dnc import max_subarray_brute, max_subarray_dc
from .flight import CANCELLED, DELAYED, SCHEDULED, VALID_STATUSES, Flight
from .hashtable import UniversalHashTable, encode_id
from .matrix import DEFAULT_CUTOFF, classical_multiply, matrices_equal, strassen_multiply, zeros
from .perfect_hash import RULE_IDS, PerfectHashTable
from .sorting import (binary_search, counting_sort, counting_sort_priority, radix_sort_int, radix_sort_strings,
                      sort_flights_by_id_exact, sort_flights_by_numeric_id, sort_for_recovery,
                      unique_sorted_strings)
from .timeutil import SLOT_MINUTES, TimeFormatError, day_start, fmt_hm, fmt_ts, parse_ts
from .tracing import tracer

REQUIRED_COLUMNS = ("flight_id", "airline", "origin", "destination", "runway",
                    "start_time", "end_time", "priority", "status")
MAX_DELAY_MINUTES = 120
ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
CODE_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
RUNWAY_PATTERN = re.compile(r"^R[0-9]+$")


class CommandError(Exception):
    pass


class Report:
    def __init__(self, title):
        self.title = title
        self.lines = []
        self.ok = True

    def add(self, line=""):
        self.lines.append(line)

    def extend(self, lines):
        for line in lines:
            self.lines.append(line)

    def fail(self, line):
        self.ok = False
        self.lines.append("ERROR: " + line)

    def text(self):
        header = f"=== {self.title} ==="
        return "\n".join([header] + self.lines)


def validate_flight_fields(flight_id, airline, origin, destination, runway, start_text, end_text, priority_text, status_text=SCHEDULED):
    flight_id = flight_id.strip()
    airline = airline.strip()
    origin = origin.strip()
    destination = destination.strip()
    runway = runway.strip()
    status = status_text.strip().upper() if status_text is not None else SCHEDULED
    if not ID_PATTERN.match(flight_id):
        raise ValueError(f"invalid flight_id '{flight_id}' (must be alphanumeric)")
    for label, value in (("airline", airline), ("origin", origin), ("destination", destination)):
        if not CODE_PATTERN.match(value):
            raise ValueError(f"invalid {label} '{value}'")
    if not RUNWAY_PATTERN.match(runway):
        raise ValueError(f"invalid runway '{runway}' (expected R1, R2, ...)")
    try:
        start = parse_ts(start_text)
        end = parse_ts(end_text)
    except TimeFormatError as exc:
        raise ValueError(str(exc))
    if start >= end:
        raise ValueError(f"start_time {start_text.strip()} must be before end_time {end_text.strip()}")
    p = priority_text.strip() if isinstance(priority_text, str) else str(priority_text)
    if p not in ("1", "2", "3"):
        raise ValueError(f"invalid priority '{p}' (must be 1, 2 or 3)")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status '{status_text}'")
    return Flight(flight_id, airline, origin, destination, runway, start, end, int(p), status)


class AirportSystem:
    def __init__(self, seed=310):
        self.seed = seed
        self.reset()

    def reset(self):
        self.registry = UniversalHashTable(seed=self.seed)
        self.runways = []
        self.flights = []
        self.source = None
        self.last_crisis = None

    def require_loaded(self):
        if self.source is None and not self.flights:
            raise CommandError("no data loaded; run LOAD <file> first")

    def get_runway(self, name, create=False):
        for bst in self.runways:
            if bst.name == name:
                return bst
        if not create:
            return None
        bst = RunwayBST(name)
        index = len(self.runways)
        while index > 0 and self._runway_before(name, self.runways[index - 1].name):
            index -= 1
        self.runways.insert(index, bst)
        return bst

    @staticmethod
    def _runway_before(a, b):
        if len(a) != len(b):
            return len(a) < len(b)
        return a < b

    def find(self, flight_id):
        return self.registry.get(flight_id)

    def load(self, path):
        try:
            handle = open(path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"cannot open '{path}': {exc.strerror}")
        with handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise CommandError(f"'{path}' is empty")
            header = [h.strip().lower() for h in header]
            positions = []
            for column in REQUIRED_COLUMNS:
                found = -1
                for i in range(len(header)):
                    if header[i] == column:
                        found = i
                        break
                if found < 0:
                    raise CommandError(f"missing required column '{column}'")
                positions.append(found)
            self.reset()
            self.source = path
            report = Report(f"LOAD {path}")
            errors = []
            loaded = 0
            with tracer.suspend():
                for row in reader:
                    line = reader.line_num
                    if not row or all(cell.strip() == "" for cell in row):
                        continue
                    if len(row) < len(header):
                        errors.append(f"line {line}: expected {len(header)} fields, found {len(row)}")
                        continue
                    values = [row[i] for i in positions]
                    try:
                        flight = validate_flight_fields(*values)
                    except ValueError as exc:
                        errors.append(f"line {line}: {exc}")
                        continue
                    if self.registry.get(flight.flight_id) is not None:
                        errors.append(f"line {line}: duplicate flight_id '{flight.flight_id}' rejected")
                        continue
                    if flight.is_active:
                        bst = self.get_runway(flight.runway, create=True)
                        clashes = bst.find_conflicts(flight.start, flight.end)
                        if clashes:
                            names = ", ".join(n.flight_id for n in clashes)
                            errors.append(f"line {line}: {flight.flight_id} overlaps {names} on {flight.runway}; rejected")
                            continue
                    self._register(flight)
                    loaded += 1
        report.add(f"loaded {loaded} flights on {len(self.runways)} runways, rejected {len(errors)} rows")
        for msg in errors[:25]:
            report.add("  " + msg)
        if len(errors) > 25:
            report.add(f"  ... {len(errors) - 25} more errors")
        report.loaded = loaded
        report.errors = errors
        return report

    def _register(self, flight):
        self.registry.insert(flight.flight_id, flight)
        self.flights.append(flight)
        if flight.is_active:
            self.get_runway(flight.runway, create=True).insert(flight)

    def conflicts(self, runway, start, end, ignore_id=None):
        bst = self.get_runway(runway)
        if bst is None:
            return []
        found = bst.find_conflicts(start, end)
        if ignore_id is None:
            return found
        return [n for n in found if n.flight_id != ignore_id]

    @staticmethod
    def next_free_slot(bst, start, duration, latest=None):
        t = start
        while latest is None or t <= latest:
            if bst is None or bst.is_free(t, t + duration):
                return t
            t += SLOT_MINUTES
        return None

    @staticmethod
    def _conflict_text(nodes):
        return ", ".join(f"{n.flight_id} [{fmt_hm(n.start)}-{fmt_hm(n.end)})" for n in nodes)

    def check_conflict(self, runway, start_text, end_text):
        self.require_loaded()
        start, end = self._interval(start_text, end_text)
        if not RUNWAY_PATTERN.match(runway):
            raise CommandError(f"invalid runway '{runway}'")
        report = Report(f"CHECK_CONFLICT {runway} [{fmt_ts(start)}, {fmt_ts(end)})")
        found = self.conflicts(runway, start, end)
        report.conflicts = [n.flight_id for n in found]
        if found:
            report.add(f"CONFLICT with {len(found)} flight(s): {self._conflict_text(found)}")
            slot = self.next_free_slot(self.get_runway(runway), start + SLOT_MINUTES, end - start)
            report.add(f"earliest later conflict-free slot: [{fmt_ts(slot)}, {fmt_hm(slot + end - start)})")
            report.suggestion = slot
        else:
            report.add("no conflict: interval is free")
            report.suggestion = start
        return report

    @staticmethod
    def _interval(start_text, end_text):
        try:
            start = parse_ts(start_text)
            end = parse_ts(end_text)
        except TimeFormatError as exc:
            raise CommandError(str(exc))
        if start >= end:
            raise CommandError("start time must be before end time")
        return start, end

    def add(self, flight_id, airline, origin, destination, runway, start_text, end_text, priority_text):
        self.require_loaded()
        try:
            flight = validate_flight_fields(flight_id, airline, origin, destination, runway, start_text, end_text, priority_text)
        except ValueError as exc:
            raise CommandError(str(exc))
        report = Report(f"ADD {flight.flight_id}")
        if self.registry.get(flight.flight_id) is not None:
            report.fail(f"flight_id '{flight.flight_id}' already exists")
            report.inserted = False
            return report
        found = self.conflicts(flight.runway, flight.start, flight.end)
        if found:
            report.fail(f"conflicts with {self._conflict_text(found)}; nothing inserted")
            slot = self.next_free_slot(self.get_runway(flight.runway), flight.start + SLOT_MINUTES, flight.duration)
            report.add(f"earliest later conflict-free slot on {flight.runway}: {fmt_ts(slot)}")
            report.inserted = False
            return report
        self._register(flight)
        report.add("inserted: " + flight.describe())
        report.inserted = True
        return report

    def cancel(self, flight_id):
        self.require_loaded()
        flight = self.registry.get(flight_id)
        report = Report(f"CANCEL {flight_id}")
        if flight is None:
            report.fail(f"flight '{flight_id}' not found")
            return report
        if flight.status == CANCELLED:
            report.fail(f"flight '{flight_id}' is already CANCELLED")
            return report
        self._deactivate(flight)
        report.add("cancelled: " + flight.describe())
        return report

    def _deactivate(self, flight):
        bst = self.get_runway(flight.runway)
        removed = bst.delete(flight.start, flight.flight_id) if bst is not None else None
        if removed is not flight:
            raise RuntimeError(f"registry/BST mismatch for {flight.flight_id}")
        flight.status = CANCELLED

    def reschedule(self, flight_id, new_start_text, runway=None):
        self.require_loaded()
        flight = self.registry.get(flight_id)
        if flight is None:
            raise CommandError(f"flight '{flight_id}' not found")
        if flight.status == CANCELLED:
            raise CommandError(f"flight '{flight_id}' is CANCELLED and cannot be rescheduled")
        try:
            new_start = parse_ts(new_start_text)
        except TimeFormatError as exc:
            raise CommandError(str(exc))
        target = runway if runway is not None else flight.runway
        if not RUNWAY_PATTERN.match(target):
            raise CommandError(f"invalid runway '{target}'")
        duration = flight.duration
        report = Report(f"RESCHEDULE {flight_id}")
        old_text = f"{flight.runway} {fmt_ts(flight.start)}-{fmt_hm(flight.end)}"
        source_bst = self.get_runway(flight.runway)
        source_bst.delete(flight.start, flight.flight_id)
        target_bst = self.get_runway(target, create=True)
        found = target_bst.find_conflicts(new_start, new_start + duration)
        if found:
            source_bst.insert(flight)
            report.fail(f"new slot conflicts with {self._conflict_text(found)}; flight unchanged")
            slot = self.next_free_slot(target_bst, new_start + SLOT_MINUTES, duration)
            report.add(f"earliest later conflict-free slot on {target}: {fmt_ts(slot)}")
            report.moved = False
            return report
        flight.start = new_start
        flight.end = new_start + duration
        flight.runway = target
        flight.status = DELAYED if flight.start > flight.original_start else SCHEDULED
        target_bst.insert(flight)
        report.add(f"moved {flight_id}: {old_text} -> {target} {fmt_ts(flight.start)}-{fmt_hm(flight.end)} ({flight.status})")
        report.moved = True
        return report

    def runway_closure(self, runway, start_text, end_text):
        self.require_loaded()
        start, end = self._interval(start_text, end_text)
        bst = self.get_runway(runway)
        if bst is None:
            raise CommandError(f"unknown runway '{runway}'")
        report = Report(f"RUNWAY_CLOSURE {runway} [{fmt_ts(start)}, {fmt_ts(end)})")
        affected = [node.flight for node in bst.find_conflicts(start, end)]
        old_slots = []
        for flight in affected:
            old_slots.append((flight.flight_id, flight.start, flight.end))
            bst.delete(flight.start, flight.flight_id)
        ordered = sort_for_recovery(affected)
        report.add(f"affected flights on {runway}: {len(affected)}")
        report.add(f"recovery order (priority, original start, flight_id): {' '.join(f.flight_id for f in ordered) if ordered else '-'}")
        report.add("")
        report.add(f"{'flight':<10} {'P':>1}  {'old slot':<17} {'new slot':<17} {'status':<10} {'delay':>5}  blocked at {fmt_hm(end)} by")
        delayed = cancelled = total_delay = 0
        rows = []
        for flight in ordered:
            old_start = flight.start
            old_end = flight.end
            duration = flight.duration
            first_block = bst.find_conflicts(end, end + duration)
            latest = flight.original_start + MAX_DELAY_MINUTES
            slot = self.next_free_slot(bst, end, duration, latest) if end <= latest else None
            if slot is not None:
                flight.start = slot
                flight.end = slot + duration
                flight.status = DELAYED
                bst.insert(flight)
                delay = flight.start - flight.original_start
                delayed += 1
                total_delay += delay
                new_text = f"{fmt_hm(flight.start)}-{fmt_hm(flight.end)}"
                tracer.log(f"{flight.flight_id}: placed at {fmt_ts(slot)} after {(slot - end) // SLOT_MINUTES + 1} tries")
            else:
                flight.status = CANCELLED
                delay = 0
                cancelled += 1
                new_text = "-"
                tracer.log(f"{flight.flight_id}: no slot by {fmt_ts(latest)}; cancelled")
            blockers = ", ".join(n.flight_id for n in first_block) if first_block else "-"
            report.add(f"{flight.flight_id:<10} {flight.priority:>1}  {fmt_hm(old_start)}-{fmt_hm(old_end):<11} {new_text:<17} {flight.status:<10} {delay:>5}  {blockers}")
            rows.append((flight.flight_id, old_start, old_end, flight.start if slot is not None else None,
                         flight.end if slot is not None else None, flight.status, delay))
        report.add("")
        report.add(f"TOTALS: affected={len(affected)} delayed={delayed} cancelled={cancelled} total_delay_minutes={total_delay}")
        report.add(f"unaffected flights moved: 0; other runways unchanged")
        problems = self.validate()
        report.add("consistency check: " + ("OK" if not problems else "; ".join(problems[:5])))
        report.rows = rows
        report.totals = (len(affected), delayed, cancelled, total_delay)
        self.last_crisis = report
        return report

    def emergency_insert(self, flight_id="EM90001", airline="EM", origin="JFK", destination="BOS", runway="R1",
                         start_text="2026-11-27 09:00", end_text="2026-11-27 09:05", priority_text="1",
                         accept=None, confirm=None):
        self.require_loaded()
        try:
            flight = validate_flight_fields(flight_id, airline, origin, destination, runway, start_text, end_text, priority_text)
        except ValueError as exc:
            raise CommandError(str(exc))
        report = Report(f"EMERGENCY_INSERT {flight.flight_id} {flight.runway} [{fmt_ts(flight.start)}, {fmt_hm(flight.end)})")
        report.inserted = False
        report.conflicts = []
        report.suggestion = None
        if self.registry.get(flight.flight_id) is not None:
            report.fail(f"flight_id '{flight.flight_id}' already exists")
            return report
        bst = self.get_runway(flight.runway, create=True)
        found = bst.find_conflicts(flight.start, flight.end)
        report.conflicts = [n.flight_id for n in found]
        if not found:
            report.add("requested slot is conflict-free")
            self._register(flight)
            report.inserted = True
            report.add("inserted: " + flight.describe())
        else:
            report.add(f"requested slot CONFLICTS with: {self._conflict_text(found)}")
            slot = self.next_free_slot(bst, flight.start + SLOT_MINUTES, flight.duration)
            report.suggestion = slot
            report.add(f"earliest feasible later slot: [{fmt_ts(slot)}, {fmt_hm(slot + flight.duration)}) "
                       f"(+{slot - flight.start} min); existing flights are not moved")
            decision = accept
            if decision is None and confirm is not None:
                decision = confirm(f"insert {flight.flight_id} at {fmt_ts(slot)}?")
            if decision:
                duration = flight.duration
                if not bst.is_free(slot, slot + duration):
                    report.fail("suggested slot is no longer free; nothing inserted")
                    return report
                placed = Flight(flight.flight_id, flight.airline, flight.origin, flight.destination,
                                flight.runway, slot, slot + duration, flight.priority, SCHEDULED)
                self._register(placed)
                report.inserted = True
                report.add("inserted at suggested slot: " + placed.describe())
            else:
                report.add("not inserted (use ACCEPT to insert at the suggested slot)")
        problems = self.validate()
        report.add("consistency check: " + ("OK" if not problems else "; ".join(problems[:5])))
        self.last_crisis = report
        return report

    def mass_cancel(self, start_text, end_text):
        self.require_loaded()
        start, end = self._interval(start_text, end_text)
        report = Report(f"MASS_CANCEL start in [{fmt_ts(start)}, {fmt_ts(end)})")
        report.add(f"{'flight':<10} {'runway':<6} {'slot':<12} {'old status':<10} -> new status")
        cancelled = []
        per_runway = []
        for bst in self.runways:
            nodes = bst.range_search(start, end)
            targets = [n.flight for n in nodes]
            for flight in targets:
                previous = flight.status
                self._deactivate(flight)
                cancelled.append(flight.flight_id)
                report.add(f"{flight.flight_id:<10} {flight.runway:<6} {fmt_hm(flight.start)}-{fmt_hm(flight.end):<6} {previous:<10} -> {CANCELLED}")
            per_runway.append(f"{bst.name}={len(targets)}")
        report.add("")
        report.add(f"TOTALS: affected={len(cancelled)} delayed=0 cancelled={len(cancelled)} total_delay_minutes=0")
        report.add("per runway: " + " ".join(per_runway))
        report.add("cancelled records remain in the registry; removed from active BSTs")
        problems = self.validate()
        report.add("consistency check: " + ("OK" if not problems else "; ".join(problems[:5])))
        report.cancelled = cancelled
        self.last_crisis = report
        return report

    def list_runway(self, runway, start_text=None, end_text=None):
        self.require_loaded()
        bst = self.get_runway(runway)
        if bst is None:
            raise CommandError(f"unknown runway '{runway}'")
        if start_text is not None:
            start, end = self._interval(start_text, end_text)
            nodes = bst.range_search(start, end)
            title = f"LIST_RUNWAY {runway} start in [{fmt_ts(start)}, {fmt_ts(end)})"
        else:
            nodes = bst.inorder()
            title = f"LIST_RUNWAY {runway}"
        report = Report(title)
        for node in nodes:
            report.add(node.flight.describe())
        report.add(f"{len(nodes)} active flight(s); BST size {len(bst)}, height {bst.height()}")
        report.nodes = nodes
        return report

    def find_report(self, flight_id):
        self.require_loaded()
        flight, probes = self.registry.lookup(flight_id)
        report = Report(f"FIND {flight_id}")
        if flight is None:
            report.fail(f"flight '{flight_id}' not found ({probes} probes)")
            return report
        report.extend(flight.describe_full())
        report.add(f"hash lookup    : home slot {self.registry.home_slot(flight_id)}, {probes} probe(s)")
        if flight.is_active:
            bst = self.get_runway(flight.runway)
            node = bst.search(flight.start, flight.flight_id)
            prev = RunwayBST.predecessor(node)
            nxt = RunwayBST.successor(node)
            report.add(f"previous on {flight.runway}: {prev.flight.describe() if prev else 'none'}")
            report.add(f"next on {flight.runway}    : {nxt.flight.describe() if nxt else 'none'}")
        return report

    def sort_priority(self, limit=20):
        self.require_loaded()
        report = Report("SORT_PRIORITY (stable counting sort, keys 1..3)")
        indexed = [(i, self.flights[i]) for i in range(len(self.flights))]
        started = time.perf_counter()
        pairs = counting_sort(indexed, key=lambda t: t[1].priority, low=1, high=3, label="counting sort priority")
        elapsed = time.perf_counter() - started
        stable = True
        counts = [0, 0, 0]
        for i in range(len(pairs)):
            counts[pairs[i][1].priority - 1] += 1
            if i > 0 and pairs[i - 1][1].priority == pairs[i][1].priority and pairs[i - 1][0] > pairs[i][0]:
                stable = False
        report.add(f"sorted {len(pairs)} flights in {elapsed * 1000:.2f} ms; P1={counts[0]} P2={counts[1]} P3={counts[2]}")
        report.add(f"stability check (equal priorities keep load order): {'PASS' if stable else 'FAIL'}")
        for index, f in pairs[:limit]:
            report.add(f"  #{index:<5} {f.describe()}")
        if len(pairs) > limit:
            report.add(f"  ... {len(pairs) - limit} more")
        report.ordered = [f for _, f in pairs]
        report.stable = stable
        return report

    def sort_id(self, mode="EXACT", limit=20):
        self.require_loaded()
        mode = mode.upper()
        started = time.perf_counter()
        if mode == "EXACT":
            ordered = sort_flights_by_id_exact(self.flights)
            title = "SORT_ID EXACT (character-based LSD radix sort, true lexicographic order)"
        elif mode == "NUMERIC":
            ordered = sort_flights_by_numeric_id(self.flights, encode_id)
            title = "SORT_ID NUMERIC (LSD radix base 256 on encoded key; ties broken by exact id)"
        else:
            raise CommandError("SORT_ID mode must be EXACT or NUMERIC")
        elapsed = time.perf_counter() - started
        report = Report(title)
        ok = True
        for i in range(1, len(ordered)):
            a, b = ordered[i - 1], ordered[i]
            if mode == "EXACT" and a.flight_id > b.flight_id:
                ok = False
            if mode == "NUMERIC":
                ka, kb = encode_id(a.flight_id), encode_id(b.flight_id)
                if ka > kb or (ka == kb and a.flight_id > b.flight_id):
                    ok = False
        report.add(f"sorted {len(ordered)} flights in {elapsed * 1000:.2f} ms; order check {'PASS' if ok else 'FAIL'}")
        for f in ordered[:limit]:
            extra = f"  key={encode_id(f.flight_id)}" if mode == "NUMERIC" else ""
            report.add(f"  {f.describe()}{extra}")
        if len(ordered) > limit:
            report.add(f"  ... {len(ordered) - limit} more")
        report.ordered = ordered
        return report

    def stability_demo(self):
        report = Report("STABILITY DEMO")
        sample = [Flight(fid, "XX", "AAA", "BBB", "R1", i * 5, i * 5 + 5, p)
                  for i, (fid, p) in enumerate((("C30", 2), ("A10", 1), ("D40", 2), ("B20", 1), ("E50", 3), ("F60", 1)))]
        report.add("input            : " + "  ".join(f"{f.flight_id}(P{f.priority})" for f in sample))
        by_priority = counting_sort_priority(sample)
        report.add("counting sort    : " + "  ".join(f"{f.flight_id}(P{f.priority})" for f in by_priority))
        report.add("P1 keeps A10, B20, F60 and P2 keeps C30, D40 in input order -> stable")
        nums = [("x", 21), ("y", 5), ("z", 21), ("w", 5), ("v", 300)]
        radix = radix_sort_int(nums, key=lambda t: t[1])
        report.add("radix input      : " + "  ".join(f"{n}={k}" for n, k in nums))
        report.add("radix sort       : " + "  ".join(f"{n}={k}" for n, k in radix))
        report.add("equal keys 5 (y before w) and 21 (x before z) keep input order -> stable")
        report.add("")
        report.add("Comparison sorts form a decision tree with at least n! leaves, so height >= log2(n!) = Omega(n log n).")
        report.add("Counting/radix sort index arrays by key digits instead of comparing pairs, so they run in O(n + k) and")
        report.add("O(d(n + b)) and are not bound by the comparison lower bound.")
        return report

    def disruption_loads(self):
        if not self.flights:
            return [], 0
        first = self.flights[0].original_start
        last = first
        for f in self.flights:
            if f.original_start < first:
                first = f.original_start
            if f.original_start > last:
                last = f.original_start
        origin = day_start(first)
        stop = day_start(last) + 24 * 60
        loads = [0] * ((stop - origin) // SLOT_MINUTES)
        for f in self.flights:
            if f.status == DELAYED or f.status == CANCELLED:
                loads[(f.original_start - origin) // SLOT_MINUTES] += 1
        return loads, origin

    def analyze_disruption(self):
        self.require_loaded()
        report = Report("ANALYZE DISRUPTION (divide-and-conquer maximum subarray)")
        loads, origin = self.disruption_loads()
        started = time.perf_counter()
        best = max_subarray_dc(loads)
        dc_time = time.perf_counter() - started
        started = time.perf_counter()
        check = max_subarray_brute(loads)
        brute_time = time.perf_counter() - started
        nonzero = 0
        for v in loads:
            if v:
                nonzero += 1
        report.add(f"buckets: {len(loads)} x {SLOT_MINUTES} min from {fmt_ts(origin)}; non-zero buckets: {nonzero}; total load {sum(loads)}")
        total, lo, hi = best
        if total == 0:
            report.add("no DELAYED/CANCELLED flights: all loads are zero")
            report.add(f"canonical answer: sum 0 at bucket range [{lo}, {hi}] ({fmt_ts(origin + lo * SLOT_MINUTES)} - {fmt_ts(origin + (hi + 1) * SLOT_MINUTES)})")
        else:
            report.add(f"maximum range: buckets [{lo}, {hi}] = [{fmt_ts(origin + lo * SLOT_MINUTES)}, {fmt_ts(origin + (hi + 1) * SLOT_MINUTES)})")
            report.add(f"total disruption load: {total} flights")
            window = loads[lo:hi + 1]
            if len(window) <= 48:
                report.add("loads in range: " + " ".join(str(v) for v in window))
        report.add(f"O(n^2) reference: {check} -> {'MATCH' if check == best else 'MISMATCH'}")
        report.add(f"time: divide-and-conquer {dc_time * 1000:.3f} ms, brute force {brute_time * 1000:.3f} ms")
        report.add("recurrence T(n) = 2T(n/2) + O(n) -> O(n log n); ties: shortest range, then earliest start")
        report.best = best
        report.loads = loads
        return report

    def route_matrix(self):
        codes = []
        for f in self.flights:
            codes.append(f.origin)
            codes.append(f.destination)
        airports = unique_sorted_strings(codes)
        n = len(airports)
        a = zeros(n, n)
        for f in self.flights:
            a[binary_search(airports, f.origin)][binary_search(airports, f.destination)] += 1
        return airports, a

    def analyze_routes(self, cutoff=DEFAULT_CUTOFF, top=10):
        self.require_loaded()
        airports, a = self.route_matrix()
        n = len(airports)
        report = Report(f"ANALYZE ROUTES (origin-destination flight counts, N={n})")
        report.add("airports: " + " ".join(airports))
        if n <= 20:
            report.add("A (rows = origin, columns = destination):")
            report.add("      " + " ".join(f"{c:>4}" for c in airports))
            for i in range(n):
                report.add(f"{airports[i]:>5} " + " ".join(f"{v:>4}" for v in a[i]))
        started = time.perf_counter()
        classic = classical_multiply(a, a)
        t_classic = time.perf_counter() - started
        stats = []
        started = time.perf_counter()
        fast = strassen_multiply(a, a, cutoff=cutoff, stats=stats)
        t_fast = time.perf_counter() - started
        started = time.perf_counter()
        fast_full = strassen_multiply(a, a, cutoff=1)
        t_full = time.perf_counter() - started
        same = matrices_equal(classic, fast) and matrices_equal(classic, fast_full)
        report.add(f"A x A classical O(N^3): {t_classic * 1000:.3f} ms")
        report.add(f"A x A Strassen (padded to {stats[0][0]}, cutoff {cutoff}, {stats[0][1]} base products): {t_fast * 1000:.3f} ms")
        report.add(f"A x A Strassen (cutoff 1, full recursion): {t_full * 1000:.3f} ms")
        report.add(f"classical == Strassen: {'YES' if same else 'NO'}")
        entries = []
        for i in range(n):
            for j in range(n):
                if classic[i][j]:
                    entries.append((classic[i][j], i, j))
        largest = 0
        for e in entries:
            if e[0] > largest:
                largest = e[0]
        entries = radix_sort_int(entries, key=lambda e: largest - e[0])
        report.add(f"top {min(top, len(entries))} two-leg route counts (A^2[i][j] = sum_k A[i][k]*A[k][j]; a proxy, not passenger flow):")
        for value, i, j in entries[:top]:
            report.add(f"  {airports[i]} -> * -> {airports[j]} : {value}")
        report.airports = airports
        report.matrix = a
        report.square = classic
        report.same = same
        return report

    def perfect_hash_report(self, queries=None):
        table = PerfectHashTable(RULE_IDS, seed=self.seed)
        report = Report("PERFECT_HASH (two-level FKS)")
        report.extend(table.report_lines())
        if not queries:
            queries = [101, 173, 283, 100, 102, 284, 9999]
        for q in queries:
            present, i, j = table.lookup(q)
            where = f"bucket {i}" + (f", slot {j}" if j is not None else ", empty bucket") if i is not None else "out of key range"
            report.add(f"lookup {q}: {'PRESENT' if present else 'ABSENT'} ({where})")
        report.table = table
        return report

    def validate(self):
        problems = []
        active = 0
        for flight in self.registry.values():
            if flight.is_active:
                active += 1
                bst = self.get_runway(flight.runway)
                node = None
                if bst is not None:
                    with tracer.suspend():
                        node = bst.search(flight.start, flight.flight_id)
                if node is None or node.flight is not flight or node.end != flight.end:
                    problems.append(f"{flight.flight_id} active in registry but missing in BST {flight.runway}")
        in_trees = 0
        for bst in self.runways:
            problems.extend(bst.check_invariants())
            for node in bst.inorder():
                in_trees += 1
                stored = self.registry.get(node.flight_id)
                if stored is not node.flight or not stored.is_active or stored.runway != bst.name:
                    problems.append(f"BST {bst.name} node {node.flight_id} not consistent with registry")
        if in_trees != active:
            problems.append(f"{active} active flights in registry but {in_trees} nodes in BSTs")
        if len(self.registry) != len(self.flights):
            problems.append(f"registry size {len(self.registry)} but {len(self.flights)} flights")
        return problems

    def stats(self):
        report = Report("STATS")
        if self.source is None:
            report.add("no data loaded")
            return report
        counts = [0, 0, 0]
        for f in self.flights:
            counts[VALID_STATUSES.index(f.status)] += 1
        report.add(f"source          : {self.source}")
        report.add(f"flights         : {len(self.flights)} total | SCHEDULED {counts[0]} | DELAYED {counts[1]} | CANCELLED {counts[2]}")
        total_delay = 0
        for f in self.flights:
            if f.status == DELAYED:
                total_delay += f.delay_minutes
        report.add(f"total delay     : {total_delay} min")
        for bst in self.runways:
            first = bst.first()
            last = bst.last()
            span = f"{fmt_ts(first.start)} .. {fmt_ts(last.end)}" if first else "-"
            report.add(f"runway {bst.name:<8} : {len(bst):>4} active, BST height {bst.height():>4}, {span}")
        report.add("registry hash table:")
        report.extend("  " + line for line in self.registry.stats_lines())
        problems = self.validate()
        report.add("registry/BST consistency: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
        report.counts = counts
        return report

    def snapshot(self):
        ordered = sort_flights_by_id_exact(self.flights)
        return [(f.flight_id, f.runway, f.start, f.end, f.status) for f in ordered]
