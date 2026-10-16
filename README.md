# Swiss Heritage Factuality — Hack Apertus 2026, Track 1B (Red Pandas)

Does Apertus 1.5 recognise Switzerland's heritage landmarks, and does it say so when it does not? A
four-language (FR/DE/IT/RM) benchmark: 5,210 questions on 242 landmarks of the Swiss inventory of cultural
property (KGS), with 409 photos. Models: Apertus 1.5 70B and 8B, with Gemma-4-31B as a comparison. The harness
grades, scores and verifies its own outputs.

**Headline (Apertus 1.5 70B).** With four named options it picks the right landmark 34 % of the time (chance
25 %; Gemma-4-31B: 60 %). In free answers on the same photos it mostly declines in French (11 % of names wrong)
but answers in Romansh (69 % of names and 97 % of places wrong).

**Who checked what.** Photos: screened by AI (Claude, then a second AI agent, Hermes; the team lead decided 6
edge cases), then reviewed again by a Gemini agent, whose 14 flags the team lead accepted; no person reviewed every
shipped photo. Grading:
one human annotator (the team lead) graded 693 Apertus-70B answers blind (670 in the dataset = 20.5 % of the
70B core answers; judge–human κ = 0.79). Details: `track_1b/docs/ai_use_statement.md`.

| | |
|---|---|
| Project | [`track_1b/`](track_1b/): overview, results, layout and commands in its README |
| Report | [`track_1b/technical_report.md`](track_1b/technical_report.md) (PDF: `track_1b/RedPandas_Report.pdf`) |
| Dataset | Hugging Face `chrizzto/swiss-heritage-factuality` (CDLA-Permissive-2.0; photos keep their CC licences) |
| Decisions and corrections | [`track_1b/CHANGELOG.md`](track_1b/CHANGELOG.md) |

**Status.** The pinned dataset revision (`26d86b35`) is the first release: the 3,412 core items from before the
third photo check (it still contains the 14 flagged photos). The photo screening is done. Pending: a re-release
with all 5,210 items and a new pinned revision, `main` fast-forwarded with a new tag, and the final report PDF.

**Run** (Docker, clean checkout):

```bash
make run
```

- No keys: downloads the pinned dataset and checks the reference results (Apertus 70B): every stored answer
  re-graded by the code grader, recomputed scores equal to the published ones (exit code = result). CPU only,
  about a minute.
- With `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY` exported (any OpenAI-compatible endpoint): also evaluates that
  model on a seeded, stratified sample (`SAMPLE=150`) or on all items (`FULL=1`).
- Optional judge: `JUDGE_MODEL`, `JUDGE_BASE_URL`, `JUDGE_API_KEY` (we used `openai/gpt-oss-120b:groq` via
  `https://router.huggingface.co/v1`, prompt `judge-v1`). Without it, the code grader grades alone. Variables:
  `track_1b/.env.example`.
- Requirements: Docker. An API key only for live runs. No model weights are downloaded. A full 70B run takes
  under an hour.

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
