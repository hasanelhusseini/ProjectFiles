import csv
import random

from .timeutil import fmt_ts, parse_ts

AIRLINES = ("AA", "DL", "UA", "B6", "WN", "AS", "NK", "F9")
AIRPORTS = ("ATL", "BOS", "DEN", "DFW", "JFK", "LAX", "MIA", "ORD", "SEA", "SFO")
HEADER = ("flight_id", "airline", "origin", "destination", "runway",
          "start_time", "end_time", "priority", "status")


def generate_rows(flights=1000, runways=5, date="2026-11-27", seed=2026, duration=5, slot=5, order="time"):
    rng = random.Random(seed)
    day0 = parse_ts(f"{date} 00:00")
    per_runway = [flights // runways + (1 if r < flights % runways else 0) for r in range(runways)]
    slots_per_day = (24 * 60) // slot
    used_ids = set()
    rows = []
    for r in range(runways):
        count = per_runway[r]
        days = 1
        while days * slots_per_day < count:
            days += 1
        chosen = sorted(rng.sample(range(days * slots_per_day), count))
        for s in chosen:
            start = day0 + s * slot
            airline = rng.choice(AIRLINES)
            while True:
                fid = f"{airline}{rng.randrange(10000, 99999)}"
                if fid not in used_ids:
                    used_ids.add(fid)
                    break
            origin = rng.choice(AIRPORTS)
            destination = rng.choice(AIRPORTS)
            while destination == origin:
                destination = rng.choice(AIRPORTS)
            rows.append((fid, airline, origin, destination, f"R{r + 1}", fmt_ts(start),
                         fmt_ts(start + duration), str(rng.choice((1, 2, 2, 3, 3, 3))), "SCHEDULED"))
    if order == "time":
        rows.sort(key=lambda row: (row[5], row[4]))
    elif order == "shuffled":
        rng.shuffle(rows)
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow(row)
