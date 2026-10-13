# Changelog

## Pre-registration (before the official evaluation run)
- 2026-10-13T11:39Z: the commit containing this entry freezes `docs/analysis_plan.md`, the question templates
  (`prompts/templates.yaml`, prompt version `q-v1`), the generation parameters (`run.py`: temperature 0,
  top_p 1, max_tokens 300, seed 1234) and the deterministic code grader (`grading/rules.py`).
  The official Apertus 1.5 70B responses are produced after this commit by the shipped `landmarks-eval run`.
- Not yet frozen at this point: the LLM-judge prompt (tuned on a 40-item dev set, frozen before the human
  audit sample is drawn; separate entry below).

## Dataset construction log
- Step 1 (13 Oct): 13,417 heritage objects -> 4,153 eligible -> 264 landmarks (seed 20261013).
  Independent audit (separate script, live Wikidata): 25/25 landmarks match; hazards found and fixed:
  town-only / type-only name aliases removed (47), saint/type-only names flagged non-distinctive (need the town),
  town names shared with another municipality need the canton, museum inception dates not used as build years,
  palaces/villas excluded, canton-suffix town names ("Carouge (GE)") split.
- Step 2 (13 Oct): 264 main photos + 653 candidate second views; licence allow-list incl. CC BY(-SA) 1.0;
  10 landmarks replaced by same-stratum reserves (no licence / too small / no author).
- Fix: the template's `.gitignore` ignored any `build/` folder, which hid the dataset-builder package;
  now tracked, and CI fails if any source file is untracked.
