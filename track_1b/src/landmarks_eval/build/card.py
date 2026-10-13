"""Write the Hugging Face dataset card (README.md) from the template sections + computed statistics."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = "https://github.com/ChristoYusj/apertus-swiss-landmarks"


def _load(p: Path):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def _table(rows: list[list], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def build_card(ds: Path, extra: dict | None = None) -> str:
    extra = extra or {}
    cases = _load(ds / "data" / "test_cases.jsonl")
    lms = _load(ds / "data" / "landmarks.jsonl")
    imgs = _load(ds / "metadata" / "images.jsonl")
    sel = json.loads((ds / "metadata" / "selection_report.json").read_text(encoding="utf-8")) if (ds / "metadata" / "selection_report.json").exists() else {}
    review = json.loads((ds / "metadata" / "review.json").read_text(encoding="utf-8")).get("report", {}) if (ds / "metadata" / "review.json").exists() else {}
    cell = Counter((l["language_region"], l["fame_tier"]) for l in lms)
    cells = [[r] + [cell[(r, t)] for t in ("high", "mid", "low")] for r in ("DE", "FR", "IT", "RM")]
    arm = Counter((c["arm"], c["question_type"]) for c in cases)
    arms = [[a, q, n] for (a, q), n in sorted(arm.items())]
    lang = Counter(c["lang"] for c in cases)
    lic = Counter(i["license_spdx"] for i in imgs)
    types = Counter(l["type_group"] for l in lms)
    funnel = sel.get("funnel", {})
    yaml_head = """---
license: cdla-permissive-2.0
language: [fr, de, it, rm]
pretty_name: Swiss Heritage Factuality (Apertus 1.5)
size_categories: [1K<n<10K]
task_categories: [visual-question-answering, question-answering]
tags: [switzerland, cultural-heritage, factuality, hallucination, evaluation, apertus, multilingual, hackapertus]
configs:
- config_name: test_cases
  data_files: data/test_cases.jsonl
- config_name: landmarks
  data_files: data/landmarks.jsonl
- config_name: item_metadata
  data_files: metadata/item_metadata.jsonl
- config_name: images
  data_files: metadata/images.jsonl
---
"""
    body = f"""# Dataset Card for Swiss Heritage Factuality

Does Apertus 1.5, Switzerland's open LLM, recognise Swiss heritage landmarks from a photo,
and does it say "I don't know" instead of inventing an answer? This dataset holds
**{len(cases):,} test questions** about **{len(lms)} landmarks** from the federal
inventory of protected cultural property (the KGS inventory). Each question asks
for the landmark's name, its municipality and canton, or its year of construction,
in French, German, Italian and Romansh. Every answer key cites Wikidata and the
official BFS municipality register. The responses of `swiss-ai/Apertus-v1.5-70B`
are included with their grades. It was built for Hack Apertus 2026, Track 1B
(Swiss Voices, core-task intelligence).

## Dataset Details

- **Curated by:** Team Red Pandas (Hack Apertus 2026 online hackathon)
- **Funded by:** none; inference was provided by CSCS through the hackathon endpoint
- **Shared by:** Team Red Pandas
- **Language(s) (NLP):** French, German (Swiss orthography), Italian, Romansh (Rumantsch Grischun)
- **License:** CDLA-Permissive-2.0 for the compilation, questions, answer keys, labels and model responses. Each photograph keeps its own free licence (see *Data Instance Licenses*).
- **Git repository:** {REPO}

## Uses

### Direct Use
- Measure factual accuracy and hallucination rates of vision-language models on Swiss cultural heritage, in Switzerland's national languages. The harness accepts any OpenAI-compatible model.
- Compare *recognising* a landmark (from a photo) with *knowing about* it (its name given in text).
- Test whether a model abstains when it cannot know (low-information photos) and whether it resists false premises in a question.

### Out-of-Scope Use
- Not an authoritative heritage register. Answer keys come from Wikidata, which can be wrong; we measured an error rate on a sample (see *Quality Control*).
- Do not use it to rank people or places, to train surveillance or person-identification systems, or as a guide to private property. Photos with recognisable people were excluded.
- Romansh results are exploratory: the Romansh question templates were not reviewed by a native speaker.

### Specifications
- **Domain:** objects of the Swiss Inventory of Cultural Property of National and Regional Significance (Wikidata P1435 classes A/B and cantonal/local significance) that are public landmark types: churches and monasteries, castles and castle ruins, bridges, fountains, towers and gates, town halls and stations, museums, monuments.
- **Strata:** official BFS language region of the municipality (SPRGEB2020) × fame tier. Fame is the number of Wikipedia articles about the object: low = 0, mid = 1–2, high = 3+.

{_table(cells, ["Region", "high (3+ articles)", "mid (1–2)", "low (0)"])}

