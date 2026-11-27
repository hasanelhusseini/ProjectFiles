import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from airport_chaos.datagen import generate_rows, write_csv


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic flight CSV with the official schema")
    parser.add_argument("--flights", type=int, default=1000)
    parser.add_argument("--runways", type=int, default=5)
    parser.add_argument("--date", default="2026-11-27")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--order", choices=("time", "shuffled", "runway"), default="time")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = generate_rows(args.flights, args.runways, args.date, args.seed, args.duration, order=args.order)
    write_csv(args.out, rows)
    print(f"wrote {len(rows)} flights on {args.runways} runways to {args.out}")


if __name__ == "__main__":
    main()
