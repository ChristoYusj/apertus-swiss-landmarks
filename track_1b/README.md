# Swiss Heritage Factuality (Team Red Pandas)

Track 1B, core-task intelligence (factuality). Does Apertus 1.5 recognise Swiss heritage landmarks, and does it
say so when it does not?

- **5,210 questions** on **242 landmarks** of the Swiss inventory of cultural property (KGS), with **409 photos**,
  in French, German, Italian and Romansh.
  - Core, 3,274: `photo_main` 2,196, `photo_alt` 688 (second view), `text_only` 314 (name given),
    `trap_premise` 44 (false town in the question), `trap_lowinfo` 32 (photo too generic to identify).
  - Extensions, registered before they were run (`docs/extensions_plan.md`), 1,936: `photo_mc` 968 (four named
    options), `photo_main_w2` 968 (second wording).
- **Models:** Apertus 1.5 70B and 8B; Gemma-4-31B as a comparison.
- **Grading:** correct / incorrect / not attempted (SimpleQA). Final label: the frozen judge `openai/gpt-oss-120b`
  (prompt `judge-v1`) on free answers, code on multiple choice (4 empty Gemma verdicts keep the code label). A
  deterministic code grader grades every item as a second rater.

## Results (Apertus 1.5 70B)

- It rarely recognises a landmark from its photo. With four named options it is right 34 % of the time
  (chance 25 %; Gemma-4-31B: 60 %), about equally in all four languages.
- The question's language decides whether it admits this. On the same photos it mostly declines in French
  (11 % of names wrong) but answers in Romansh (69 % of names and 97 % of places wrong).
- In Romansh it places half of the landmarks outside Graubünden in Graubünden (94 of 181). Gemma does the same
  (89 of 181).
- On photos too generic to identify it declines every time (32 of 32). Gemma invents a name for a quarter of
  them (8 of 32).

Method, hypotheses and limits: [`technical_report.md`](technical_report.md) (PDF: `RedPandas_Report.pdf`).

## Who checked what

- **Photos:** screened by AI (Claude Opus 5.5 with three re-checkers, then a second AI agent, Hermes); the team
  lead decided 6 photos on 4 landmarks. Then a Gemini agent reviewed all 429 shipped photos and flagged 14; the
  team lead accepted the flags (9 landmarks and 4 other photos removed). No person reviewed every shipped photo.
- **Grading audit:** one annotator (the team lead) graded 693 Apertus-70B core answers blind (the pre-registered
  20 % sample plus a registered top-up to 20 % per stratum); 670 are in the dataset (20.5 % of the 3,274 core
  answers). On these, judge–human κ = 0.79, code–human κ = 0.76. There is no second human; 8B, Gemma and the extension items
  have no human audit. Hermes graded the first (pre-registered) sample as an AI cross-check (481 of its 499 in the
  dataset).
- **AI-assisted:** the re-reads of judge–code disagreements and the code-grader reviews (Claude). Full list:
  [`docs/ai_use_statement.md`](docs/ai_use_statement.md).

## Status

Released (16 Oct): dataset revision `3b58eb219120` (pinned in `config.json`) with all 5,210 items, the three
models' graded responses and the human audit; code: `main`, tag `submission-v2`. The Hugging Face history was
squashed and the removed photos deleted, so earlier revisions are not served.

Result: 2nd runner-up (3rd place) in Track 1B, announced 23 Oct 2026.

Picking this up later: everything needed to check or extend the results is public. `make run` downloads the
pinned dataset and re-verifies every stored grade; with `LLM_*` set it evaluates a new model on the same items.
Every decision and correction, with its date and effect, is in `CHANGELOG.md`. The build caches and review
files under `work/` are local only (git-ignored) and are not needed to reproduce the published results.

## Run

From the repo root or this folder (Docker, clean checkout):

```bash
make run
```

