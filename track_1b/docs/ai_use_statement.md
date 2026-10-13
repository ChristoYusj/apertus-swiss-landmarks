# AI use in this project (disclosure)

| What | Tool / model | Role | Human oversight |
|---|---|---|---|
| Model under evaluation | `swiss-ai/Apertus-v1.5-70B` (CSCS hackathon endpoint) | Answers every test question | — |
| Answer grading | `openai/gpt-oss-120b`, open weights, via Hugging Face Inference Providers | Independent LLM judge on 100 % of answers. Never Apertus grading itself | Code grader on 100 % as a second rater; blind human audit of a random 20 % |
| Question templates | Drafted with an AI coding assistant (Claude Code) | About 6 fixed sentences per language (FR, DE, IT, RM) | FR reviewed by French-speaking team members. DE/IT checked by back-translation. RM not reviewed by a native speaker, so RM results are labelled exploratory |
| Software | Written with an AI coding assistant (Claude Code) | Data pipeline, graders, harness, tests | Every step had an automated regression check and an independent re-check (`work/verify_*`, not shipped). The team reviewed the design decisions |
| Answer translation for annotators | `openai/gpt-oss-120b` (same judge endpoint), labelled as machine translation | English gloss of non-FR/EN answers in the audit sheet | Annotators see the original answer next to the gloss |

The answer keys come from Wikidata (CC0) and the official BFS municipality register. No AI system produced or changed a gold answer.
