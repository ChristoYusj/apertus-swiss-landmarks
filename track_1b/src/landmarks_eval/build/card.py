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
    uncleared = [i["image_id"] for i in imgs if i.get("pii_decision") != "keep"]
    if uncleared and not extra.get("allow_unscreened_draft"):
        # the card states that every shipped photo was screened: never write it before that is true
        raise SystemExit(f"photo screening incomplete: {len(uncleared)} shipped photos not cleared (e.g. {uncleared[:3]})")
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
    # every claim about grading and annotation below is derived from the files actually present (never assumed)
    rdirs = sorted(p for p in (ds / "responses").glob("*") if (p / "responses.jsonl").exists()) if (ds / "responses").exists() else []
    models = [_load(p / "responses.jsonl")[0]["model"] for p in rdirs]
    ref = ds / "responses" / "apertus-v1.5-70b"
    judg = _load(ref / "judgements.jsonl") if (ref / "judgements.jsonl").exists() else []
    judge_done = bool(judg) and all(j.get("judge_label") for j in judg)
    audit = _load(ref / "human_audit.jsonl") if (ref / "human_audit.jsonl").exists() else []
    gloss = (ref / "glosses.jsonl").exists()
    stab = json.loads((ref / "stability.json").read_text(encoding="utf-8")) if (ref / "stability.json").exists() else None
    gold_qc = extra.get("gold_qc")
    files_of = {p.name: sorted(f.name for f in p.iterdir() if f.is_file()) for p in rdirs}
    file_desc = {"responses.jsonl": "raw outputs with parameters, usage, latency and request hashes",
                 "judgements.jsonl": "code-grader label and rule" + (", LLM-judge label" if judge_done else "") + ", final label",
                 "scores.json": "all scores recomputed by `landmarks-eval score`",
                 "stability.json": "temperature-0 stability check", "stability_responses.jsonl": "the re-asked answers",
                 "human_audit.jsonl": "blind human labels (annotator A1)",
                 "human_audit_repeat.jsonl": "the annotator's second labels of the hidden repeat items (self-consistency)",
                 "audit_sample.json": "the seeded, stratified audit sample (item ids, strata, hidden repeats)",
                 "ai_crosscheck_audit.jsonl": "the audit sample graded by a second AI system: a cross-check, not a human audit",
                 "disagreement_adjudication.jsonl": "AI-assisted re-reading of every judge-vs-code disagreement (sensitivity analysis)",
                 "judge_dev_set.jsonl": "judge tuning items and labels", "judge_dev_eval.json": "the frozen judge on its dev set",
                 "glosses.jsonl": "English machine glosses of answers (annotation aid)"}
    responses_block = "\n".join(
        f"- `responses/{name}/`:\n" + "\n".join(f"  - `{f}`: {file_desc.get(f, '')}".rstrip(": ") for f in fs
                                             if not f.endswith(".recomputed.json"))
        for name, fs in files_of.items())
    meta_desc = {"excluded_items.jsonl": "questions removed by documented rules, with their answers and the reason",
                 "excluded_landmarks.jsonl": "answer keys of landmarks removed in the photo screening",
                 "removed_place_aliases.jsonl": "place labels removed from the answer keys (district, region or former municipality)",
                 "gazetteer.json": "Swiss cantons, current and former municipalities and countries (location analysis)",
                 "review.json": "photo-screening summary (protocol, counts, dropped landmarks and reasons)"}
    meta_block = "\n".join(f"- `metadata/{f}`: {d}" for f, d in meta_desc.items() if (ds / "metadata" / f).exists())
    arm_desc = {"photo_main": "Wikidata main photo.",
                "text_only": "the object's name is given; the question asks where it is or when it was built.",
                "photo_alt": "a second view of the same object, accepted in the photo screening.",
                "trap_premise": "the question falsely states the town of a real look-alike.",
                "trap_lowinfo": "a photo too generic to identify; abstaining is correct.",
                "photo_mc": "the main photo with four named options (the landmark and three similar ones); graded by code.",
                "photo_main_w2": "the main photo, name and place asked with a second wording (French, Romansh)."}
    present_arms = {c["arm"] for c in cases}
    arms_block = "\n".join(f"- `{a}`: {d}" for a, d in arm_desc.items() if a in present_arms)
    goldqc_line = f"- **Answer-key spot check:** {gold_qc}." if gold_qc else ""
    grading_block = (
        "  - Every model answer was graded by a deterministic code grader and by an independent open-weights LLM judge "
        "(`openai/gpt-oss-120b`, temperature 0); the final label is the judge's.\n"
        "  - The judge prompt was tuned on a 40-item dev set (labels proposed by Claude; the team lead ruled on the 4 "
        "hard cases and accepted the other 36 without item-by-item review) and frozen before the audit sample was drawn."
        if judge_done else
        "  - Every model answer was graded by a deterministic code grader (rules in the repository, each post-run change "
        "documented in the CHANGELOG). LLM-judge labels are not part of this version; final label = code-grader label.")
    ai_check = _load(ref / "ai_crosscheck_audit.jsonl") if (ref / "ai_crosscheck_audit.jsonl").exists() else []
    repeats = _load(ref / "human_audit_repeat.jsonl") if (ref / "human_audit_repeat.jsonl").exists() else []
    ai_line = (f"\n- **AI cross-check (not a human audit):** a second AI system "
               f"({', '.join(sorted({a['annotator_id'] for a in ai_check}))}) graded the same sample "
               f"({sum(1 for a in ai_check if a.get('label'))} of {len(ai_check)} items; the rest were left unscored as "
               "uncertain); its agreement with the judge and the code grader is in `scores.json`." if ai_check else "")
    if audit:
        n_items = len({a["item_id"] for a in audit})
        who = sorted({a["annotator_id"] for a in audit})
        n_overlap = len({a["item_id"] for a in audit if a.get("in_overlap")})
        audit_block = (f"- **Human audit:** {n_items} answers of a seeded, stratified random sample were labelled blind by "
                       + (f"{len(who)} annotators ({', '.join(who)}), each alone" if len(who) > 1 else f"one annotator ({who[0]})")
                       + " following `docs/annotation_guidelines.md`"
                       + (f"; {n_overlap} items were labelled by all of them" if len(who) > 1 and n_overlap else "")
                       + (f"; {len(repeats)} items were shown a second time, unannounced, to measure self-consistency"
                          if repeats else "")
                       + ".\n- **Agreement:** judge-human and code-human agreement (Cohen's kappa)"
                       + (" and agreement between the annotators (Fleiss' kappa)" if len(who) > 1 and n_overlap else "")
                       + (" and the annotator's self-consistency" if repeats else "")
                       + " are in `scores.json` and the technical report." + ai_line)
        annot_details = ((f"{len(who)} student members of Team Red Pandas (pseudonyms {', '.join(who)}), French and English speakers."
                          if len(who) > 1 else f"One student member of Team Red Pandas (pseudonym {who[0]}), French and English speaker.")
                         + (" Non-French answers were shown with a labelled English machine gloss." if gloss else ""))
    else:
        audit_block = "- **Human audit:** not part of this version." + ai_line
        annot_details = "No human grading labels are published in this version; *Privacy screening* says who screened the photos."
    proto = review.get("guideline_version")
    revs = review.get("reviewers") or []
    if proto == "v3b-ai-review" and revs == ["ai:claude-opus-5-5", "ai:hermes"]:
        screening_lines = (
            "  - Every candidate photo was screened by an AI (Claude Opus 5.5); three further Claude instances re-checked "
            "every photo to be shipped, and a second AI agent (Hermes) reviewed them again under the team lead's "
            "\"if unsure, exclude\" policy.\n"
            f"  - The team lead decided the edge cases of {review.get('stats', {}).get('landmarks_with_human_decision', 0)} "
            "landmarks directly. No person reviewed every shipped photo.")
    elif proto == "v3-ai-assisted" and "A1" in revs:
        screening_lines = ("  - Every candidate photo was screened by an AI (Claude Opus 5.5) and re-checked by further "
                           "Claude instances; annotator A1 then checked every shipped photo.")
    elif proto == "v2-team":
        screening_lines = ("  - Every shipped photo was then reviewed by the team, jointly, one decision per landmark "
                           "(guideline v2-team).")
    elif extra.get("allow_unscreened_draft"):
        screening_lines = "  - Screening provenance: see `metadata/review.json` (draft card)."
    else:  # never guess who screened the photos
        raise SystemExit(f"unknown screening protocol {proto!r} / reviewers {revs}: cannot describe the screening")
    n_post = sum(1 for i in imgs if i.get("post_cutoff"))
    contam_line = ("The `photo_alt` arm (a second view of the same object) is the only, indirect image-side check"
                   + (f"; {n_post} shipped photos post-date 14 Jul 2026" if n_post else
                      "; no shipped photo was uploaded or taken after 14 Jul 2026, so a post-cutoff contrast was not possible")
                   + ". URL-level checks against web-scale image corpora were infeasible.")
    stab_line = (f" Re-asking 100 items gave {stab['identical_text_rate']:.0%} identical text and "
                 f"{stab['same_code_label_rate']:.0%} identical labels." if stab else "")
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
official BFS municipality register. The responses of {', '.join(f'`{m}`' for m in models) or 'the evaluated models'}
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
- Not an authoritative heritage register. Answer keys come from Wikidata, which can be wrong{'; we measured an error rate on a sample (see *Quality Control*)' if gold_qc else ''}.
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
  - expected behaviour and traps: `expected_behavior`, `trap_type`, `false_premise_claim`, `false_premise_aliases`, `paired_control_item_id`, `confusable_with`
