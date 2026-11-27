import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from airport_chaos.datagen import HEADER, generate_rows, write_csv
from airport_chaos.engine import AirportSystem
from airport_chaos.timeutil import parse_ts

OFFICIAL_CSV = os.path.join(ROOT, "airport_flights.csv")

_cache = {}


def temp_csv(rows, header=HEADER):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
    with handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(row) + "\n")
    return handle.name


def synthetic_csv(flights=1000, runways=5, seed=2026, order="time"):
    key = (flights, runways, seed, order)
    if key not in _cache:
        path = os.path.join(tempfile.gettempdir(), f"cp3_synthetic_{flights}_{runways}_{seed}_{order}.csv")
        write_csv(path, generate_rows(flights, runways, "2026-11-27", seed, order=order))
        _cache[key] = path
    return _cache[key]


def datasets():
    paths = [synthetic_csv(), synthetic_csv(600, 3, 99, "shuffled"), synthetic_csv(1500, 6, 5)]
    if os.path.exists(OFFICIAL_CSV):
        paths.insert(0, OFFICIAL_CSV)
    return paths


def fresh(path):
    system = AirportSystem()
    report = system.load(path)
    assert report.loaded > 0
    return system


def row(fid, runway, start, end, priority="2", status="SCHEDULED", airline="AA", origin="JFK", destination="BOS"):
    return (fid, airline, origin, destination, runway, start, end, priority, status)


def reference_closure(system, runway, start_text, end_text):
    s = parse_ts(start_text)
    e = parse_ts(end_text)
    flights = [f for f in system.flights if f.is_active and f.runway == runway]
    affected = [f for f in flights if f.start < e and f.end > s]
    occupied = [(f.start, f.end) for f in flights if not (f.start < e and f.end > s)]
    affected = sorted(affected, key=lambda f: (f.priority, f.original_start, f.flight_id))
    outcome = {}
    for f in affected:
        duration = f.end - f.start
        t = e
        placed = None
        while t <= f.original_start + 120:
            if all(not (t < oe and os_ < t + duration) for os_, oe in occupied):
                placed = t
                break
            t += 5
        if placed is None:
            outcome[f.flight_id] = ("CANCELLED", None)
        else:
            occupied.append((placed, placed + duration))
            outcome[f.flight_id] = ("DELAYED", placed)
    return outcome
