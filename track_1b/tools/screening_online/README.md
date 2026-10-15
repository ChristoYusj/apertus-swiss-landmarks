# Photo-screening tools (Task P)

Team-only tools for the photo screening (`docs/annotation_guidelines.md`, Task P). Run them with the project venv.
The `.html` files are sources for private claude.ai artifacts (decisions saved per click in the artifact
database, or downloaded as JSON when the viewer cannot write).

## Used for the shipped photos (protocol v3b-ai-review)
AI screening (Claude) and a second AI review (Hermes); the team lead decided 6 photos on 4 landmarks. Then a
third check (15 Oct, evening): a Gemini agent reviewed all 429 shipped photos on the blank PDF form and flagged
14 by its own judgement; the team lead accepted the flags (merged as below). No person reviewed every shipped
photo.

- `hermes_to_check.py <Hermes handoff.json> <a1_decisions.json> <out screening_check.json>`: converts the second
  AI review into a screening-check file. Per photo, the reviewer's verdict is used (the lead's edge decisions are
  part of it); later entries in `a1_decisions.json` override it: the lead's own decisions (e.g. made in chat) and
  AI flags the lead accepted (marked `"by": "ai:<name>"`, never credited to a person). The class of each dropped
  main photo comes from the reviewed table `MAIN_DROP_CLASS` in the script.
- Then `landmarks-eval combine-screening --ai work/review/screening_ai.json --check <screening_check.json> --out
  screening_team.json`, then `landmarks-eval merge-review screening_team.json`.

## Check of every shipped photo (the third check)
Rule 1 of the screening (recognisable face, readable plate, private interior, personal text). A flagged main
photo removes its landmark; a flagged 2nd view or too-generic photo removes only that photo (never replaced).
- Forms: `build_photo_check_page.py <dataset> <out dir>` + `photo_check.html` (one row per landmark with exactly
  the published photos, face-detector hits first; collection `pcheck`, or download `photo_check_A1.json`), or
  `build_photo_check_pdf.py <dataset> <out.pdf>` (fillable PDF, 6 photos per page, one "problem" tick box per
  photo) and `read_photo_check_pdf.py <filled.pdf> <out.json>` (lists the ticked photos). The two PDF scripts need
  `reportlab` and `pypdf`, which are not in the project `.venv`.
- `apply_photo_check.py decisions|record <check.json> <work dir>`. `<check.json>` is a human check (the PDF
  reader's output, or the online page's download or database documents; undecided photos are refused) or an AI
  review (format `ai-photo-review`: `reviewer` `ai:<name>`, `accepted_by`, `photos`, `flagged`, `ai_notes`). An AI
  review is recorded as `ai_photo_review` and credits no person; a human check is recorded as `human_photo_check`
  and adds the checker to the reviewers of every photo still shipped.
- Order: (1) `apply_photo_check.py decisions <check.json> work` writes the flags to `work/review/a1_decisions.json`;
  (2) `hermes_to_check.py`, `combine-screening`, `merge-review` as above; (3) `apply_photo_check.py record
  <check.json> work` removes exactly the items of removed photos and landmarks (every other item byte for byte),
  logs them in `work/removed_items.jsonl` and stores the check in the screening report; (4) `landmarks-eval
  assemble`, regenerate the card, re-score every model, `verify`.
- As run: `work/review/photo_check/gemini_photo_review.json` (the agent's flags and notes, taken from its script;
  one licence-plate number redacted).

## Earlier protocols
- **v3-ai-assisted (human check of the AI screening), used for 3 rows only:** `build_check.py <track_1b dir>
  work/review/screening_ai.json <out dir>` + `check.html`: one row per landmark with the photos the AI screening
  would publish, flagged rows first; collection `check`, or download `screening_check.json` for
  `combine-screening`.
- **v2-team (joint team screening), not run (0 decisions):** `build_packs.py <track_1b dir> <out dir>` (420 px
  photo packs, 22 landmarks per pack, `data/cards.json`) + `screening.html`: one joint decision per landmark
  (collection `screening`, or download `screening_team.json`), merged with `landmarks-eval merge-review`.