- **Questions per landmark:** Q1 name; Q2 municipality + canton; Q3 year built (only when Wikidata has a single consistent year- or decade-precision inception; never for museums, whose inception is usually the founding of the institution).
- **Prompts:** every question explicitly allows the model to say it is unsure (prompt version `q-v1`).

## Dataset Structure

- `data/test_cases.jsonl`: the evaluation set, one row per question. Fields:
  - identity and question: `item_id`, `landmark_qid`, `arm`, `question_type`, `lang`, `template_id`, `prompt_version`, `question_text`, `image_id`
  - expected behaviour and traps: `expected_behavior`, `trap_type`, `false_premise_claim`, `false_premise_aliases`, `paired_control_item_id`, `confusable_with`, `split`
- `data/landmarks.jsonl`: answer keys, one row per landmark. Fields:
  - names: labels in 5 languages and `name_aliases` (each flagged `distinctive`; saint/type-only names count only together with the town)
  - place: `place_aliases` (current, former and merged municipality names), `ambiguous_place_aliases` (need the canton), `canton_aliases`
  - year: `gold_year`, `year_window`, raw inception and its precision
  - inventory: KGS number, heritage class
  - design covariates: fame tier, language region, type, coordinates
- `images/`: {len(imgs)} JPEG files, 500 px wide.
- `metadata/images.jsonl`: per image the role (main Wikidata image or a second view), Commons title and URL, author, licence (SPDX), ready-to-use attribution text, modifications, hashes, upload/capture dates and the privacy review.
- `metadata/item_metadata.jsonl`: per test case, the licence of each modality, translation provenance and review status, and design covariates.
- `responses/apertus-v1.5-70b/`:
  - `responses.jsonl`: raw model outputs with parameters, usage, latency and request hashes
  - `judgements.jsonl`: code-grader and LLM-judge labels and the final label
- `annotations/`:
  - human audit labels by annotators A1–A3
  - photo-screening decisions
  - answer-key check

Test cases by arm and question type:

{_table(arms, ["arm", "question", "n"])}

- `photo_main`: Wikidata main photo.
- `text_only`: the object's name is given; the question asks where it is or when it was built.
- `photo_alt`: a second, human-accepted view.
- `trap_premise`: the question falsely states the town of a real look-alike.
- `trap_lowinfo`: a photo too generic to identify; abstaining is correct.

Questions per language: {', '.join(f'{k}: {v}' for k, v in sorted(lang.items()))}.

## Dataset Creation

### Curation Rationale
Swiss heritage is a domain where a wrong but confident answer causes quiet harm. A
cataloguer files a photo under the wrong monument, or a visitor is told a Lausanne
fountain is in Bern. Hallucination is more likely for the many small regional
monuments than for famous ones, and possibly more likely outside the German-speaking
majority. Existing Swiss benchmarks test legal or administrative text. To our
knowledge, none tests visual recognition of Swiss heritage, abstention, or
susceptibility to false premises, and no audio or vision results have been published
for Apertus 1.5.

### Source Data

#### Data Collection
- **Selection:**
  - Candidates were pulled from Wikidata (via the QLever mirror, snapshot of 13 Oct 2026; frozen queries in the repository) and the BFS municipality register (typology export valid on 1 Oct 2026).
  - Funnel: {funnel.get('pulled', '?')} heritage objects with a photo → {funnel.get('eligible', '?')} eligible public landmarks with a specific name and a current municipality.
  - Exclusions: non-public types, villas and private houses, archaeological sites, collections and archives, generic labels.
  - Seeded random draw: seed {sel.get('seed', 20261013)}, 50 % soft cap per type.
- **Photos:**
  - Each object's main image (Wikidata P18) and up to three other views from its Commons category.
  - Licence-filtered, downscaled to 500 px, re-encoded without metadata.
  - Main photos that failed the licence filter were replaced by a reserve landmark from the same stratum (never silently).

#### Source Data Producers and Data Subjects
- **Photographs:** Wikimedia Commons contributors, credited per image.
- **Facts:** Wikidata editors and the Swiss Federal Statistical Office.
- **Questions:** written by the team.
- **Model responses:** Apertus 1.5 (CSCS endpoint).

No person is a data subject: photos showing recognisable people were excluded.

#### Ownership and Consent Management
- **Photos:** remain owned by their authors and are redistributed under their licences.
- **Team members:** signed the annotator consent form (`docs/consent_form_template.md`), which covers publication under CDLA-Permissive-2.0, use for AI, pseudonymity and withdrawal.
- **Takedown and corrections:** open a discussion on this dataset page. Requests are handled within 14 days in a new version.

#### Data Processing and Quality Control
- **Answer keys:**
  - Aliases that are only a town name or only type words were removed.
  - Saint- or type-only names are flagged as non-distinctive.
  - Town labels that are another municipality's or canton's name were dropped.
  - Conflicting or century-precision inception dates give no year question.
