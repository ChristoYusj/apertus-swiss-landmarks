# Technical report — Swiss Heritage Factuality: does Apertus recognise Switzerland's landmarks?

> **DRAFT 13 Oct.** Numbers marked ⟨code⟩ are from the deterministic code grader only; the primary LLM judge
> and the blind human audit are pending and will replace them. Do not quote ⟨code⟩ numbers as final.

> We built a four-language (FR/DE/IT/RM) benchmark of 2,766 questions about 264 Swiss heritage landmarks from the
> federal inventory (KGS), stratified by language region and fame, with photo, text-only and trap variants and
> per-item licences. Apertus 1.5 70B almost never recognises a landmark from its photo, and when it commits to a
> name it is wrong about 99 % of the time ⟨code⟩. Whether it commits at all depends on the question's
> language: on the same photos it declines in French (10 % confidently wrong) but answers confidently in Romansh
> (72 % wrong), where it also relocates half of all non-Graubünden landmarks to Graubünden.

**Track:** Apertus Readiness - Track 1B (Swiss Voices), dimension: core-task intelligence (factuality)  
**Event:** Online  
**Team:** Red Pandas — `member`, `member`, `member`, `member`  
**Demo / data:** dataset `huggingface.co/datasets/chrizzto/swiss-heritage-factuality` ⟨to publish⟩ ·
code `github.com/ChristoYusj/apertus-swiss-landmarks`

----

### Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B` (main), `swiss-ai/Apertus-v1.5-8B` (secondary comparison)
- **How it is used:** evaluation (multimodal: photo + question)
- **Where it runs:** hosted CSCS inference endpoint (OpenAI-compatible); the harness accepts any
  OpenAI-compatible endpoint via `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`

----
## Use Case Description

A visitor, a teacher or a tourism chatbot points a phone at a Swiss chapel, castle or fountain and asks
"what is this, where is it, when was it built?". This is a natural, high-volume use of a Swiss multimodal
assistant, and it is exactly where a confident wrong answer is costly: it is believable, it is about a real
place, and the person asking usually cannot check it. Switzerland's heritage is also a clean test of
*localised* knowledge: the federal inventory of cultural property (KGS) lists thousands of objects, most of them
known only locally, spread over four language regions of very unequal size.

We therefore measure **factuality and hallucination** (SimpleQA-style: correct / incorrect / not attempted) of
Apertus 1.5 on Swiss heritage landmarks, and ask four questions fixed before the run (pre-registration commit
`a73986e`, `docs/analysis_plan.md`): does Apertus invent more about obscure landmarks (H1); are wrong answers
pulled toward the German-speaking majority (H2) or toward famous look-alikes (H2b); is the failure one of
*recognition* (photo) rather than *knowledge* (name given) (H3); and does it accept a false premise in the
question (H4)?

## Dataset Summary

| | |
|---|---|
| Landmarks | 264 KGS heritage objects (A: 109, B: 146, local: 9) in 4 BFS language regions × 3 fame tiers |
| Fame tiers | Wikipedia articles: low 0, mid 1–2, high ≥ 3 (24 per cell; Romansh region: census of a small pool) |
| Types | churches 110, castles 63, museums 36, civic 19, bridges 14, fountains 10, towers/gates 10, monuments 2 |
| Photos | 264 main photos (Wikidata P18) + candidate second views; 500 px, EXIF stripped, per-image licence |
| Questions | 2,766 (2,384 photo questions, each in 4 languages; 332 text-only; 50 premise traps; + second-view and low-information photo items after screening ⟨pending⟩) |
| Question types | Q1 name, Q2 municipality + canton, Q3 year built (68 landmarks with a precise, unconflicted year) |
| Languages | French, German, Italian, Romansh (Rumantsch Grischun); identical templates, explicit "if unsure, say so" |
| Answer keys | Wikidata (CC0) + BFS municipality register: name aliases (flagged if only valid with the town), current/former municipality names, canton names in 5 languages, year windows |
| Licences | questions/keys/responses CDLA-Permissive-2.0; photos keep their CC licence (TASL attribution per item) |

**Arms.** `photo_main`: the photo, asked in all four languages (same image → language is the only change).
`text_only`: the landmark's name is given and the place or year is asked (FR, DE), separating *recognition*
from *knowledge*. `trap_premise`: the question asserts the town of a real look-alike in another municipality
("This building is in Rothrist. Which building is it?"). After the photo screening: `photo_alt` (a second view
of the same object, a memorisation hint) and `trap_lowinfo` (a photo too generic to identify; declining is right).

**Selection funnel** (seed 20261013): 13,417 heritage objects with a photo → 4,153 eligible (public landmark
types, a current municipality, a specific label, one language region) → stratified sample of 264 + 83
same-cell reserves for replacements.

## Data Collection Method

**Sources.** Wikidata (QLever mirror, cached queries in the repository) for objects, names, inception dates and
administrative location; the Federal Statistical Office municipality register (01-10-2026) for municipality
numbers, cantons and language regions; Wikimedia Commons for photos and their licences.

