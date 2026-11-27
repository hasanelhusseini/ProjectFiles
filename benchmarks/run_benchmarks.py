import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from airport_chaos import benchmarks


def plot(results, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plots")
        return
    for name, header, rows in results:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        if name == "HASH":
            alphas = [r[0] for r in rows]
            ax.plot(alphas, [r[3] for r in rows], "o-", label="measured hit probes")
            ax.plot(alphas, [r[4] for r in rows], "s-", label="measured miss probes")
            ax.plot(alphas, [r[5] for r in rows], "--", label="theory hit 1/2(1+1/(1-a))")
            ax.plot(alphas, [r[6] for r in rows], ":", label="theory miss 1/2(1+1/(1-a)^2)")
            ax.set_xlabel("load factor")
            ax.set_ylabel("average probes")
            ax.set_yscale("log")
        elif name == "BST":
            for label in ("sorted", "shuffled"):
                sub = [r for r in rows if r[0] == label]
                ax.plot([r[1] for r in sub], [r[3] for r in sub], "o-", label=f"insert all ({label})")
                ax.plot([r[1] for r in sub], [r[4] for r in sub], "s--", label=f"search all ({label})")
            ax.set_xlabel("n")
            ax.set_ylabel("ms")
            ax.set_yscale("log")
        elif name == "SORT":
            ns = [r[0] for r in rows]
            for i in range(1, len(header)):
                ax.plot(ns, [r[i] for r in rows], "o-", label=header[i].replace("_ms", ""))
            ax.set_xlabel("n")
            ax.set_ylabel("ms")
            ax.set_xscale("log")
            ax.set_yscale("log")
        elif name == "MATRIX":
            ns = [r[0] for r in rows]
            for i in range(1, len(header) - 1):
                ax.plot(ns, [r[i] for r in rows], "o-", label=header[i].replace("_ms", ""))
            ax.set_xlabel("N")
            ax.set_ylabel("ms")
            ax.set_xscale("log", base=2)
            ax.set_yscale("log")
        ax.set_title(f"{name} benchmark")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = os.path.join(out_dir, f"{name.lower()}.png")
        fig.savefig(path, dpi=130)
        plt.close(fig)
        print(f"saved {path}")


def main():
    parser = argparse.ArgumentParser(description="Run CP3 benchmark suite")
    parser.add_argument("which", nargs="?", default="ALL", help="ALL, HASH, BST, SORT or MATRIX")
    parser.add_argument("--full", action="store_true", help="larger sizes and more repeats")
    parser.add_argument("--out", default=os.path.join(ROOT, "benchmarks", "results"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    results = benchmarks.run(args.which, quick=not args.full, out_dir=args.out)
    if not args.no_plots:
        plot(results, args.out)
    print(f"results written to {args.out}")


if __name__ == "__main__":
    main()
