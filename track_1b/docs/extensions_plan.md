# Extensions plan (registered 15 Oct 2026, before any of these items exist or were run)

Three additions to the frozen analysis plan (`docs/analysis_plan.md`). Everything below is fixed by the commit that
adds this file; the items are built and run only after it. All three are **descriptive** (no new hypothesis enters
the Holm family). Results are reported whatever they show.

## E1. Comparison model
- Model: `google/gemma-4-31B-it`, open weights, via the Hugging Face router, provider pinned (`:novita`).
- Same 3,412 items, same request format and parameters as Apertus (temperature 0, top_p 1, max_tokens 300, seed
  1234, one base64 JPEG + one question, no system prompt), same graders (frozen judge `judge-v1` + code grader).
- Reported: the same tables as for Apertus 70B (by language, arm, fame); the question is whether the language
  pattern (declining in French, fabricating in Romansh) is specific to Apertus.

## E2. Multiple choice (`photo_mc`)
- For each of the 251 landmarks, its main photo with 4 named options: the landmark and 3 distractors drawn (seed
  20261019) from the other dataset landmarks of the same type group, from the same language region first, then
  any region. Each option is shown as "name (municipality)"; the name is the label in the question's language,
  else in the landmark's region language, else English, else its first name alias; options with identical text
  are redrawn. Option order shuffled with the same seed. Asked in FR, DE, IT, RM (1,004 items).
- Template (prompt version `q-v2-mc`): the name question + the 4 lettered options + "answer with the letter; if you
  are not sure, say so".
- Graded by code only (the judge is not used): exactly one option identified by its letter or its text ->
  correct / incorrect; two or more options -> incorrect; a refusal, or no option identified -> not attempted.
  The number of answers that name something outside the options is reported.
- Run on Apertus 70B, Apertus 8B and Gemma. Reported: accuracy by language against chance (25 %).

## E3. Second wording (`photo_main_w2`)
- The name and place questions on the main photo, asked again in French and Romansh with a second, independent
  wording written before the run (prompt version `q-v2-w2`; same meaning, same "say so if unsure" cue).
  1,004 items, Apertus 70B only, graded like `photo_main` (judge + code).
- Reported: per language, the not-attempted and incorrect rates under both wordings, paired by landmark (McNemar).
  If the Romansh-vs-French gap stays under the second wording, the effect is not an artefact of one phrasing.

## Cost and logging
Apertus runs on the hackathon CSCS endpoint. Gemma and the judge run on Hugging Face (paid): token usage is
logged per chunk; the total is reported in the CHANGELOG.
