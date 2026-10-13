"""Command-line entry point: `landmarks-eval <command>` (or `python -m landmarks_eval`)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_WORK = Path(__file__).resolve().parents[2] / "work"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="landmarks-eval")
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK, help="build working directory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-landmarks", help="(team only, network) pull Wikidata + BFS and sample landmarks")
    b.add_argument("--refresh", action="store_true", help="ignore the SPARQL cache and re-pull")
    args = ap.parse_args(argv)

    if args.cmd == "build-landmarks":
        from .build.sample import build_landmarks
        report = build_landmarks(args.work, refresh=args.refresh)
        print(json.dumps(report, indent=1, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
