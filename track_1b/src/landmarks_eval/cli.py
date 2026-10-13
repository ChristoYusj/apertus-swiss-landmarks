"""Command-line entry point: `landmarks-eval <command>` (or `python -m landmarks_eval`).

Judge-facing commands (no network needed for `verify`):
  verify   re-check shipped responses/judgements against the dataset and expected scores (exit 1 on any mismatch)
  live     ask the model in LLM_NAME/LLM_BASE_URL/LLM_API_KEY a seeded sample, grade it, print scores
  run / grade / score   the individual stages
Team-only commands (network, build the dataset): build-landmarks, build-images, build-questions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]  # track_1b/ in a source checkout
DEFAULT_WORK = ROOT / "work"
EXPECTED = PKG / "expected" / "reference.scores.json"


def resolve_dataset(spec: str | None) -> Path:
    """Local directory, or 'hf:<repo_id>@<revision>' downloaded with huggingface_hub (anonymous)."""
    spec = spec or os.environ.get("LANDMARKS_DATASET") or _config().get("dataset")
    if not spec:
        raise SystemExit("no dataset given (use --dataset DIR or hf:<repo>@<revision>)")
    if spec.startswith("hf:"):
        from huggingface_hub import snapshot_download
        repo, _, rev = spec[3:].partition("@")
        return Path(snapshot_download(repo_id=repo, repo_type="dataset", revision=rev or None))
    p = Path(spec)
    return p if p.is_absolute() or p.exists() else (ROOT / p)


def _config() -> dict:
    for p in (Path.cwd() / "config.json", ROOT / "config.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="landmarks-eval")
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK, help="build working directory (team only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build-landmarks", help="(team only, network) pull Wikidata + BFS and sample landmarks")
    b.add_argument("--refresh", action="store_true", help="ignore the SPARQL cache and re-pull")
    sub.add_parser("build-images", help="(team only, network) fetch, licence-filter and re-encode photos")
    sub.add_parser("build-questions", help="(team only) generate test cases from the frozen templates")
    r = sub.add_parser("review-page", help="(team only) write the offline photo-screening page + photos")
    r.add_argument("--out", type=Path, default=None, help="output folder (default: <work>/review/photo_screening)")
    m = sub.add_parser("merge-review", help="(team only) merge the team's screening_team.json decision file")
    m.add_argument("files", nargs=1, type=Path)
    sub.add_parser("assemble", help="(team only) assemble the publishable dataset folder")

    st = sub.add_parser("stability", help="re-ask a seeded sample to measure temperature-0 answer stability")
    st.add_argument("--dataset")
    st.add_argument("--results", type=Path, required=True)
    st.add_argument("--n", type=int, default=100)
    st.add_argument("--probe", type=int, default=20)
    st.add_argument("--repeats", type=int, default=2)

    for name in ("run", "grade", "score", "verify", "live"):
        p = sub.add_parser(name)
        p.add_argument("--dataset", help="dataset dir or hf:<repo>@<revision> (default: config.json)")
        p.add_argument("--results", type=Path, help="results directory (responses.jsonl, judgements.jsonl)")
        if name in ("run", "live"):
            p.add_argument("--sample", type=int, default=None, help="seeded stratified sample size (default: all)")
        if name in ("score", "verify"):
            p.add_argument("--expected", type=Path, help="expected scores JSON to compare against")
        if name == "score":
            p.add_argument("--write", type=Path, help="where to write scores.json")
    args = ap.parse_args(argv)

    if args.cmd == "build-landmarks":
        from .build.sample import build_landmarks
        print(json.dumps(build_landmarks(args.work, refresh=args.refresh), indent=1, ensure_ascii=False))
        return 0
    if args.cmd == "build-images":
        from .build.images import build_images
        report = build_images(args.work)
        print(json.dumps({k: v for k, v in report.items() if k != "replaced"}, indent=1, ensure_ascii=False))
        print("replaced:", len(report["replaced"]))
        return 0

    if args.cmd == "build-questions":
        from .build.questions import build_questions
        merged = args.work / "review" / "merged.json"
        alt = low = dropped = None
        if merged.exists():
            mj = json.loads(merged.read_text(encoding="utf-8"))
            alt, low, dropped = mj["alt_accepted"], mj["lowinfo"], mj["report"]["dropped_landmarks"]
        print(json.dumps(build_questions(args.work, alt, low, dropped), indent=1, ensure_ascii=False))
        return 0
    if args.cmd == "review-page":
        from .build.review_page import build_review_page
        print(build_review_page(args.work, args.out))
        return 0
    if args.cmd == "merge-review":
        from .build.review_merge import merge_review
        print(json.dumps(merge_review(args.work, args.files), indent=1, ensure_ascii=False))
        return 0
    if args.cmd == "assemble":
        from .build.assemble import assemble
        print(json.dumps(assemble(args.work), indent=1, ensure_ascii=False))
        return 0

    from .client import Endpoint
    dataset = resolve_dataset(args.dataset)

    if args.cmd == "verify":
        from .verify import verify
        results = args.results or dataset / "responses" / _config().get("reference_model_dir", "apertus-v1.5-70b")
        expected = args.expected or EXPECTED
        return 0 if verify(dataset, results, expected if expected.exists() else None) else 1

    if args.cmd == "stability":
        ep = Endpoint.from_env("LLM")
        if ep is None:
            print("LLM_NAME, LLM_BASE_URL and LLM_API_KEY must be set.", file=sys.stderr)
            return 2
        from .stability import stability
        rep = stability(dataset, args.results, ep, n=args.n, probe=args.probe, repeats=args.repeats)
        print(json.dumps({k: v for k, v in rep.items() if k != "probe"} | {"probe": {k: v for k, v in rep["probe"].items()
                                                                               if k != "detail"}}, indent=1))
        return 0

    if args.cmd in ("run", "live"):
        ep = Endpoint.from_env("LLM")
        if ep is None:
            print("LLM_NAME, LLM_BASE_URL and LLM_API_KEY must be set for a live run.", file=sys.stderr)
            return 2
        from .run import run
        results = args.results or Path.cwd() / "results" / ("live-" + ep.model.replace("/", "_"))
        run(dataset, results, ep, sample=args.sample)
        if args.cmd == "run":
            return 0
        args.results = results

    if args.cmd in ("grade", "live"):
        from .score import grade_all
        judge = Endpoint.from_env("JUDGE")
        if judge is None:
            print("note: no JUDGE_MODEL/JUDGE_BASE_URL/JUDGE_API_KEY -> code grader only (documented, see README)")
        grade_all(dataset, args.results, judge)
        if args.cmd == "grade":
            return 0

    if args.cmd in ("score", "live"):
        from .score import compute_scores, write_scores
        scores = compute_scores(dataset, args.results)
        out = getattr(args, "write", None) or args.results / "scores.json"
        write_scores(scores, out)
        brief = {k: scores[k] for k in ("model", "coverage", "H1_name_hallucination_low_minus_high")}
        brief["overall_by_arm_qtype"] = {k: {m: v[m] for m in ("n", "pct_correct", "pct_not_attempted", "hallucination_rate")}
                                         for k, v in scores["overall_by_arm_qtype"].items()}
        print(json.dumps(brief, indent=1, ensure_ascii=False))
        print(f"full scores: {out}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
