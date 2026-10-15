# Technical report — Swiss Heritage Factuality: does Apertus recognise Switzerland's landmarks?

> Final labels are the frozen LLM judge's (`judge-v1`), checked by a blind human audit of the 20 % sample (one
> annotator; judge–human κ = 0.76). Photos were screened by AI (see Annotation and Limitations).

> We built a four-language (FR/DE/IT/RM) benchmark of 5,420 questions about 251 Swiss heritage landmarks from the
> federal inventory (KGS), stratified by language region and fame, with photo, second-view, multiple-choice,
> text-only and trap variants and per-item licences. Apertus 1.5 70B almost never recognises a landmark from its
> photo: given four named options it is right only 35 % of the time (chance 25 %; the open model Gemma-4-31B:
> 61 %), about equally in all four languages. What the language changes is whether it admits it: on the same photos
> it mostly declines in French (11 % of names confidently wrong) but answers in Romansh (68 % of names and
> 97 % of places wrong), where it also relocates half of all non-Graubünden landmarks to Graubünden, a pull
> Gemma shares. Shown a photo too generic to identify, it declines every time; Gemma invents a name for a quarter.

**Track:** Apertus Readiness - Track 1B (Swiss Voices), dimension: core-task intelligence (factuality)  
**Event:** Online  
**Team:** Red Pandas — Christopher Yazigi, Giovanni Yazbeck, Alfredo Pio Yazbeck  
**Demo / data:** dataset `huggingface.co/datasets/chrizzto/swiss-heritage-factuality` ·
code `github.com/ChristoYusj/apertus-swiss-landmarks`

----

### Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B` (main), `swiss-ai/Apertus-v1.5-8B` (secondary); comparison model
  `google/gemma-4-31B-it` (open weights, via the Hugging Face router) on the same items
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
| Landmarks | 251 KGS heritage objects (A: 104, B: 139, local: 8) in 4 BFS language regions × 3 fame tiers (264 drawn; 13 removed by the photo screening) |
| Fame tiers | Wikipedia articles: low 0, mid 1–2, high ≥ 3 (21–24 per cell; Romansh region: smaller pools, 12–18, the high-fame cell a census) |
| Types | churches 108, castles 61, museums 30, civic 18, bridges 14, fountains 10, towers/gates 8, monuments 2 |
| Photos | 251 main photos (Wikidata P18), 161 second views, 17 low-information photos; 500 px, EXIF stripped, per-image licence |
| Questions | 5,420: core 3,412 (`photo_main` 2,276, each photo in 4 languages; `photo_alt` 732; `text_only` 322; `trap_premise` 48; `trap_lowinfo` 34) + registered extensions 2,008 (`photo_mc` 1,004; `photo_main_w2` 1,004) |
| Question types | Q1 name, Q2 municipality + canton, Q3 year built (67 landmarks with a precise, unconflicted year) |
| Languages | French, German, Italian, Romansh (Rumantsch Grischun); identical templates, explicit "if unsure, say so" |
| Answer keys | Wikidata (CC0) + BFS municipality register: name aliases (flagged if only valid with the town), current/former municipality names, canton names in 5 languages, year windows |
| Licences | questions/keys/responses CDLA-Permissive-2.0; photos keep their CC licence (TASL attribution per item) |

**Arms.** `photo_main`: the photo, asked in all four languages (same image → language is the only change).
`text_only`: the landmark's name is given and the place or year is asked (FR, DE), separating *recognition*
from *knowledge*. `trap_premise`: the question asserts the town of a real look-alike in another municipality
("This building is in Rothrist. Which building is it?"). `photo_alt` (FR, DE): a second view of the same object,
a memorisation hint. `trap_lowinfo` (FR, DE): a photo too generic to identify; declining is right.
Extensions, registered before they were run (`docs/extensions_plan.md`): `photo_mc`, the main photo with four
named options (the landmark and three others, of the same type and mostly the same region; chance 25 %), in all four
languages; `photo_main_w2` (FR, RM), the name and place questions with a second, independent wording.

