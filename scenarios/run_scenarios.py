import argparse
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from airport_chaos.cli import CommandRunner, run_batch

SCENARIOS = (
    ("A", "scenario_a_runway_closure.txt"),
    ("B", "scenario_b_emergency_insert.txt"),
    ("C", "scenario_c_mass_cancel.txt"),
)


def run_one(path, csv_path, out_path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().replace("airport_flights.csv", csv_path)
    temp = out_path + ".cmd"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(lines)
    buffer = io.StringIO()

    def write(text):
        buffer.write(text + "\n")

    status = run_batch(temp, CommandRunner(out=write))
    os.remove(temp)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(buffer.getvalue())
    return status, buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Run the three official scenarios, each from a fresh LOAD")
    parser.add_argument("--csv", default=os.path.join(ROOT, "airport_flights.csv"))
    parser.add_argument("--out", default=os.path.join(ROOT, "scenarios", "output"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if not os.path.exists(args.csv):
        print(f"ERROR: {args.csv} not found")
        return 1
    os.makedirs(args.out, exist_ok=True)
    overall = 0
    for name, filename in SCENARIOS:
        out_path = os.path.join(args.out, f"scenario_{name.lower()}.txt")
        status, text = run_one(os.path.join(ROOT, "scenarios", filename), args.csv, out_path)
        overall |= status
        if not args.quiet:
            print(text)
        print(f"scenario {name}: {'OK' if status == 0 else 'ERRORS'} -> {out_path}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
