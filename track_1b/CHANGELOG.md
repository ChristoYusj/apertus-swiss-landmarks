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

## Second audit and protocol changes (13 Oct, afternoon)
- **Photo screening protocol v2-team (before any screening data existed):** the team screens together on one
  computer and records one joint decision per landmark, instead of three separate annotators with a
  100-photo overlap. Consequence: no inter-annotator agreement is reported for the photo screening (it is
  still reported for the grading audit, Task G, which stays independent). Only photos picked as 2nd view or
  low-information are shipped; unpicked candidates are never published. A main photo marked "exclude" or
  "wrong object" drops the landmark; its existing answers move to `metadata/excluded_items.jsonl` (code:
  `assemble.prune_results`), and the premise-trap draw is made before dropping so other items do not change.
- **Code-grader fix v4 (after seeing answers, documented):** an audit of *every* code-"correct" name grade
  (4 of 1,056) found 2 false positives: an abstention containing "bâtiment" (Wikidata lists "bâtiment" as an
  alias of that landmark) and "una torre dell'orologio" (a generic phrase stored as a name). We then listed
  all 786 tokens that made a name count as specific and classified each by hand: ~250 generic words were
  added to the type-word list (`normalize.GENERIC_WORDS_AUDIT`: building types, religious-order compounds,
  shared dedications such as "Assunta" or "Notre-Dame", museum/railway/military words, function words,
  inventory codes). Words that are also place or family names here were kept ("château de Villa",
  "Château Grenier"). Matching changes: an alias that names no kind of object ("bâtiment", "Building") is
  never used; a non-distinctive name counts as correct with the right town, also when the name itself
  contains the town ("Burg Rapperswil" when only "Rapperswil-Jona" is a place alias).
  Effect on the official run: exactly 2 code labels change (both correct -> not_attempted); no other label moves.
  Pinned by regression tests (`test_grading_rules.py`, section "Fix v4").
- **Item-validity rule applied again** with the audited word list (same rule as before, decided from the
  question text only): 94 more text-only place items (47 landmarks, FR+DE kept or dropped together) showed a
  name that does not identify the object ("Granary tower", "Former Arsenal", "Gare CFF", "Église anglaise",
  "Dreifaltigkeitskirche", "bâtiment"). Removed; responses kept in `metadata/excluded_items.jsonl`.
  Base set: 2,862 -> 2,768 items; verify V1-V5 pass.
- **Covariate added (not pre-registered):** `item_metadata.shown_name_lang` records the language of the name
  shown in text-only questions; where a landmark has no label in the question's language a fallback label is
  shown (mostly English in French questions). Results are reported with and without these items
  (sensitivity analysis, added after the run).

## Analyses added (13 Oct, after the run; labelled as such in the report)
- **Hypothesis tests implemented** (`analysis.py`, part of `scores.json`): H1b, H2, H2b, H3 (FR, DE), H4 and the
  Holm correction across them, exactly as registered. Two-sided cluster-bootstrap p-values for H1/H1b/H2.
  - H2 as registered compares against "the share of DE municipalities among wrong answers for DE landmarks",
    which is not an informative base rate; the registered test is kept in the Holm family and a clarified
    comparison (vs. the share of German-speaking municipalities among all current Swiss municipalities, BFS)
    is reported next to it.
  - H2b is not testable: only 3 wrong answers (1 landmark) name a look-alike's town; reported descriptively.
    Look-alike siblings are now shipped in `landmarks.jsonl` (`lookalike_siblings`) so this is reproducible.
- **Location analysis (exploratory, not registered):** which canton/municipality/country a place answer
  names, by question language, extracted deterministically with `metadata/gazetteer.json` (26 cantons,
  2,110 current + 1,126 former municipalities in 5 languages from Wikidata/BFS; Liechtenstein's BFS-numbered
  municipalities count as abroad). Matching rules (capitalised names only, no hyphenated continuation, church
  context, place cue for "Zug"/"Baden", short forms of suffixed names) were fixed by reading 40 random
  extractions plus every distinct extracted name, before the tables were interpreted; pinned in
  `tests/test_location.py`.
- **Stability check** (`landmarks-eval stability`): 100 items re-asked once, 20 of them twice more:
  72 % identical text, 100 % identical code label (kappa 1.0); 20/20 probe items kept their label over 4 answers.