**Selection funnel** (seed 20261013): 13,417 heritage objects with a photo → 4,153 eligible (public landmark
types, a current municipality, a specific label, one language region) → stratified sample of 264 + 83
same-cell reserves for replacements.

## Data Collection Method

**Sources.** Wikidata (QLever mirror, cached queries in the repository) for objects, names, inception dates and
administrative location; the Federal Statistical Office municipality register (01-10-2026) for municipality
numbers, cantons and language regions; Wikimedia Commons for photos and their licences.

**Answer keys** (rules in code, decisions in `CHANGELOG.md`). Names: Wikidata labels, aliases and sitelinks in
six languages, without town-only or type-only aliases; a name is *non-distinctive* if nothing is left after
removing type words, saints and the town ("Kapelle St. Antonius"), and then counts only with the right town.
Places: the current municipality's names in all languages (16 district/region/former-municipality labels removed);
shared town names need the canton. Years: unconflicted year- or decade-precision inception (window ±5), never a
museum's founding date. An independent script re-checked 25 random landmarks against live Wikidata (25/25).

**Question validity rules** (from the question text only): text-only questions are dropped when the shown name
is not distinctive or contains the town or a year; 170 items, kept with their answers in
`metadata/excluded_items.jsonl`.

**Annotation** (`docs/annotation_guidelines.md`; deviations from the plan are logged in `CHANGELOG.md`).

- *Photo screening, by AI (deviation: the plan had the team screen).* Exclude recognisable people, readable plates,
  private interiors and personal text (never blur); drop a main photo that does not show the object; pick a second
  view; mark too-generic photos. Claude Opus 5.5 screened all 917 candidates, three further instances re-checked
  the 491 proposed for shipping, and a second AI agent (Hermes) reviewed them under the lead's "if unsure,
  exclude" policy; the lead decided 6 edge cases. 13 landmarks were removed (privacy 4, wrong object 4, unclear 5;
  answers kept in `metadata/excluded_items.jsonl`), 429 photos shipped. ⟨P1⟩
- *Grading audit (human, blind):* the pre-registered, seeded, stratified 20 % sample (546 of the 2,726 70B answers
  before the screening; 522 still in the dataset; the later `photo_alt`/`trap_lowinfo` items are not covered) was
  graded by one annotator (A1, the team lead) on three fillable PDFs that show no grade of any kind, with an English
  machine gloss for non-French answers. The protocol planned three annotators; A1 graded all three parts, so no
  agreement between people is reported. A second AI agent graded the same sample as a separate cross-check.

**Consent and personal data.** No person is a data subject: photos with recognisable people are excluded,
EXIF is stripped. Annotators sign the consent form in `docs/consent_form_template.md` (pseudonymous IDs).

## Dataset Details

- **Quality metrics:** answer-key audit (above), selection funnel, per-cell counts, item-validity rules,
  stability of answers at temperature 0 (below), judge–code agreement and an independent re-read of every
  disagreement (AI-assisted), a blind human audit of the 20 % sample (one annotator) and an AI cross-check.
- **Diversity / edge cases:** four languages incl. Romansh; fame tiers; same-photo language contrast; text vs
  photo; false-premise traps with real look-alikes; low-information photos; ambiguous town names;
  non-distinctive names.
- **Contamination:** the Apertus pre-training data list contains no Wikimedia/landmark image set by name, but
  includes web-scale image–text corpora that may contain some of these photos; URL-level checks are infeasible
  for us (limitation). The `photo_main` vs `photo_alt` contrast is our indirect check: no advantage for the
  main photos (Results 4).
- **Ethics and licensing:** photos with NC/ND/GFDL-only/unknown licences are excluded; every image row carries
  author, licence, source URL and the modification made. Takedown via the dataset's discussion page.

## Evaluation

### Method
- **Labels:** SimpleQA three-way. *Hallucination rate* = incorrect / attempted.
- **Graders:** (1) a deterministic code grader on 100 % (alias matching with the distinctiveness and ambiguity
  rules, abstention and hedge detection in all four languages, a gazetteer of all Swiss cantons and current and
  former municipalities); (2) an independent open-weights judge, `openai/gpt-oss-120b` (not Apertus), on 100 %,
  pinned to one provider, temperature 0; prompt tuned on a 40-item dev set (labels proposed by Claude; the lead
  ruled on the 4 hard cases and accepted the other 36 without item-by-item review)
  (final prompt: 40/40 agreement, two runs identical) and frozen before the full run and the audit sample;
  final label = judge's. Multiple choice is graded by code only (one option named by letter or text).