- `data/landmarks.jsonl`: answer keys, one row per landmark. Fields:
  - names: labels in 5 languages and `name_aliases` (each flagged `distinctive`; saint/type-only names count only together with the town)
  - place: `place_aliases` (names of the current municipality in all languages; districts, regions and former municipalities removed, see `metadata/removed_place_aliases.jsonl`), `ambiguous_place_aliases` (need the canton), `canton_aliases`
  - year: `gold_year`, `year_window`, raw inception and its precision
  - inventory: KGS number, heritage class
  - design covariates: fame tier, language region, type, coordinates
- `images/`: {len(imgs)} JPEG files, 500 px wide.
- `metadata/images.jsonl`: per image the role (main Wikidata image or a second view), Commons title and URL, author, licence (SPDX), ready-to-use attribution text, modifications, hashes, upload/capture dates and the privacy review.
- `metadata/item_metadata.jsonl`: per test case, the licence of each modality, translation provenance and review status, and design covariates.
{meta_block}
{responses_block}

Test cases by arm and question type:

{_table(arms, ["arm", "question", "n"])}

{arms_block}

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
- **Questions:** fixed templates drafted with an AI coding assistant (Claude Code); French reviewed by French-speaking team members, German and Italian back-translation checked, Romansh not reviewed by a native speaker.
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
{screening_lines}
    Excluded photos and unpicked candidate views are not shipped.
  - Landmarks dropped in the screening: {len(review.get('dropped_landmarks', {}))} (main photo excluded for privacy, not showing the landmark, or excluded because that was unclear; reasons in `metadata/review.json`); their answers are kept in `metadata/excluded_items.jsonl`.
{goldqc_line}