- **No keys:** downloads the pinned dataset and checks the reference results (Apertus 70B): schema, image hashes,
  coverage, the code grader re-run on every stored answer, the final-label rule, a screening decision for every
  shipped photo, and recomputed scores equal to the published ones (checks V1–V7; exit code = result). CPU only,
  about a minute.
- **Live run:** with `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY` set (any OpenAI-compatible endpoint), it also
  evaluates that model on a seeded, stratified sample (`SAMPLE=150`) or on all items (`FULL=1`). Results go to
  `results/live-<model>/` (`scores.json`).
- **Judge (optional):** `JUDGE_MODEL`, `JUDGE_BASE_URL`, `JUDGE_API_KEY`. We used `openai/gpt-oss-120b:groq` via
  `https://router.huggingface.co/v1`. Without a judge, the code grader grades alone.
- `make` does not read `.env` by itself. Copy [`.env.example`](.env.example) to `.env`, fill it in, then run
  `set -a; . ./.env; set +a; make run` in this folder.
- **Other targets:** `make test` (unit and end-to-end tests), `make smoke` (live run on 20 items), `make shell`,
  `make clean`. Team only, in this folder: `make report` (PDF from `technical_report.md`; needs pandoc and xelatex).
- **Requirements:** Docker. An API key only for live runs. No model weights are downloaded. A full 70B run takes
  under an hour at 4 parallel requests.

Without Docker (Python ≥ 3.11, in this folder): `pip install -e .`, then `landmarks-eval verify`, or
`landmarks-eval live --sample 150` with the `LLM_*` variables set. Single steps: `landmarks-eval run`, `grade`,
`score`, `verify`, each with `--results <dir>`. `landmarks-eval --help` lists every command.

## Layout

| Path | Content |
|---|---|
| `src/landmarks_eval/` | Harness: dataset build (team only), run, graders, scores, `verify`, figures |
| `tests/` | Unit and end-to-end tests (offline fixture dataset) |
| `docs/` | `analysis_plan.md` (pre-registration), `extensions_plan.md`, `annotation_guidelines.md`, `ai_use_statement.md`, `consent_form_template.md`, `figures/` |
| `tools/` | Team-only pages for the grading audit and the photo check; the report's LaTeX header |
| `CHANGELOG.md` | Every decision and post-run correction, with its effect |
| `config.json` | Pinned dataset revision |

---

*The organisers' challenge description follows, unchanged.*

# Challenge 1B: Swiss Voices

This track 1 is focused on improving the multimodal Apertus v1.5 8B and 70B models. There are two different paths. Path B focuses on localising Apertus to the languages, dialects, knowledge and values of Switzerland. Submissions can focus either on the 8B or 70B model.

