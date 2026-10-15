# Photo-screening tools (Task P)

Team-only tools for the photo screening (`docs/annotation_guidelines.md`, Task P). Run them with the project venv.
The `.html` files are sources for private claude.ai artifacts (decisions saved per click in the artifact
database, or downloaded as JSON when the viewer cannot write).

## Used for the shipped photos (protocol v3b-ai-review)
AI screening (Claude) and a second AI review (Hermes); the team lead decided 6 photos on 4 landmarks. No person
reviewed every shipped photo.

- `hermes_to_check.py <Hermes handoff.json> <a1_decisions.json> <out screening_check.json>`: converts the second
  AI review into a screening-check file. Per photo, the reviewer's verdict is used (the lead's edge decisions are
  part of it); later lead decisions in `a1_decisions.json` (e.g. made in chat) override it. The class of each
  dropped main photo comes from the reviewed table `MAIN_DROP_CLASS` in the script.
- Then `landmarks-eval combine-screening --ai work/review/screening_ai.json --check <screening_check.json> --out
  screening_team.json`, then `landmarks-eval merge-review screening_team.json`.

## Human check of every shipped photo: prepared, not done yet
Two forms for the same check (rule 1 of the screening: recognisable face, readable plate, private interior,
personal text). A flagged main photo removes its landmark; a flagged 2nd view or too-generic photo removes only
that photo.
- `build_photo_check_page.py <dataset> <out dir>` + `photo_check.html`: one row per landmark with exactly the
  published photos (byte for byte), face-detector hits first; collection `pcheck`, or download `photo_check_A1.json`.
- `build_photo_check_pdf.py <dataset> <out.pdf>`: fillable PDF, 6 photos per page, one "problem" tick box per photo;
  `read_photo_check_pdf.py <filled.pdf> <out.json>` lists the flagged photos.
- `apply_photo_check.py <check.json> <work dir>`: records a complete check with no photo flagged (screening report +
  reviewer on every shipped photo); refuses undecided photos and stops on flagged ones (those need a rebuild).

## Earlier protocols
- **v3-ai-assisted (human check of the AI screening), used for 3 rows only:** `build_check.py <track_1b dir>
  work/review/screening_ai.json <out dir>` + `check.html`: one row per landmark with the photos the AI screening
  would publish, flagged rows first; collection `check`, or download `screening_check.json` for
  `combine-screening`.
- **v2-team (joint team screening), not run (0 decisions):** `build_packs.py <track_1b dir> <out dir>` (420 px
  photo packs, 22 landmarks per pack, `data/cards.json`) + `screening.html`: one joint decision per landmark
  (collection `screening`, or download `screening_team.json`), merged with `landmarks-eval merge-review`.