**Answer-key construction and cleaning** (all rules in code, all decisions logged in `CHANGELOG.md`):
- Name aliases from Wikidata labels/aliases/sitelinks in EN/FR/DE/IT/RM/GSW. Aliases that are only a town name
  or only type words are dropped. A name is *non-distinctive* if, after removing type words, saints' names and
  the town, nothing is left ("Kapelle St. Antonius", "Kunsthaus Zürich"): it then counts only together with the
  right town. The type-word list was audited by hand over all 786 tokens that occur in the names.
- Place aliases: current, former and merged municipality names; town names shared by two municipalities
  (e.g. Gossau) require the canton.
- Year: only preferred, unconflicted inception values with year precision (window ±5) or decade precision;
  museum founding dates are not used as build years.
- An independent script re-checked 25 random landmarks against live Wikidata (25/25).

**Question validity rules** (decided from the question text only): a text-only "where is it?" question is kept
only if the name shown is distinctive in both FR and DE and does not contain the town; a text-only year
question is dropped if the shown name contains a year. 170 items were removed this way after the run; their
responses are kept in `metadata/excluded_items.jsonl` with the reason.

**Human annotation** (`docs/annotation_guidelines.md`).
- *Task P, photo screening:* the team screens every shipped photo jointly (one decision per landmark): privacy
  (recognisable people, licence plates, private interiors → exclude, never blur), "wrong object", the best second
  view, and "too generic" photos for the low-information trap ⟨pending⟩.
- *Task G, grading audit:* three team members (A1–A3) label a seeded, stratified 20 % of graded answers blind
  (they do not see the judge's or the code grader's labels), 100 items by all three ⟨pending⟩.

**Consent and personal data.** No person is a data subject: photos with recognisable people are excluded,
EXIF is stripped. Annotators sign the consent form in `docs/consent_form_template.md` (pseudonymous IDs).

## Dataset Details

- **Quality metrics:** answer-key audit (above), selection funnel, per-cell counts, item-validity rules,
  stability of answers at temperature 0 (below), judge–code–human agreement ⟨pending⟩.
- **Diversity / edge cases:** four languages incl. Romansh; fame tiers; same-photo language contrast; text vs
  photo; false-premise traps with real look-alikes; low-information photos ⟨pending⟩; ambiguous town names;
  non-distinctive names.
- **Contamination:** the Apertus pre-training data list contains no Wikimedia/landmark image set by name, but
  includes web-scale image–text corpora that may contain some of these photos; URL-level checks are infeasible
  for us (limitation). The `photo_main` vs `photo_alt` contrast is our indirect check ⟨pending⟩.
- **Ethics and licensing:** photos with NC/ND/GFDL-only/unknown licences are excluded; every image row carries
  author, licence, source URL and the modification made. Takedown via the dataset's discussion page.

## Evaluation

### Method
- **Labels:** SimpleQA three-way. *Hallucination rate* = incorrect / attempted.
- **Graders:** (1) a deterministic code grader on 100 % (alias matching with the distinctiveness and ambiguity
  rules, abstention and hedge detection in all four languages, a gazetteer of all Swiss cantons and current and
  former municipalities); (2) an independent open-weights judge, `openai/gpt-oss-120b` (not Apertus), on 100 %,
  prompt tuned on a 40-item dev set and frozen before the human audit ⟨pending⟩; final label = judge's.
- **Statistics:** cluster bootstrap over landmarks (2,000 resamples) for CIs; exact McNemar for paired
  contrasts; Holm correction across the registered tests; Wilson intervals for rates.

### Evaluation setup and inference parameters
Temperature 0, top_p 1, max_tokens 300, seed 1234, one image (base64 JPEG) + one question, no system prompt.
Every response is stored with a content hash of its request; `verify` replays the stored answers.
**Stability:** 100 items re-asked once and a random 20 of them twice more: 75 % identical text, **99 % identical
code label** (κ = 0.98; the one change is a vague hedge reworded into another vague hedge), and all 20 probe items
kept their label over four answers: the endpoint is not bit-for-bit deterministic, but the grades are stable.

### Results ⟨code⟩

**1. Recognition from a photo almost never succeeds, and committed answers are almost always wrong.**

| photo_main (n per cell = 264) | FR | IT | DE | RM |
|---|---|---|---|---|
| Name: declines ("not sure") | 90 % | 75 % | 51 % | **27 %** |
| Name: confidently wrong | 10 % | 25 % | 49 % | **72 %** |
| Place: confidently wrong | 2 % | 2 % | 31 % | **97 %** |

Overall, name correct 0.2 %, place correct 1.1 %, year never answered (0 of 272). Among committed name answers
99.5 % are wrong. The same instruction ("if you are not sure, say so") produces honest refusals in French and
confident fabrication in Romansh, on identical images.

