# AI use in this project (disclosure)

| What | Tool / model | Role | Human oversight |
|---|---|---|---|
| Models under evaluation | `swiss-ai/Apertus-v1.5-70B` and `-8B` (CSCS hackathon endpoint) | Answer every test question | — |
| Comparison model | `google/gemma-4-31B-it`, open weights, via Hugging Face Inference Providers | Answers every test question with the same request format, as a reference point | Registered before the run (`docs/extensions_plan.md`) |
| Answer grading | `openai/gpt-oss-120b`, open weights, via Hugging Face Inference Providers (frozen prompt `judge-v1`) | Independent LLM judge on 100 % of answers; final labels. Never Apertus grading itself | Code grader on 100 % as a second rater. Blind human audit of the 20 % sample (522 answers, one annotator): judge vs human κ = 0.76 |
| Judge dev set | Labels proposed by Claude (AI coding assistant) | 40 items used to tune the judge prompt before it was frozen | The team lead ruled on the 4 hard cases and accepted the other 36 without item-by-item review |
| Judge-vs-code disagreements | Independent Claude agents | Re-read every disagreement against the written rules (two reads where the judge looked wrong); used only for a sensitivity analysis | AI-assisted, not a human audit; results in `disagreement_adjudication.jsonl` |
| Code-grader reviews | Claude agents | Read the code grader's labels and proposed rule fixes (reviews 2–5) | Each change is logged in `CHANGELOG.md` with its effect and pinned by regression tests; AI-assisted, not a human audit |
| Photo screening | Claude Opus 5.5 (8 screeners, 3 independent re-checkers) and a second AI agent (Hermes) | Privacy (people, plates, private interiors, personal text), wrong object, second view, too-generic photos | The team lead set the policy ("if unsure, exclude") and decided 6 edge-case photos on 4 landmarks. No person reviewed every shipped photo |
| AI cross-check of the audit sample | Second AI agent (Hermes) | Graded the 546 sampled answers | Reported as AI-vs-judge agreement (`ai_crosscheck_audit`), never as a human audit |
| Question templates | Drafted with an AI coding assistant (Claude Code) | About 6 fixed sentences per language (FR, DE, IT, RM) | FR reviewed by French-speaking team members. DE/IT checked by back-translation. RM not reviewed by a native speaker, so RM results are labelled exploratory |
| Software | Written with an AI coding assistant (Claude Code) | Data pipeline, graders, harness, tests | Every step has automated regression tests; `make run` re-verifies every stored grade. The team reviewed the design decisions |
| Answer translation for annotators | `openai/gpt-oss-120b` (same judge endpoint), labelled as machine translation | English gloss of non-FR answers on the audit page | Annotators see the original answer next to the gloss |

The answer keys come from Wikidata (CC0) and the official BFS municipality register. No AI system wrote a gold answer;
the rule-based cleaning of the keys (rules in code) is logged in `CHANGELOG.md`.
