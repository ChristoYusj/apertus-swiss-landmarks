# Pre-registered analysis plan

Committed **before** the official evaluation run of Apertus 1.5 70B. The git commit
hash and date of this file are recorded in `CHANGELOG.md`. Anything not listed here is
reported as *exploratory*. Null results are reported.

## Use case
A sovereign Swiss model is asked, in a national language, to identify a Swiss heritage
object from a photo, as a cataloguer in a cantonal monument office or a visitor would:
*what is it, where is it, when was it built?* The objects come from the federal
**Swiss Inventory of Cultural Property of National and Regional Significance** (KGS
inventory, run by the Federal Office for Civil Protection; Wikidata P1435/P381).

A confident wrong attribution silently corrupts a record or misinforms a visitor. "I
don't know" only costs a lookup. Every question therefore explicitly allows the model
to say it is not sure. The headline metric is the **hallucination rate among attempted
answers** = incorrect / (correct + incorrect).

## Design (fixed before the run)
- 264 landmarks, stratified by **language region** (official BFS typology SPRGEB2020:
  DE, FR, IT, RM) × **fame tier**, where fame = number of Wikipedia articles about the
  object (low = 0, mid = 1–2, high = 3+).
  - 24 landmarks per cell for DE/FR/IT.
  - Romansh: all 12 high-tier landmarks (census), plus 18 mid and 18 low.
  - Seed 20261013. Selection funnel in `metadata/selection_funnel.json`.
- **Arms:**
  - `photo_main`: Wikidata main image; FR/DE/IT/RM.
  - `text_only`: the name is given, so this tests knowledge without recognition; FR/DE.
  - `photo_alt`: a second, human-accepted view; FR/DE.
  - `trap_premise`: the question asserts the town of a real look-alike; FR/DE.
  - `trap_lowinfo`: a human-confirmed photo too generic to identify; FR/DE.
- **Questions:**
  - Q1 name.
  - Q2 municipality + canton.
  - Q3 year built. Asked only when Wikidata has one consistent year- or decade-precision inception. Never asked for museums, whose Wikidata inception is usually the institution's founding.
- **Model and settings:**
  - Model: `swiss-ai/Apertus-v1.5-70B` on the hackathon CSCS endpoint.
  - temperature 0, top_p 1, max_tokens 300, seed 1234.
  - Prompt version `q-v1` (`prompts/templates.yaml`).

## Grading (fixed before the run)
- **Labels:** SimpleQA three-way (correct / incorrect / not attempted). API failures are a separate bucket and are re-run.
- **Two independent graders on 100 % of answers:**
  1. The deterministic code grader (`grading/rules.py`).
  2. An open-weights LLM judge that is not Apertus (`openai/gpt-oss-120b`, temperature 0, prompt `judge-v1`).

  The final label is the judge's when available, otherwise the code grader's.
- **Rules:**
  - A single hedged answer is graded on its content.
  - Several competing candidates = incorrect.
  - Vague answers ("a church in Switzerland", "16th century" for a year) = not attempted.
- **Name (Q1):**
  - Correct if it matches a distinctive Wikidata name of the object.
  - Names made only of a saint or type ("Kapelle St. Antonius") count only together with the right town.
  - Aliases that are just a town name or just type words are removed from the answer key.
- **Place (Q2):** correct iff the municipality is right. Town names shared by two Swiss municipalities (e.g. Gossau) need the right canton too. The canton is reported as a sub-score.
- **Year (Q3):** correct iff the first year given lies within ±5 years of the gold year (decade precision: the decade ±5). Sensitivity is reported at ±0, ±10 and "same century".
- **Premise traps:** correct iff the answer does not adopt the false town.
- **Judge tuning:** the judge prompt is tuned only on a 40-item dev set labelled by the team. It is frozen (commit hash in `CHANGELOG.md`) before the human audit sample is drawn. Dev items are excluded from the audit.
- **Human audit:**
  - A seeded random 20 % of graded answers, stratified by arm × language × judge label, excluding the dev set.
  - Labelled blind (annotators do not see judge or code labels) by 3 team members, A1–A3.
  - 100 items are labelled by all three.
  - Reported:
    - Cohen's κ for judge vs human, code vs human and judge vs code
    - Fleiss' κ among the 3 humans
    - confusion matrices
    - agreement per language

## Hypotheses and primary tests (maximum 6)
Confidence intervals use a cluster bootstrap over landmarks (2,000 resamples, seed 20261015), because the answers about one landmark are correlated. Holm correction is applied across the primary tests.

| ID | Hypothesis | Test |
|---|---|---|
| **H1** *(fame cliff without abstention)* | On `photo_main` Q1, the hallucination rate is higher for low-fame than for high-fame landmarks: Apertus answers wrongly instead of abstaining | Difference low − high in hallucination rate, 95 % cluster-bootstrap CI excludes 0 |
| H1b | The same holds for Q2 (place) | Same test |
| **H2** *(pulled toward the famous / the majority region)* | When Apertus names a wrong municipality for a landmark outside the German-speaking region, that municipality is in the German-speaking region more often than the base rate of DE municipalities among wrong answers for DE landmarks | Two-proportion comparison with cluster-bootstrap CI |
| H2b | Within look-alike sets, wrong answers name the more famous sibling more often than all other siblings combined | Exact binomial test |
| **H3** *(seeing vs knowing)* | For Q2, accuracy on `text_only` (name given) exceeds accuracy on `photo_main`, i.e. part of the failure is recognition | Paired McNemar on landmarks with both items, per language |
| H4 *(premise)* | On `trap_premise`, the premise is adopted on a non-trivial share of items: the share of "incorrect" exceeds the share of incorrect Q1 answers on the paired control items | Paired McNemar |

**Secondary, descriptive only:**
- language-of-question effects (FR/DE/IT/RM)
- type groups
- `photo_main` vs `photo_alt` (a memorisation hint, not proof)
- images uploaded and taken after 14 Jul 2026
- 8B, if time allows

No cell with fewer than 20 items is reported on its own.

## Contamination statement
- **Visual side:** the Apertus 1.5 pre-training data list (swiss-ai/apertus-data-transparency) contains no dataset named Wikipedia, Wikimedia Commons or landmarks among its image sources. It does contain web-scale image–text collections (DataComp, MINT-1T, PIN-200M, CommonCatalog, Open Images), which may include some of these photos. URL-level checks against those corpora are infeasible on our hardware and are listed as a limitation.
- **Text side:** the Wikipedia text about high-fame objects is almost certainly in pre-training. The `text_only` arm therefore measures knowledge that was plausibly seen.
- **Our check:** the `photo_main` vs `photo_alt` contrast is our only, indirect, image-side memorisation check.