- **Independent checks:**
  - An independent script re-checked 25 random landmarks against live Wikidata (25/25 matched).
  - It also scanned all answer keys for hazards; the fixes are documented in the repository CHANGELOG.
- **Privacy screening:**
  - An OpenCV face detector pre-flagged {sum(i['faces_detected'] > 0 for i in imgs)} shipped photos.
  - 100 % of photos were then reviewed by humans. Excluded photos are not shipped.
  - Screening agreement (Fleiss' κ on the overlap set): {review.get('privacy_fleiss_kappa_overlap', 'reported in the technical report')}.
- **Answer-key spot check:** {extra.get('gold_qc', 'two annotators checked the answer keys of 30 random landmarks against Wikipedia and the KGS inventory; see the technical report')}.

#### Data Instance Licenses
- Questions, answer keys (derived from CC0 Wikidata facts), labels and model responses: **CDLA-Permissive-2.0**.
- Photos keep their own licence. Image licences: {', '.join(f'{k} ({v})' for k, v in sorted(lic.items()))}. NC, ND, GFDL-only and unlicensed files were excluded.
- Each image row carries a ready-to-use TASL attribution (title, author, source, licence) and its modifications. CC BY-SA images remain under CC BY-SA when reused.

### Annotations

#### Annotation Process
- **Grading:**
  - Every model answer was graded by a deterministic code grader and by an independent open-weights LLM judge (`openai/gpt-oss-120b`, prompt `judge-v1`, temperature 0).
  - The judge prompt was frozen after tuning on a 40-item dev set.
- **Human audit:**
  - A seeded, stratified random 20 % of answers was labelled blind by 3 team members following `docs/annotation_guidelines.md`.
  - 100 items were labelled by all three.
- **Agreement:** judge–human, code–human and inter-annotator agreement (Cohen's and Fleiss' κ) are reported in the technical report.

#### Annotator Details
Three student members of Team Red Pandas (pseudonyms A1–A3), French and English
speakers. Non-French answers were shown with a labelled English machine translation.

## Risks, Bias, and Limitations
- **Wikidata coverage:** coverage is uneven. The Romansh region has only 12 listed landmarks with 3+ Wikipedia articles (all included), and Italian and Romansh cells draw on smaller pools.
- **Romansh templates:** not native-reviewed (exploratory).
- **Inception dates:** these can refer to an earlier building on the same site. Answer-key errors are estimated on a sample, not eliminated.
- **Contamination:** famous objects and their Wikipedia text are likely in pre-training data. The `photo_alt` arm and post-July-2026 photos give only an indirect check, and URL-level checks against web-scale image corpora were infeasible.
- **Determinism:** model outputs at temperature 0 are not perfectly reproducible on shared GPU servers. We report stability rates and verify scores by replaying the stored responses.

### Personally Identifiable Information
No personal data. Photos were screened, and any with recognisable people, readable licence plates, private interiors or personal text were excluded. EXIF metadata, which can contain camera owner names and GPS positions, was stripped from every file.

### Sensitive Information
Some objects are religious buildings (churches, chapels, monasteries). The dataset records only their names, locations and construction dates, and makes no statement about beliefs.

### Recommendations
Report hallucination as incorrect ÷ attempted, alongside accuracy, and break results down by fame tier and language region. Treat Romansh results as exploratory. Re-check answer keys before using single items as ground truth.

## Citations

**BibTeX:**
```
@misc{{redpandas2026swissheritage,
  title  = {{Swiss Heritage Factuality: a multilingual photo benchmark for Apertus 1.5}},
  author = {{Team Red Pandas}},
  year   = {{2026}},
  note   = {{Hack Apertus 2026, Track 1B}},
  url    = {{{REPO}}}
}}
```

**APA:** Team Red Pandas. (2026). *Swiss Heritage Factuality: a multilingual photo benchmark for Apertus 1.5* [Data set]. Hack Apertus 2026. {REPO}

## Glossary
- **KGS inventory:** Swiss Inventory of Cultural Property of National and Regional Significance.
- **BFS SPRGEB2020:** the Federal Statistical Office's language-region typology of municipalities.
- **Hallucination rate:** incorrect ÷ (correct + incorrect).
- **SimpleQA grading:** correct / incorrect / not attempted.

## More Information
- Pre-registered analysis plan and changelog: see the Git repository.
- Type groups: {', '.join(f'{k} {v}' for k, v in sorted(types.items()))}.
- Canary GUID (do not train on this dataset): `hackapertus-swiss-heritage-7d1f3c2a-1b5e-4c9d-9e0a-6f2b8c4d1a73`

## Dataset Card Authors
Team Red Pandas

## Dataset Card Contact
Open a discussion on this dataset's Hugging Face page.
"""
    text = yaml_head + body
    assert "[More Information Needed]" not in text
    (ds / "README.md").write_text(text, encoding="utf-8")
    return text