- **Statistics:** cluster bootstrap over landmarks (2,000 resamples) for CIs; exact McNemar for paired
  contrasts; Holm correction across the registered tests; Wilson intervals for rates.

### Evaluation setup and inference parameters
Temperature 0, top_p 1, max_tokens 300, seed 1234, one image (base64 JPEG) + one question, no system prompt.
Every response is stored with a content hash of its request; `verify` replays the stored answers.
**Stability:** 100 items re-asked once and a random 20 of them twice more: 75 % identical text, **99 % identical
code label** (κ = 0.98; the one change is a vague hedge that, asked again, named two candidate cantons), and all 20 probe items
kept their label over four answers: the endpoint is not bit-for-bit deterministic, but the grades are stable.

### Results

**1. The question's language decides whether the model answers, not what it recognises.**

| photo_main, Apertus 70B (n per cell = 251) | FR | IT | DE | RM |
|---|---|---|---|---|
| Name: not attempted (declines, or too vague to check) | 89 % | 76 % | 58 % | **32 %** |
| Name: confidently wrong | 11 % | 24 % | 41 % | **68 %** |
| Place: confidently wrong | 2 % | 2 % | 30 % | **97 %** |

Only 4 of 1,004 names and 6 of 1,004 places are right; 360 of 364 committed names are wrong. The same instruction
("if you are not sure, say so") gives honest refusals in French and confident fabrication in Romansh, on identical
images. **With four named options** (`photo_mc`) the language gap disappears: 70B picks the right landmark in
32–39 % in every language (34.7 % overall, 95 % CI 29.7–39.7 resampling landmarks; chance 25 %), 8B in 31–33 %.
Part of the margin over chance is a position bias (70B starts with "A" in 58 % of answers; 74 % correct when the
answer is A, about 22 % otherwise, still above the ~14 % a pure "A" bias would give). So recognition is weak in every language; the
language changes whether the model admits it. **A second, independent wording** (`photo_main_w2`, registered
before the run for 70B, also run on 8B and Gemma) keeps the gap: Romansh names 93 % wrong vs French 20 % (70B); the 8B model is very sensitive to
wording (French names wrong 78 % → 32 %) but Romansh stays its worst language (79 %). The comparison model, Gemma-4-31B, has no such gap: it rarely declines (names not attempted 5–10 %), gives a
wrong name in 86–94 % of answers in every language, and with four options is right 61 % of the time (95 % CI
55.8–66.4; 61–63 % in every language). It recognises far more than Apertus but does not say when it does not
know; the language-dependent caution is an Apertus trait (both sizes, strongest in 70B).

![Free answer (left) vs multiple choice (right), same photos, by question language and model.](docs/figures/fig4_models.png){width=100%}

**2. In Romansh the model moves landmarks to Graubünden** (exploratory, location extracted with the gazetteer).
Of 190 landmarks outside Graubünden, the Romansh answer places **96** in Graubünden; the French and Italian
answers for the same photos place none there and the German answers 14 (paired McNemar RM vs FR/IT/DE,
p < 10⁻⁶). Overall 60 % of Romansh place answers say Graubünden (true share 24 %), mostly German- and
Italian-speaking towns (93 of 137 named; e.g. Chur, Roveredo, Poschiavo): the pull is toward the canton
associated with Romansh, not toward Romansh-speaking villages. The 8B model shows the same pull, weaker (35 %).
Gemma shows the same pull (58 % of its Romansh place answers say Graubünden; 95 of the 190 non-Graubünden
landmarks), so this is a cross-model association of Romansh with Graubünden, not an Apertus quirk.

**3. Famous names absorb unknown objects.** Eleven different landmarks, mostly castles, are called "Castel
Tarasp" (the iconic Engadine castle), eight become "Castle Vaduz" (Liechtenstein), and castles in French and
Italian answers become "Château de Chillon". Disentis Abbey becomes "Kloster Einsiedeln".

