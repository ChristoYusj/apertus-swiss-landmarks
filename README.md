# Swiss Heritage Factuality — Hack Apertus 2026, Track 1B (Red Pandas)

Does Apertus 1.5 recognise Switzerland's heritage landmarks? A four-language (FR/DE/IT/RM) benchmark of
photo, text-only and trap questions about 264 landmarks of the Swiss inventory of cultural property, with a
fully automated harness that grades, scores and **verifies its own outputs**.

| | |
|---|---|
| Project | [`track_1b/`](track_1b/) — code in `track_1b/src/landmarks_eval`, tests in `track_1b/tests` |
| Report | [`track_1b/technical_report.md`](track_1b/technical_report.md) (PDF: `track_1b/RedPandas_Report.pdf`) |
| Dataset | Hugging Face `chrizzto/swiss-heritage-factuality` (CDLA-Permissive-2.0, per-photo CC licences) |
| Changes and decisions | [`track_1b/CHANGELOG.md`](track_1b/CHANGELOG.md) (pre-registration, every post-run correction) |

**Run it** (Docker, clean checkout):

```bash
make run
```

- Without keys: downloads the pinned dataset, re-grades every stored answer and checks that the recomputed
  scores equal the published ones (exit code = verification result). No GPU, about a minute.
- With `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY` set (any OpenAI-compatible endpoint, e.g. the CSCS Apertus
  endpoint): also evaluates that model on a seeded, stratified sample (`SAMPLE=150`) or on everything (`FULL=1`).
- Optional independent judge: `JUDGE_MODEL`, `JUDGE_BASE_URL`, `JUDGE_API_KEY` (we used `openai/gpt-oss-120b:groq`
  via the Hugging Face router, `https://router.huggingface.co/v1`, prompt `judge-v1`); without it the deterministic code grader is used. See `track_1b/.env.example`.
- Requirements: Docker; runtime ~1 min (verify), under an hour for a full 70B run; API key only for live runs;
  no model weights are downloaded.

---

# Hack Apertus — project template

Template repository for [Hack Apertus](https://hackapertus.ch/) submissions.
Every project keeps almost the same layout, so organizers and judges find the
same things in the same place.

## Select your track

This repository holds one example project per track:

- `track_1a/`
- `track_1b/`
- `track_2a/`
- `track_2b/`

Keep the directory for the track you are competing in **exactly as it is** —
don't rename it or move its files — and delete the other track directories.
That directory is your project root. Keep the files and directories as shown
below.

## The structure

| Path | What it is |
| --- | --- |
| `README.md` | The challenge description and submission requirements for your track |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| `Makefile` | `make run` must spin up your project |
| `src/` | Your code |
| `data/` | Datasets — `track_1a`, `track_2a` and `track_2b` only; max. 100 MB |
| `findings/` | Issue files — `track_1a` only |
| `docs/` | Diagrams, notes, longer write-ups |

## Run it

Judges run `make run` from the root of the project, on a clean checkout:

```bash
make run
```

`make run` is expected to run the project using Docker, since that
is how the judges will run it.
- If you used other local open-weight models, include instructions for running the project in your technical report.
- Use the following environment variables:
```
LLM_NAME — name and version of the model
LLM_BASE_URL — endpoint base URL
LLM_API_KEY — your API key
```

## Getting started

1. Click **Use this template** to create your own repository.
2. Delete the other track directories. Don't rename or restructure yours.
3. Read its `README.md` and fill in `technical_report.md`.
4. Make `make run` work from the root of the project, on a clean checkout.

## License

All Hack Apertus projects are open-sourced. Please check our Terms & Conditions for specific licensing details (6. What you build is open source): https://hackapertus.ch/terms-and-conditions
