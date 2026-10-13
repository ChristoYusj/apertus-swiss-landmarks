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

## Official run and post-run corrections (13 Oct)
- Official run: `swiss-ai/Apertus-v1.5-70B`, 2,936 items, 2,936 `ok`, 0 truncated (`finish_reason=stop`),
  produced by the shipped `landmarks-eval run` after the pre-registration commit.
- **Code-grader fix v2 (after seeing answers, documented):** the abstention detector missed short refusals
  observed in the run ("Unsicher.", "Betg segir", "Incertain", "N/A", "nicht eindeutig identifizierbar");
  hedged guesses ("not 100 % sure, but it seems to be X") are now explicitly kept as attempts graded on X.
  Effect on code labels: 323 incorrect -> not_attempted, 116 not_attempted -> incorrect (of 2,936).
  The real answers that motivated each rule are pinned as regression tests (`test_grading_rules.py`).
  The LLM judge (primary grader) and the blind human audit are independent of this change.
- **Code-grader fix v3:** a premise-trap answer that abstains while repeating the false town is
  `not_attempted`, not "premise adopted".
- **Item-validity correction (rule-based, decided without looking at answers):** saint pairs
  ("St. Peter und Paul", "SS. Pietro e Paolo") and confession words ("römisch-katholisch", "reformiert",
  "cattolica"...) are type words; a text-only "where is it?" question is only valid if the *name shown* is
  distinctive. 74 text-only place items were removed; their responses are kept in
  `metadata/excluded_items.jsonl` with the reason. No item was added or re-asked.
- Source-hygiene regression test added after a tooling error inserted invisible control characters into
  grader regexes (caught by the tests before any result was reported).