**4. A second view and an uninformative photo** (descriptive, FR + DE). On the 161 landmarks with a second view,
70B names 2 landmarks correctly from the main photo and 1 other (in both languages) from the second view, and is
wrong about as often (names 24 % vs 26 %; places 11 % vs 16 %, McNemar p = 0.04): no advantage for the Wikidata
main photos, so no sign that they were memorised. On 17 photos too generic to identify, 70B declined all 34
times and 8B 33 of 34, although on the main photos of the same landmarks they gave wrong names 7 and 26 times: the
models can tell an uninformative image from a recognisable one, but a photo that *looks* identifiable triggers
a confident guess.

**5. Registered hypotheses** (Holm-adjusted):

| | Result |
|---|---|
| H1 fame cliff (name) | not supported: hallucination 97.5 % (low) vs 99.2 % (high); floor effect |
| H1b fame cliff (place) | not supported (Δ = +2.3 pp, CI −1.0 to +6.4) |
| H2 majority-region pull | not supported: wrong towns for non-DE landmarks are 59 % German-speaking vs 65 % of all municipalities (registered comparison points the other way, p_Holm = 0.10) |
| H2b famous look-alike | not testable: 3 answers (1 landmark) name a look-alike's town |
| H3 seeing vs knowing (place) | **supported in French** (text 8 vs photo 0 correct of 95 landmarks, p_Holm = 0.04), same direction in German (9 vs 1, p_Holm = 0.09). Fragile: before the photo screening removed 13 landmarks, French was 8 vs 1 (p_Holm = 0.13) |
| H4 false premise | **supported**: 79 % adopt the false town vs 29 % incorrect on the same photo asked plainly (p_Holm < 0.0001); counting a wrongly named building as incorrect too (team rule), 88 % |

Knowing the name helps, and fame matters there: text-only place accuracy is 12.5 % for high-fame vs 3.7 % for
low-fame landmarks, while from the photo both are ≈ 0 %. The bottleneck is visual recognition.

![Left: municipality correct with the name given vs from the photo, by fame (H3). Right: incorrect on the plain photo question vs with a false town in the question (H4).](docs/figures/fig3_know_vs_see.png){width=100%}

**6. Smaller model and comparison model.** Apertus 1.5 8B declines less (name: 28 % not attempted vs 64 % for
70B) and is confidently wrong more often in every language (name wrong: FR 78 %, IT 48 %, DE 70 %, RM 90 %); it
is not more misled by the false premise than by the plain question (71 % vs 83 %, n.s.) because it is already
wrong on the plain question. Gemma-4-31B answers almost everything (names not attempted 9 %) and is wrong in 89 %; it names 26 of 1,004
landmarks correctly (Apertus 70B: 4) and is the only model with a significant fame effect (H1: 99.7 % vs 93.2 %
hallucination, low vs high fame; H1b likewise; p_Holm 0.01–0.02). It invents a name for 24 % of the too-generic
photos (Apertus 70B: 0 %) and adopts the false town in 69 % of premise traps.

**7. Agreement and judge errors.** Judge vs code grader on the 3,412 core items: κ = 0.95 (70B; 97.9 % identical
labels), 0.94 (8B; 96.8 %), 0.92 (Gemma; 97.2 %). Every core disagreement of the Apertus models (236 re-reads over
two rounds, 224 still in the dataset;
`disagreement_adjudication.jsonl`) was re-read independently against the written rules, with a second blind read
where the judge looked wrong (AI-assisted, not a human audit): of the 224, the judge was right in 86, the code
grader in 131, neither in 1, and 6 stayed unsettled. The judge is too strict on vague answers whose building type
fits the landmark and on saint names without a town, and leaves vague centuries outside the year window as not
attempted. Replacing its label wherever the re-read settled it lowers the Romansh name-wrong rate from 68 % to
59 % (70B; 8B 90 % → 81 %), raises the small Romansh year cell by 6 pp and lowers the premise-trap rate from 88 %
to 83 %; no other 70B language × question cell moves by more than about 1.5 pp. The registered results keep the
frozen judge's labels. *Human audit* (blind, one annotator, 522 answers): judge vs human κ = 0.76 (89 % identical),
code grader vs human κ = 0.73 (88 %). Most disagreements are answers the judge counted as declines that the
annotator marked incorrect (29) and answers the annotator marked correct that the judge did not (18); the 30
answers that appear in all three parts got the same label each time. *AI cross-check:* a second AI agent graded
the same sample: κ = 0.96
with the judge (98.2 % identical), 0.99 with the code grader.

