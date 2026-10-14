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
- **Code-grader fix v5b (second audit of every hedged answer):** the v5 "names something specific" detector had
  false positives (German plurals such as "mittelalterliche Burgen", function words after a noun such as
  "auf einem Hügel, der ...", and names merely repeated from the text-only question, e.g. «Grimmenturm») and
  missed real names ("il Teatro alla Scala", "l'Abbazia di Ettal", bold names, "situà a Cuera", "à Sent").
  Now: the name shown in the question is removed before checking; only building nouns anchor a name
  (`TYPE_NOUNS`, no function words or adjectives); an Italian/French definite article + capitalised word, a
  **bold** name, or a capitalised word after a locative preposition count as names; "Sent" counts as the
  village only outside dedications ("baselgia da Sent Martin"). Effect: 39 labels incorrect -> not_attempted
  (all read by hand); pinned in `test_grading_rules.py` ("Fix v5b").
- **Stability re-run** with a random probe subset: 75 % identical text, 99 % identical code label (kappa 0.98).

## Team-lead decisions on the judge dev set (13 Oct, night)
The lead ruled on the 4 hard dev-set cases; the rules now apply to the judge prompt (not yet frozen), the human
guidelines (Task G) and the code grader:
- a similar but different name ("Museo cantonale d'arte e di storia" for "Museo Cantonale d'Arte") is incorrect;
- place (photo questions): the right town with a DIFFERENT landmark ("chiesa di San Martino a Poschiavo" for
  San Vittore) is incorrect; a village inside the gold municipality instead of the municipality is incorrect;
- premise traps: naming a landmark that is not the gold one is incorrect even without the false town (the right
  saint without a town stays not attempted). The pre-registered H4 keeps its definition (false town ADOPTED,
  code rule `premise_adopted`); the stricter version is reported as `H4_lead_rule` outside the Holm family.
Also fixed: "il chantun è Turitg" names the canton, not the town Zürich (`mentions_as_town`).
Effect on the official run: 7 labels (70B), 4 (8B), all read by hand. Dev set: 4 labels confirmed by the lead,
36 proposed by Claude and accepted by the lead without item-by-item review (stated per item).

