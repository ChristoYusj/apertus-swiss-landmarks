# Online photo screening (team annotation tool)

The shared, live version of the photo-screening page (Task P, guideline v2-team), published as a private
claude.ai artifact so team members on different devices screen together. `build_packs.py` builds the
photo packs (420 px JPEG, base64, 22 landmarks per pack) and `data/cards.json` from `work/`; `screening.html`
stores one joint decision per landmark in the artifact's shared database (collection `screening`, one document
per landmark QID: `main`, `main_id`, `alt`, `low`, `t`), or on the device with a downloadable
`screening_team.json` when the viewer cannot write. The decisions use the same format as the offline page and
are merged with `landmarks-eval merge-review`.

## Human check of the AI screening (protocol v3-ai-assisted)
`check.html` + `build_check.py` (`python build_check.py <track_1b dir> work/review/screening_ai.json <output dir>`):
one row per landmark with only the photos the AI screening would publish (main, 2nd view, too generic), flagged
rows first. A1 clicks **Agree with AI ✓** or rejects a photo; checks are stored per landmark in the artifact's
database (collection `check`) or downloaded as `screening_check.json`. `landmarks-eval combine-screening --ai
work/review/screening_ai.json --check screening_check.json --out screening_team.json` turns them into the decision
file for `merge-review` (A1's verdict wins; unchecked landmarks stay pending).