## Dataset Limitations
- Results are for one prompt template per language; Romansh templates were not reviewed by a native speaker
  (exploratory). The language effect could partly reflect template wording; a no-abstention-cue variant is
  future work.
- Gold comes from Wikidata; errors there propagate (mitigated by the rule-based checks, the 25-landmark live
  re-check and the AI-assisted re-reading of every grader disagreement against the gold). The photo screening also found one
  Wikidata main photo of the wrong building (removed).
- Fame is proxied by Wikipedia article counts. Low accuracy everywhere limits the power of fame contrasts (floor).
- Neither automatic grader is perfect. The frozen judge is too strict on vague answers that fit the landmark
  (see Agreement). The code grader (second rater) misses fine-grained contradictions: Romansh "house of X"
  phrases, a denomination the gold does not state, name-shaped phrases built from common nouns ("Tour de
  l'Horloge" for another tower), and descriptive museum names.
- Post-run corrections to the code grader and item validity were made after seeing answers; each is
  documented with its effect in `CHANGELOG.md` and pinned by regression tests. One independent review read every
  answer the code grader marked incorrect and moved 109 (70B) and 356 (8B) labels, mostly refusals
  phrased in ways the patterns did not know; a third read 831 labels and its fixes moved 14 (70B) and 29 (8B)
  more (every changed label was read individually; these reviews were AI-assisted, not a human audit).
- The human audit has one annotator, so agreement between people cannot be reported; the annotator's labels depart
  from the written rules in places (declines marked incorrect), which lowers the judge–human agreement.
- The photo screening was done by AI (two systems) with the team lead deciding edge cases; no person reviewed every
  shipped photo. It removed 13 landmarks; 3 of the 4 removed for privacy were busy town-centre scenes, which are
  also among the easiest to recognise, so the removal took away 3 of the 70B's 9 correct place answers from photos
  (see H3).

## Lessons Learnt and Recommendations
- For Apertus: its visual knowledge of Swiss landmarks lags a comparable open model (multiple choice 35 % vs
  61 % for Gemma-4-31B); its strength is calibration, declining instead of guessing in French and Italian, and
  Romansh breaks it. Calibration training should include Romansh and German, and recognisable-looking but
  unknown objects; retrieval (e.g. a KGS/Wikidata lookup) would help recognition more than more text.
- For evaluators: score abstention separately from accuracy and compare languages on identical images; check
  hedged answers ("not sure, but it seems to be a church") — they are abstentions, not errors.

## Reproducibility
`make run` (Docker) on a clean checkout: builds the image, downloads the pinned dataset revision from Hugging
Face, runs `verify` (schema, image hashes, coverage, re-grading reproduces every stored label, final-label rule,
recomputed scores equal the expected scores), and, if `LLM_*` is set, evaluates that model on a stratified
sample (`FULL=1` for all items). Hardware: any CPU; runtime ≈ 1 min for verification, under an hour for a
full 70B run at 4 parallel requests. Seeds: selection 20261013, sampling 7, bootstrap 20261015, stability 20261016,
audit 20261017. Dataset revision `26d86b35d1a6` (pinned in `config.json`); code: the `main` branch, tag `submission`.

## License
Code: Apache-2.0. Dataset: CDLA-Permissive-2.0 (photos under their own CC licences, listed per item).
Report: CC-BY-4.0.

## References
SimpleQA (Wei et al., 2024); Wikidata; Swiss Inventory of Cultural Property of National and Regional
Significance (KGS); BFS Swiss official commune register; Apertus technical report (Swiss AI Initiative, 2025).