**2. In Romansh the model moves landmarks to Graubünden** (exploratory, location extracted with the gazetteer).
Of 200 landmarks outside Graubünden, the Romansh answer places **98** in Graubünden; the French and Italian
answers for the same photos place none there and the German answers 14 (paired McNemar RM vs FR/IT/DE,
p < 10⁻⁶). Overall 59 % of Romansh place answers say Graubünden (true share 24 %). The municipalities named are
mostly German- and Italian-speaking Graubünden towns (Chur, Davos, Poschiavo): the pull is toward the canton
associated with Romansh rather than toward Romansh-speaking villages. The 8B model shows the same pull (28 %).

**3. Famous names absorb unknown objects.** Twelve different landmarks, mostly castles and towers, are called "Castel Tarasp" (the
iconic Engadine castle), nine Swiss landmarks become "Castle Vaduz" (Liechtenstein), and castles in French and Italian
answers become "Château de Chillon". Disentis Abbey becomes "Kloster Einsiedeln".

**4. Registered hypotheses** (Holm-adjusted):

| | Result ⟨code⟩ |
|---|---|
| H1 fame cliff (name) | not supported: hallucination 100 % (low) vs 99.3 % (high); floor effect |
| H1b fame cliff (place) | not supported (Δ = +1.3 pp, CI −3.7 to +6.0) |
| H2 majority-region pull | not supported: wrong towns for non-DE landmarks are 60 % German-speaking vs 65 % of all municipalities (registered comparison points the other way, p_Holm = 0.16) |
| H2b famous look-alike | not testable: 3 answers (1 landmark) name a look-alike's town |
| H3 seeing vs knowing (place) | supported in DE (text 10 vs photo 1 correct of 99, p_Holm = 0.02); FR same direction (8 vs 1, p_Holm = 0.12) |
| H4 false premise | **supported**: 76 % adopt the false town vs 38 % incorrect on the same photo asked plainly (p_Holm = 0.0001) |

Knowing the name helps, and fame matters there: text-only place accuracy is 13.6 % for high-fame vs 3.7 % for
low-fame landmarks, while from the photo both are ≈ 0 %. The bottleneck is visual recognition.

**5. Smaller model.** Apertus 1.5 8B declines far less (name: 18 % not attempted vs 60 % for 70B) and is
confidently wrong in every language (name wrong: FR 84 %, IT 62 %, DE 78 %, RM 98 %); for 8B the fame effect
on place questions is significant (H1b, p_Holm = 0.04), as a secondary result. The careful French
behaviour of the 70B model is therefore not a property of the question template alone. ⟨code⟩

**6. Agreement.** Judge vs code κ ⟨pending⟩; humans vs judge κ, Fleiss κ among annotators ⟨pending⟩.

## Dataset Limitations
- Results are for one prompt template per language; Romansh templates were not reviewed by a native speaker
  (exploratory). The language effect could partly reflect template wording; a no-abstention-cue variant is
  future work.
- Gold comes from Wikidata; errors there propagate (mitigated by the audit and the human spot check ⟨pending⟩).
- Fame is proxied by Wikipedia article counts. Low accuracy everywhere limits the power of fame contrasts (floor).
- The code grader cannot judge vagueness perfectly; it is a second rater, the judge is primary.
- Post-run corrections to the code grader and item validity were made after seeing answers; each is
  documented with its effect in `CHANGELOG.md` and pinned by regression tests.

## Lessons Learnt and Recommendations
- For Apertus: abstention behaviour is language-dependent; calibration training should include Romansh and
  German, where the model guesses most. Visual recognition of Swiss heritage is the weakest link; grounding with
  retrieval (e.g. KGS/Wikidata lookup from GPS or image search) would help more than more text knowledge.
- For evaluators: score abstention separately from accuracy and compare languages on identical images; check
  hedged answers ("not sure, but it seems to be a church") — they are abstentions, not errors.

## Reproducibility
`make run` (Docker) on a clean checkout: builds the image, downloads the pinned dataset revision from Hugging
Face, runs `verify` (schema, image hashes, coverage, re-grading reproduces every stored label, final-label rule,
recomputed scores equal the expected scores), and, if `LLM_*` is set, evaluates that model on a stratified
sample (`FULL=1` for all items). Hardware: any CPU; runtime ≈ 1 min for verification, under an hour for a
full 70B run at 4 parallel requests. Seeds: selection 20261013, sampling 7, bootstrap 20261015, stability 20261016,
audit 20261017. Exact commit and dataset revision: ⟨on submission⟩.

## License
Code: Apache-2.0. Dataset: CDLA-Permissive-2.0 (photos under their own CC licences, listed per item).
Report: CC-BY-4.0.

## References
SimpleQA (Wei et al., 2024); Wikidata; Swiss Inventory of Cultural Property of National and Regional
Significance (KGS); BFS Swiss official commune register; Apertus technical report (Swiss AI Initiative, 2025).