## Second independent review of the code grader (13 Oct, late night) and fixes
A second reviewer (separate agent, read-only) read every answer the code grader marked incorrect, for both
models. Its findings and what changed (`grading/rules.py`, `build/gazetteer.py`, `analysis.py`):
- **Refusals graded as wrong (must fix):** phrasings the patterns did not know ("Non è sicuro identificare…",
  "Ich bin mir nicht sicher, wo…", "nicht eindeutig aus dem Bild ableitbar", "mir nicht bekannt", "Je ne dispose
  pas d'informations", "Betga segir", "Nessuna informaziun", "Non indicheda", "impossible de donner un nom",
  "Je ne trouve pas", and the 70B's one-word Romansh "Nesgir" = "Na segir" run together) are now abstentions.
  "Not sure, BUT it is X" is graded on X (contrast words ma/mais/aber/but/cependant/...).
- **Similar-name rule was not in the code (must fix):** an alias continued by more name words ("Museo cantonale
  d'arte e di storia" for "Museo Cantonale d'Arte") is now `incorrect` (`similar_but_different_name`).
- **Premise: a rejected false town beat a wrong landmark (must fix):** "the Kapellbrücke in Luzern, not in Baden"
  is now `incorrect` (`premise_negated_wrong_landmark`). An abstention that repeats the false town after a
  contrast word ("…, mais … de quel bâtiment il s'agit à Alto Malcantone") is not adoption; the adjective form of
  the false town ("Reuenthaler Staumauer" for Full-Reuenthal) is adoption.
- **"Right canton only" let wrong places through (must fix):** before an answer counts as "right canton only"
  (not attempted), any remaining name word makes it incorrect: villages ("Neuthal, Kanton Zürich", "Vésenaz"),
  towns the gazetteer lacks ("Setteln"), "Italien, Tessin". Two or more named cantons are competing candidates
  and incorrect whichever is the gold (was graded by order).
- **Bare type words (must fix, pre-registered rule):** an answer that names nothing ("Kapelle", "Bahnhof",
  "Chasa da baselgia", "Covered Bridge") is not attempted. The list of words that made "names something" fire was
  printed for every answer of both models and read; common nouns found there were added to `GENERIC_CAPS`.
- **Echo of the shown name:** the name shown in a text-only question is still removed, but its words are removed
  only inside the answer's own quotes. "Schloss Tarasp befindet sich in der Gemeinde Tarasp" now counts Tarasp
  as the claimed place (a former municipality, so incorrect under the village rule); before, the word-by-word
  removal hid it, and also hid "Fribourg" in "Fribourg, canton de Fribourg" for the Romont fortifications.
- Smaller: more countries in the gazetteer (Denmark/"Danimarca", Estonia, Sweden, …, USA; Scotland under GB);
  "Cuera" (Sursilvan) for Chur; "Sent" is the village unless a capitalised word follows directly ("Sent
  Martin"); "dédiée à Cosmas" introduces a saint, not a place; "d'Enfer" is split so the capital is seen;
  a missing space ("chantunSurselva") is split; sentence-initial connectives ("Sans", "Cependant") are not names.
- Not changed (reported as known limitations): descriptive museum names count as vague; a wrong building type
  with the right town in a NAME answer is not detected; Q663436 text-only place stays a lucky correct (text-only
  questions get no object check); "am Vierwaldstättersee … Zentralschweiz" stays not attempted.
- **Effect:** 70B 109 labels moved (100 incorrect -> not_attempted, 8 not_attempted -> incorrect, 1 correct ->
  incorrect: the similar name); 8B 356 moved (349 incorrect -> not_attempted, 6 not_attempted -> incorrect,
  1 correct -> incorrect: the Kapellbrücke premise). Every changed label was read by hand, in four passes, each
  diffed against the previous one. Registered results: 70B H3_de and H4 still supported (H4 78 % vs 28 %);
  8B H1b no longer significant after Holm (p_Holm 0.04 -> 0.08). Stability re-graded offline with the new grader
  (`stability --regrade`, no requests): unchanged, 99 % same label.
- 51 regression tests with the real answers ("Review 2" in `test_grading_rules.py`); 38 of them fail on the
  previous grader. 205 tests pass.

## Third independent review (13 Oct, night) and fixes
A third reviewer (separate agent, read-only) re-graded all 5,532 stored labels (0 mismatches with the code), then
read 831 labels: every label of the small rule groups (other_place_named, names_nothing, premise_*, hedged_*,
right_canton_only, similar_but_different_name, ...) and a seeded random 150 per model. All premise_adopted labels
(73), both hedged groups and all trap declines were confirmed. Findings and fixes (`grading/rules.py`):
- **Named landmarks missed:** "Musee gruérien" (a lowercase place adjective after a building noun) and "Chaplutta
  da Sur En" (two capitalised short words mid-sentence form a name) are now attempts, graded incorrect.
- **Common nouns read as names:** the building-noun anchor no longer crosses a bracket or comma ("Rathaus
  (Stadtverwaltung)"); a hyphenated word counts only if one part is a name ("Uhren-Turm"); the trigger-word audit
  was repeated over EVERY claim branch (anchor, article, name+noun, quoted, preposition, town cue), both models,
  and the common nouns found were added to `GENERIC_CAPS` (Fundaziun, Posta, Parrocchia, Muntogna, Stadtverwaltung,
  Centrale, ...). `claim_evidence()` / `name_evidence()` now return the triggering word, so the audit is reproducible.
- **The gold saint in another language:** "Pfarrkirche St. Martin" for "Katholische Kirche S. Martin" was graded
  incorrect. Saints' names are now compared across languages (Antonius = Antonio, Giachem = Jakob, Jean-Baptiste =
  Giovanni Battista; Mary Magdalene is not Mary) and the gold saint is treated like a non-distinctive name: with the
  right town correct, with another town or another name incorrect, alone not attempted (as already for premises).
- Missed refusal: Sursilvan "Non inditgà".
- **Answer keys (place):** 16 Wikidata "located in" labels that are not names of the current gold municipality
  (Kreis 1, Töss, Basel-Vorstädte, Region Surselva, Waltensburg/Vuorz, Ardez) were removed from `place_aliases`
  (team-lead village rule) in `assemble.clean_place_aliases`, logged in `metadata/removed_place_aliases.jsonl`.
  BFS register names stay (a border landmark lists both municipalities). Runs after the questions are built, so no
  item changes; no stored label changed (verify V4 passes).
- Decided, not changed: "Château de la Tour" stays vague (a building noun after "de la"), "Tour de la Roche" is a
  name; "Sontga Maria" as a place answer is a (wrong) place; "Champ-Pittet, Kanton Waadt" is a locality = incorrect.
- **Effect:** 70B 18 labels (10 incorrect -> not_attempted, 4 not_attempted -> incorrect, 4 rule only); 8B 31 (29
  incorrect -> not_attempted, 2 rule only); all read by hand. 70B: H4 78 % vs 24 % (control lower), name wrong
  FR 9 / IT 24 / DE 39 / RM 52 %; registered results unchanged (H3_de, H4 supported). Stability re-graded: unchanged.
- 20 regression tests ("Review 3"; 14 fail on the previous grader) + 1 for the alias cleaning; 226 tests pass.

## LLM judge: dev-set tuning and freeze (13 Oct, night)
- Judge: `openai/gpt-oss-120b` via the Hugging Face router, pinned to one provider (`:groq`) so verdicts are
  reproducible; temperature 0, max_tokens 1500 (the model's hidden reasoning, ~250-400 tokens, counts against it).
- Dev set (40 items, labels confirmed by the lead; never used for the audit): first run 39/40 agree (kappa 0.95).
  Tuning, on these 40 items only, two clarifications:
  1. a descriptor before the municipality's own name is not wrong ("Gemeinde Val Verzasca" for Verzasca);
  2. that edit made one premise item flip ("not sure which building in Geneva this is" read as accepting the
     false town), so the existing premise rule was stated as its own line with that example.
  Final prompt: 40/40 agree with the confirmed labels (kappa 1.0) on two independent runs, and the two runs agree
  with each other on 40/40 (`responses/apertus-v1.5-70b/judge_dev_eval.json`). The code grader agrees on 39/40.
- **Frozen as `judge-v1` by the commit containing this entry**, before the full judge run and before the human
  audit sample is drawn. Judging is parallel (`JUDGE_CONCURRENCY`) and resumable (cache by response hash and
  prompt version, file written every 200 items). New command `landmarks-eval judge-dev`.

## Human audit protocol v3: one annotator (14 Oct, before the sample was drawn)
- The team has ONE annotator for Task G, not three (deviation from analysis_plan.md, which registered three
  annotators with a 100-item overlap and Fleiss' kappa). The sample is unchanged in size and design: a seeded,
  stratified 20 % of the 70B answers (the track's "20 % human check"), excluding the judge dev set.
- Instead of agreement between annotators, 40 sampled items are shown a second time, each at least 150 items
  after its first showing, without notice; test-retest agreement (raw, Cohen's kappa) is reported as the
  annotator's self-consistency (`agreement.self_consistency`, `human_audit_repeat.jsonl`).
- Judge-vs-human and code-vs-human agreement are reported as planned. Inter-annotator agreement cannot be
  reported (stated as a limitation).
- The online audit page (`tools/audit_online`) and the offline page show the same items in the same order;
  answers not in French get a labelled English machine gloss (`landmarks-eval glosses`, gpt-oss-120b, names kept).

## Full judge run and review 4: every judge-vs-code disagreement re-read (14 Oct)
- Judge `judge-v1` (`openai/gpt-oss-120b:groq`) on all 5,532 answers (70B and 8B): 0 API errors, 0 unparsed.
  Final labels = the judge's (registered). Results with judge labels: 70B name wrong FR 10 / IT 24 / DE 40 /
  RM 66 %; H4 supported (78 % vs 28 %); H3_de no longer significant after Holm (p = 0.02, p_Holm = 0.11).
- **Review 4.** All 192 disagreements (75 + 117) were re-read by independent adjudicator agents against the
  written rules; where the judge looked wrong a second blind read followed. Judge right 85, code grader right
  101, unsettled 6 (`responses/<model>/disagreement_adjudication.jsonl`, marked AI-assisted, not a human audit).
  - Judge errors (frozen, reported as a limitation): vague answers whose building type FITS the landmark graded
    incorrect (57), "[only with the town]" names ignored (31), refusals or premise repeats read as claims (7),
    missed contradictions (6). Sensitivity analysis (`scores.json: sensitivity_adjudicated`): replacing the
    judge's label where the re-read settled it changes RM name wrong 66 % -> 58 % (70B), 89 % -> 80 % (8B);
    every other cell moves by about 1 pp or less.
  - **Code grader (post-hoc rule change, `grading/contradict.py`):** SimpleQA's "not attempted" requires that
    the answer does not contradict the gold, and the code grader ignored contradictions in vague answers. Now a
    vague answer is incorrect when it states a building type the landmark is not (coarse classes from the gold's
    names; a fitting type stays not attempted; "X or a historic building" commits to no type; the inventory's
    museum type group is not trusted), a denomination the gold contradicts, a century that excludes the gold
    year (Romansh ordinals and Roman numerals now read), or a Swiss region that excludes the gold canton. Also:
    early years with a cue ("ca. 450"), "Italy or an Alpine area" is not a foreign claim, a firm sentence
    placing the landmark abroad counts after a refusal, more refusal spellings. Not adopted (single-read
    evidence, would reverse earlier reviewed decisions): name-shaped phrases of common nouns, the text-only
    object check. Effect vs the adjudication: 51 code errors fixed, 0 broken, 34 remain; 14 further labels
    where judge and code had agreed changed (12 centuries outside the window, 2 contradicting types), all
    checked against the gold. Judge-vs-code kappa 0.937 -> 0.950 (70B), 0.917 -> 0.933 (8B).
  - 17 regression tests ("Review 4"); 248 tests pass.

## Photo screening protocol v3-ai-assisted (14 Oct, before any screening decision existed)
- The joint team screening (v2-team) had 0 decisions on 14 Oct morning and the team could not spare the hours
  for 917 photos, so Task P is run as **AI screening + human check** (`docs/annotation_guidelines.md`, Task P as
  run). The rules (privacy, wrong object, 2nd view, too generic) are unchanged; no model answer is shown at
  any step.
- Step 1, AI screening: Claude Opus 5.5, 8 parallel screeners, every one of the 917 photos opened at the
  published 500-px size; a structured record per photo. Proposed: 6 landmarks dropped (3 privacy: two with
  visible faces, one with a partly readable plate; 3 wrong object: a painting, a display case of pots, and a
  photo of Schloss Wildenberg filed as the San Bastian church in Zernez), 177 second views, 50 too-generic photos.
- Step 2, independent AI re-check: 3 further instances, without the screeners' reasons, re-checked all 491
  photos the screening would publish. Disagreement on the binary privacy flag (recognisable person, plate,
  private interior or personal text): 2 of 491 photos (one main photo the screener kept, one it excluded).
  Role doubts: 14 of 177 second views ("not the same object" 1, "unsure" 13), 7 main photos (exhibit-only or
  hidden building); all 50 too-generic photos confirmed.
- Step 3, human check (A1): `tools/screening_online/check.html` shows each landmark with only the photos that
  would be published, flagged rows first (139 of 264). A1's verdict wins (`landmarks-eval combine-screening`);
  a photo ships only if A1 accepted it; unchecked landmarks stay pending, so verify V7 fails until a person has
  seen every published photo. Image records name both reviewers (`ai:claude-opus-5-5`, `A1`).
- Clarification for the check (consistent with rule 1): a main photo showing only exhibits (a display case, a
  painting) is "wrong object"; a room inside the museum still shows the museum. The screeners had applied
  this inconsistently (one display case marked wrong, two kept), so those rows are flagged for A1.
- Dry run on a copy (assuming every AI call is accepted): 2,766 -> 3,600 items (+796 photo_alt, +98
  trap_lowinfo, -60 items of the 6 dropped landmarks, whose answers move to `metadata/excluded_items.jsonl`);
  no kept item changes.

## Photo screening as run: second AI review instead of the human check (15 Oct, protocol v3b-ai-review)
- The human check page (step 3 above) was used for 3 rows only. Instead, a separate AI agent (Hermes) reviewed
  the same 491 photos under the lead's policy "if unsure, exclude" (32 photos excluded under that policy), and the
  lead decided 6 edge cases directly plus one in chat (San Bastian, Zernez: the main photo shows Schloss
  Wildenberg -> wrong object). **No person looked at every published photo**; the report says so.
- Merged with `combine-screening` (converter `tools/screening_online/hermes_to_check.py`; A1 decisions in
  `work/review/a1_decisions.json`). `merge_review` now records reviewers per landmark (`ai:claude-opus-5-5`,
  `ai:hermes`, plus `A1` where a person decided) and a drop reason per landmark.
- Result: 13 landmarks dropped (privacy 4: visible faces; wrong object 4: a painting, two display cases, the
  Wildenberg photo; "may not show the landmark (excluded when unsure)" 5), 161 second views, 17 too-generic
  photos. Dataset: 251 landmarks, 3,412 items (+732 photo_alt, +34 trap_lowinfo; 120 items of the dropped
  landmarks moved per model to `metadata/excluded_items.jsonl`), 429 photos shipped. verify V7 passes.
- 24 of the 546 audit-sample items belong to dropped landmarks; agreement statistics use the items still in the
  dataset, and the count is reported.
- Judge calls now log their token usage per chunk (paid API; the HF dashboard has the exact cost).

## New photo items run and judged; review 5 (15 Oct, night)
- `photo_alt` (732) and `trap_lowinfo` (34) items run on Apertus 1.5 70B and 8B with the shipped `run` (cached
  answers reused, only new requests sent): 3,412/3,412 `ok` for both; 8B: 2 answers hit max_tokens.
- Judged with the frozen `judge-v1` (766 new answers per model, 0 failures; tokens in/out 574k/160k for 70B,
  572k/140k for 8B; now logged per chunk).
- **Review 5:** the 44 judge-vs-code disagreements not covered by review 4 (new items, and labels the review-4
  contradiction rules changed) re-read with the same two-read protocol. Settled by label: judge right 11, code
  right 31, neither 1, unsettled 1. Every current disagreement (70B 72, 8B 108) now has a re-read. Sensitivity
  (`sensitivity_adjudicated`): 70B RM name wrong 68 % -> 59 %, RM year +6 pp, other cells <= 1.2 pp.
- **Result changes caused by the screening (13 landmarks removed):** the language pattern is unchanged (70B name
  wrong FR 11 / IT 24 / DE 41 / RM 68 %). H3 (French) is now significant after Holm (text 8 vs photo 0,
  p_Holm = 0.04); before the screening it was 8 vs 1 (p_Holm = 0.13): the one photo-correct French answer was on a
  landmark removed for privacy. Reported as fragile in the report.
- Descriptive (analysis plan, secondary): second view vs main photo shows no advantage for the main photos
  (70B 2 vs 2 correct names, different landmarks); on low-information photos 70B declined 34/34 and 8B 33/34.
- The second AI's grades of the audit sample are stored as `ai_crosscheck_audit.jsonl` and scored as
  `ai_crosscheck_audit` (marked `not_a_human_audit`); audit items of removed landmarks are skipped and counted.
- Reference scores for `verify` V6 (= the 70B scores) are added to `src/landmarks_eval/expected/` at release,
  together with the pinned dataset revision (CI runs `make run` once that file exists). A Docker run with the
  dataset mounted read-only passed V1-V7, which also showed `verify` must not write into the dataset (fixed).

## Final audit before submission (15 Oct, night): corrections
Three independent auditors (Claude agents: report numbers vs data, provenance claims across documents, code review)
and one skeptic re-check. Fixed:
- **Wording that overstated human work.** "read by hand" / "classified by hand" in the entries of 13 Oct means read
  item by item by Claude (AI-assisted), not by a person. "Labels confirmed by the lead" for the judge dev set means
  4 lead rulings + 36 labels proposed by Claude and accepted without item-by-item review. The report, the dataset
  card and `docs/ai_use_statement.md` now say this; the card no longer says the questions were "written by the
  team" (templates drafted with Claude Code).
- **Per-photo credit.** A1 is now credited only on the photos a person decided (3 shipped photos), not on every
  photo of a landmark with one human decision; a screening-check file must name its checker (an unnamed one was
  taken for A1); the dropped-main-photo classes come from a reviewed table instead of a keyword match.
- **Numbers.** Second view: 70B names 1 landmark correctly (in FR and DE), not 2 different ones (entry above).
  Re-reads: 236 over two rounds, 224 still in the dataset (judge 86, code 131, neither 1, unsettled 6). The
  sensitivity analysis also lowers the premise-trap rate (88 % -> 83 %). 8B Graubünden pull stated with the same
  statistics as 70B. The audit sample is 20 % of the 2,726 answers before the screening (522 still in the dataset;
  the later items are not covered). AI cross-check counts: 24 sampled items dropped with their landmark, 18
  in-dataset items unscored, 504 compared; its confusion matrix is keyed `confusion_ai_rows`.
- **Plan deviations not yet acknowledged:** the post-14-Jul-2026 photo contrast was not possible (no shipped photo
  is that recent); the year-window sensitivity (±0/±10/century) was not run (2 of 268 photo year answers).
- Scores and merge files are written with LF line endings on every platform; the dataset card refuses an unknown
  screening protocol instead of describing a team screening.
- **Privacy gate standard, stated plainly:** V7 checks that every shipped photo has a screening decision. Under
  protocol v3 that decision needed a person; as run (v3b) V7 passes on AI clearance for 426 of 429 shipped photos
  (`pii_reviewer_ids` = Claude + Hermes; 3 also carry A1). The gate was not tightened back, so the report says that
  no person reviewed every shipped photo. The guideline's Task G "as run" text now says the human labels are not
  yet collected; the card no longer lists a `split` field (no test case has one).
