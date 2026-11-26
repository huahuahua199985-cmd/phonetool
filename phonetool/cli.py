import argparse
import multiprocessing as mp
import sys

from . import engine


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--countries", default="IN,ID,TH")
    ap.add_argument("--pack", type=int, default=100000)
    ap.add_argument("--fmt", default="txt", choices=["txt", "xlsx"])
    ap.add_argument("--no-cc", action="store_true", help="同时输出不带国家码")
    ap.add_argument("--only-no-cc", action="store_true")
    ap.add_argument("--workers", type=int, default=0)
    a = ap.parse_args(argv)
    last = [-1]

    def prog(f, m):
        if int(f * 100) != last[0]:
            last[0] = int(f * 100)
            print(f"[{f:5.0%}] {m}", file=sys.stderr, flush=True)

    rep = engine.run({"input_dir": a.input, "output_dir": a.output, "countries": a.countries.split(","),
                      "pack_size": a.pack, "fmt": a.fmt, "with_cc": not a.only_no_cc,
                      "without_cc": a.no_cc or a.only_no_cc, "workers": a.workers}, prog)
    print(rep["_text"])


if __name__ == "__main__":
    mp.freeze_support()
    main()