The submission must comply with the [HackApertus T&C](https://hackapertus.ch/terms-and-conditions). For this challenge it is essential that you pay particular attention to the conditions for responsibly sourced datasets.

## 🎯 The Challenge

**Localised alignment to the languages, dialects, knowledge and values of Switzerland**

**👉🏼You can pick one localisation dimension for your submission.**

This challenge accepts submissions that evaluate any of the following dimensions of localising Apertus to specific Swiss contexts: **input adaptation**, domain-specific **core task intelligence**, and **behavioural alignment.** These dimensions are motivated as follows.

### Input adaptation to local speech and dialects

Many speech-native multimodal LLMs struggle with phonetic drift, code-switching, local accents, and unwritten or low-resource dialects. Submissions should measure transcription accuracy and dialect comprehension to evaluate Apertus’s ability to transcribe Swiss voice inputs into written text representations without losing local context. Note that audio input is an experimental feature in Apertus 1.5.

Dialects that belong to the following ISO-639-3 dialect groups are permitted: gsw, wae, roh, lmo, frp. Dialects should be reported with their glottocodes.

### Core task intelligence for domain-specific knowledge

General base models usually struggle with domain-specific knowledge and niche terminology. Submissions should measure factuality and hallucination rates to evaluate whether Apertus possesses factually accurate, domain-tailored knowledge to execute specialised reasoning for localised Swiss contexts (e.g., legal statutes, local medical guidelines, local government administration processes).

### Alignment to localised preferences

Model performance is not only about dialects and facts, but also about cultural nuances, tone, safety boundaries, and local ethics. For every item in the dataset, the "correct" behaviour must trace to a source of normative authority. This could be a codified law or regulation, a documented professional or institutional standard, a measured majority preference (primary data collection or citation), a convention documented in a style guide or reference work. An item whose only warrant is the author's intuition does not present an authoritative source.

Submissions should measure how frequently responses meet end user expectations, to evaluate which regional norms and local regulatory standards Apertus respects by default. 

---

Each localisation approach calls for a different evaluation dataset type and has its own expectations for test items and evaluation metrics. The table below lists minimum dataset expectations for each localisation approach and example evaluation metrics. We expect the winning submissions to present datasets and evaluations that are significantly deeper than the minimum requirements. 

You should describe and motivate your dataset and evaluation design choices in detail in the submission report. 

| Localisation approach | Minimum evaluation dataset expectations | Example evaluation metrics |
|---|---|---|
| **Input Adaptation** | 100 curated audio clips, paired with text transcriptions and translations to a standard written language (e.g. German, French, Italian, Romansh) | Transcription: mean character error rate and word error rate across all audio clips.<br>Translation: BLEU, chrF, COMET. |
| **Core Task Intelligence** | 300 single-turn Q&A pairs with answer variations and source citations | SimpleQA-style three-way grading (correct/incorrect/not attempted) against ground-truth references using LLM-as-a-judge (with a random sample of 20% of judgements evaluated by a human and reported judge–human agreement). |
| **Behavioural Alignment** | 200 scenario prompts with explicit criteria defining acceptable vs. unacceptable answers, and a matched pair of `chosen` vs. `rejected` outputs; must be anchored in a specific use case and user community; expected behaviours should be labelled as contested vs. settled and treated accordingly. | Forced-choice preference accuracy, rubric-scored free generation with LLM-as-a-judge scoring against stated acceptance criteria (with a random sample of 20% of judgements evaluated by a human and reported judge–human agreement). |

---

## 🔧 Resources & Tools

Check our resources & tools page for detailed information:
https://hackapertus.notion.site/resources-tools


| Models           | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |

---

## 📦 Submission Requirements & Deliverables

❗️ Submissions are not handled on Devpost but via this URL only:
http://hackapertus.ch/online-hack/submissions

The submission must: 
1. follow the template repo and include all prerequisite files and definitions
2. follow the specified input/output formats
3. run in a Docker container, launched with `make run` from the root of the project
4. run end-to-end when judges try to run it

### Git repo (URL)
- Create your repo from this template (**Use this template**) and work in the `track_1b/` challenge directory. Delete the other track challenge directories.
- Keep `track_1b/` as it is: don't rename it or move its files.
- Set the repo to PUBLIC (Settings --> Collaborators --> Manage Visibility)
- Submit the URL of YOUR Git repo.

### Technical Report (pdf)
- Update [technical_report.md](technical_report.md) in this repository with all the details for your submission.
- Upload a pdf of your technical report to this directory, named as `TeamName_Report.pdf`.
- Format: pdf, max. 6 pages w/o references
- Submit the pdf of the technical report.

### Dataset (URL)
Submitted datasets must comply with our guidelines for responsibly sourced datasets.

- Create a user account on Hugging Face
- Clone our dataset template on Hugging Face: https://huggingface.co/datasets/HackApertus/online_hack_template
- Complete the dataset card with all required information
- Upload your dataset. It should consist of the following components:
    - evaluation dataset (i.e. individual test cases)
    - model response dataset (i.e. the model response to each test case)
    - metadata file (i.e. additional information about each test case; where relevant, this file must contain instance-level licensing information) 
- Make sure your dataset access control is set to PUBLIC
- Provide the URL of _your_ data set

### Reproducibility

You can create a Python notebook that reproduces your evaluation.

Judges will *only* run code for reproducing the submission from the root of the project with the following command:
```bash
make run
```
You should update the [Makefile](Makefile) so that it works for your submission on a clean checkout.

Requirements: `runtime, hardware, API keys, model weights`

---

## ⚖️ Judging Criteria

The following rubric will be used for scoring submissions. The points gained correspond to the scoring level, i.e. 1 scores 1 point. A submission must score at least at Level 1 on categories 1. to 4. to receive any points.

Categories 2. to 4. are weighted. The total score for the team is calculated as the weighted sum across all categories. The maximum score is 100 and the winning team will be the team with the highest score.

| **Category (× weight)** | **Scoring levels** |
|---|---|
| **1. Localisation and use case relevance** | **0:** No use case stated.<br>**1:** Use case clearly stated.<br>**2:** Use case relevance motivated; use case matters.<br>**5:** Dataset specifications clearly defined.<br>**10:** Dataset specifications are well matched to use case. |
| **2. Dataset quality (× 3)** | **0:** Only dataset links shared; dataset includes personally identifiable information.<br>**1:** Minimally viable dataset that follows schema and includes test items, metadata and ground truth / expected responses; basic descriptive statistics.<br>**2:** Quality metrics provided and motivated; ad hoc quality checks were done; dataset is usable but limited / has low diversity.<br>**5:** Full quality control was done to validate the dataset and is documented; dataset includes diverse / interesting examples (e.g. edge cases, adversarial examples).<br>**10:** Dataset presents a major improvement over currently available datasets; previously untested capabilities can be evaluated with this dataset; contamination checks conducted against Apertus training data (if relevant). |
| **3. Dataset documentation (× 2)** | **0:** Data card with placeholders or missing information; dataset not licensed under CDLA-Permissive-2.0 license.<br>**1:** Documentation complete; licenses provided for individual content items; appropriate consent form template provided.<br>**2:** Consent management and AI permissions clearly outlined.<br>**5:** Reproducible dataset construction (e.g. sampling strategy, data cleaning and preprocessing, annotation guidelines).<br>**10:** Exemplary data card providing full provenance on design choices, versioning, data sourcing, metadata labelling, ground truth annotations and compliance. |
| **4. Evaluation reproducibility (× 2)** | **0:** Cannot be reproduced; code or data missing.<br>**1:** Reproducible only with significant manual tweaking.<br>**2:** Scripted workflow exists but is fragile or poorly documented.<br>**5:** Deterministic workflow given fixed model outputs; clear instructions for creating the results file; substantiated grading; correctly implemented scoring functions.<br>**10:** Reusable harness for fully automated, self-contained evaluation; verifies its own outputs against expected results; works from a clean environment and can accept new models. |
| **Report clarity and communication** | **0:** Poorly organized with major gaps or unreadable sections.<br>**1:** Basic structure but difficult to follow.<br>**2:** Clear narrative with minor ambiguities.<br>**5:** Polished writing with well-chosen figures; concise.<br>**10:** Publication-quality document with compelling visualisations and flawless flow. |
| **Code quality** | **1:** Only submission files shared.<br>**2:** Useful shared notebook or package with basic documentation.<br>**5:** Well-documented package, Apache-2.0 licence, basic tests.<br>**10:** Plug-and-play package that can be adopted in the next iteration of the hackathon; excellent docs. |

## Support

### Licensing requirements
Please check our Terms & Conditions (6. What you build is open source):
https://hackapertus.ch/terms-and-conditions

### FAQ
💡 https://hackapertus.ch/faq

### Contact

💬 In case you have questions, join the conversation on Discord. Alternatively, send an email to “hello@hackapertus.ch”.
