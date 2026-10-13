# Online photo screening (team annotation tool)

The shared, live version of the photo-screening page (Task P, guideline v2-team), published as a private
claude.ai artifact so team members on different devices screen together. `build_packs.py` builds the
photo packs (420 px JPEG, base64, 22 landmarks per pack) and `data/cards.json` from `work/`; `screening.html`
stores one joint decision per landmark in the artifact's shared database (collection `screening`, one document
per landmark QID: `main`, `main_id`, `alt`, `low`, `t`), or on the device with a downloadable
`screening_team.json` when the viewer cannot write. The decisions use the same format as the offline page and
are merged with `landmarks-eval merge-review`.