- **Code-grader fix v5 (after seeing answers, documented):** the pre-registered rule "vague answers = not
  attempted" was not implemented for HEDGED answers: "Non sono sicuro, ma sembra essere una chiesa" was graded
  incorrect because "sembra" looked like a guess. Found while drafting the judge dev set (about half of 40 random
  code-"incorrect" name answers were vague hedges). Now a hedged answer is graded on its guess only if the guess
  names something checkable: a Swiss town or foreign country (gazetteer), a wrong canton, a saint's name, a type
  word with a name ("Castello di Vaduz"), a quoted name, or "Gemeinde X"; otherwise it is not attempted.
  Place answers naming only the RIGHT canton are not attempted; a wrong canton or a foreign country is incorrect.
  Unhedged bare answers are unchanged ("Sveti Stefan", "Riviera" stay incorrect). Effect: 145 labels
  incorrect -> not_attempted (97 name DE/IT, 46 place DE, 4 place FR/IT abstentions containing "peut-être");
  all 145 were read by hand. The judge prompt (not yet frozen) states the same two rules.
  Pinned by regression tests ("Fix v5" in `test_grading_rules.py`).
- **Item-validity rule (year leak, decided from the question text only):** a text-only year question whose shown
  name contains a year ("Rathausbrunnen (1833)") gives the answer away; 2 items removed (logged).
- **Judge prompt clarified before freezing:** premise items are graded only on whether the false town is accepted
  (naming another landmark without placing it there is NOT_ATTEMPTED), matching the code grader and H4.
- **Judge dev set drafted** (`responses/<model>/judge_dev_set.jsonl`, 40 items, labels proposed by Claude, to be
  confirmed by the team lead before the judge prompt is tuned and frozen); these items are excluded from the audit.

## Independent code review (13 Oct, evening) and fixes
An independent reviewer (separate agent, read-only) checked commits 1f4030c..86eba1a, re-ran the graders, and
confirmed: fix v4 changes exactly the 2 labels stated; the bootstrap refactor is numerically identical; Holm,
H3/H4 pairing, the premise-trap draw and the stability comparison are correct. Its findings, all fixed:
- **Builder reproducibility:** the audited type-word list had also entered the step-1 builder (which objects and
  aliases enter the dataset). Step 1 now uses frozen copies of the selection-time vocabulary and rules
  (`TYPE_WORDS_V1` = the set at a73986e, `distinctive_v1`). Check: a rebuild from the cached queries reproduces
  `landmarks.jsonl`, `reserves.jsonl` and `selection_report.json` exactly (264/264 QIDs in order, 0 field diffs).
- **Former municipalities' language region:** 516 former municipalities in multilingual cantons had none, so
  wrong answers naming e.g. Tarasp, Müstair, Bondo were dropped from H2 and the location tables. They now take
  canton and region from their successor (Wikidata P1366/P7888 chain): 1,050 of 1,126 resolved, 20 without region.
- **"im Kanton Bern" was read as the town Bern;** a town named after a canton now wins over the canton; an
  ambiguous town is narrowed by the canton named in the answer before preferring current municipalities.
- **Name grader:** a non-distinctive name with ANOTHER town ("Kunsthaus Aarau" for Kunsthaus Zürich) is
  incorrect (was not attempted); a town shared by two municipalities (Holderbank AG/SO) counts only with the
  right canton, also inside a canton-suffixed alias. Former names of the right town do not count as another town.
  Effect on the official run: 1 label (Q29573995 text-only DE, "Neuthal, Kanton Zürich." -> right canton only).
- **Exclusion log:** records keep the full response and judgement rows verbatim, one record per (item, model),
  an item that comes back is restored, line endings are preserved; dropped landmarks keep their answer key in
  `metadata/excluded_landmarks.jsonl`. Backfill of the 170 earlier records: 96 with full rows from backups; for
  the first 74 only the answer text and the grade at the time survive (stated in each record).
- **Privacy gate:** new verify check V7 fails while any shipped photo is not cleared by the screening (all 264
  are pending now, so verify FAILS until the team screening is merged; this is intended); the dataset card refuses
  to build in that state.
- **Directional hypotheses:** each registered test now reports `direction_as_hypothesised`; "supported" needs a
  Holm rejection in the registered direction. Bootstrap p-values use (k+1)/(B+1). H2 is reported per language.
- Minor: screening decisions record the main photo's id (merge refuses a mismatch); no "Santa Maria" short form;
  the stability probe items are a seeded random subset (the earlier run used the first 20 of the sample by id).