#### Data Instance Licenses
- Questions, answer keys (derived from CC0 Wikidata facts), labels and model responses: **CDLA-Permissive-2.0**.
- Photos keep their own licence. Image licences: {', '.join(f'{k} ({v})' for k, v in sorted(lic.items()))}. NC, ND, GFDL-only and unlicensed files were excluded.
- Each image row carries a ready-to-use TASL attribution (title, author, source, licence) and its modifications. CC BY-SA images remain under CC BY-SA when reused.

### Annotations

#### Annotation Process
- **Grading:**
{grading_block}
{audit_block}

#### Annotator Details
{annot_details}

## Risks, Bias, and Limitations
- **Wikidata coverage:** coverage is uneven. The Romansh region has only 12 listed landmarks with 3+ Wikipedia articles (all included), and Italian and Romansh cells draw on smaller pools.
- **Romansh templates:** not native-reviewed (exploratory).
- **Inception dates:** these can refer to an earlier building on the same site. Answer-key errors are {'estimated on a sample, not eliminated' if gold_qc else 'reduced by rule-based checks, not eliminated'}.
- **Contamination:** famous objects and their Wikipedia text are likely in pre-training data. {contam_line}
- **Determinism:** model outputs at temperature 0 are not perfectly reproducible on shared GPU servers. Scores are verified by replaying the stored responses.{stab_line}

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
