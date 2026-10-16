# Annotation guidelines (v2)

Written for three annotators (pseudonymous IDs **A1, A2, A3**). As run, there was **one** annotator, A1 (see the
"as run" notes under each task and `CHANGELOG.md`). Two tasks: photo screening (Task P) and the grading audit
(Task G).

## Task P: photo screening (guideline v2-team, joint decisions; not run, see *as run* below)
The team screens **together on one computer** and records **one joint decision per landmark** (no split, no
separate votes). Disagreements are discussed until the team agrees; if it cannot agree, the cautious option is
recorded. The page shows no model answers. One card per landmark:

1. **Main photo.** Choose **OK**, or **Exclude** if *any* of these is visible:
   - a recognisable person: a face, or a person close enough to be identifiable;
   - a readable car licence plate;
   - the inside of a private home;
   - any text with personal data (name plates, letters).

   Tiny, unrecognisable people in a crowd or in the distance are fine. We **exclude and replace** photos; we never
   blur them, because blurring would modify a CC BY-SA work. Choose **Wrong object** if the photo does not show
   this landmark (another building, a map, a painting). An excluded or wrong main photo removes the landmark from
   the dataset; its existing answers are kept in `metadata/excluded_items.jsonl`.
2. **Second view.** Among the other photos, click **Use as 2nd view** on the best one: the **same object**, from
   the **outside** (or the main visible feature for a fountain, bridge or statue), clear enough that someone who
   knows the object could recognise it, and with **no recognisable people** (rule 1). If none qualifies, click
   **None usable** (different building, interior, detail only, mostly scenery, old engraving or map).
3. **Too generic (optional).** Click **Too generic** on a photo (also with no people) that alone would not
   let even an expert know *which* object it is: a close-up of a generic door, a typical chapel interior, a
   plain wall. It becomes an "unknowable" trap item, where the correct behaviour is to say "I can't tell".

Besides the main photo, only the photos picked in 2 and 3 are shipped; the others are never published.
If unsure, choose the more cautious option: **Exclude** for privacy, no second view.
The page saves progress in the browser after every click; **Save progress** downloads `screening_team.json`
and **Load saved file** resumes from it.

### Task P as run: AI screening with a second AI review and a third check (protocol v3b-ai-review, 14–15 Oct)
The team did not have the hours to screen 917 photos jointly, so AI applied the rules above. The lead (A1) set
the policy, decided edge cases and accepted the third check's flags. No model answer was shown at any step.

1. **AI screening.** Claude (Opus 5.5) applied rules 1–3 to every photo, viewing each at the published size
   (8 parallel screeners, 33 landmarks each). Each photo got a structured record: people (none / distant and
   unrecognisable / recognisable), licence plate, private interior, personal text, whether it shows the landmark,
   the kind of view, and whether it is too generic.
2. **Independent AI re-check.** Three further Claude instances, without the screeners' reasons, re-checked every
   photo that step 1 would publish (491: main photo, 2nd view, too-generic photo) for the same privacy items and
   for the role ("same object as the main photo", "really too generic").
3. **Second AI review (Hermes agent).** A separate AI agent reviewed the same 491 photos under the lead's policy
   "if unsure, exclude": 32 photos it could not settle were excluded under that policy. The lead decided 6 photos
   on 4 landmarks (a partly visible licence plate, a borderline second view, ...), one landmark of them in chat (the
   "San Bastian" main photo shows Schloss Wildenberg: wrong object). A human check page
   (`tools/screening_online/check.html`: one row per landmark with only the published photos) was prepared but
   used for 3 rows only, so in this screening **no person looked at every published photo**. Result: 13
   landmarks removed, 429 photos shipped (the first release).
4. **Third check (15 Oct, evening).** A Gemini agent (`gemini-3.8-flash`, Google Antigravity) reviewed all 429
   shipped photos on the blank photo-check form (`tools/screening_online/build_photo_check_pdf.py`) and flagged
   14 by its own judgement; the lead accepted the flags. No person reviewed every shipped photo. Same rule as above: a flagged main photo removes its
   landmark (9), a flagged 2nd view or too-generic photo only itself (4 on other landmarks; never replaced). Some
   flags (a shop-window mannequin, a museum interior) go beyond rule 1: precautionary removals. 210 questions went
   (answers kept in `metadata/excluded_items.jsonl`); 409 photos are shipped.

The second review's verdict wins, except on the photos the lead decided and the third check's flags
(`landmarks-eval combine-screening`, converter `tools/screening_online/hermes_to_check.py`; flags added by
`tools/screening_online/apply_photo_check.py`). A photo is published only if it was kept. A rejected 2nd
view or too-generic photo becomes "none" (never silently replaced). A rejected main photo drops the landmark, with
the reason in the exclusion log (privacy, wrong object, "may not show the landmark (excluded when unsure)", or the
third check's flag with the AI's note).
Image records name the screening reviewers (`ai:claude-opus-5-5`, `ai:hermes`, plus `A1` on photos a person
decided; the 3 such photos were removed in the third check, so no shipped photo carries `A1`). The third check is
recorded once, in `metadata/review.json` (`ai_photo_review`: the agent's flags and notes, accepted by A1), not
per photo.

## Task G: grading audit (after the official run)
Each annotator labels **independently**: alone (one shared computer is fine, one after the other, each under
their own ID), and no item is discussed until all annotators have submitted. Agreement between annotators is only
meaningful if the labels are independent.

Forms: as run (protocol audit-v4), one blind fillable PDF per part (below). The earlier protocol v3 had an
offline page (`landmarks-eval audit-page`) and an online page (`tools/audit_online`) with the same items in the
same order; it was replaced before any label was collected. Answers not in French come with a labelled English
machine gloss (same model as the judge; proper names left untranslated). The original answer is authoritative;
tick *used translation* if you relied on the gloss.

You see the question, the gold answer (with accepted alternatives) and the model's answer. You do **not** see the automatic grades. Choose exactly one label:

- **Correct:** the answer commits to the gold target and contradicts nothing in it. The name can be any recognisable name, translation or unique description of *this* object. The place must be the right municipality. A year must fall inside the gold window shown.
- **Incorrect:** the answer commits to something that contradicts the gold: another object, municipality or year outside the window. Also incorrect: several competing candidates, or (trick questions) going along with the false town stated in the question.
- **Not attempted:** the answer declines ("I can't tell"), or is too vague to check ("a church in Switzerland", "the 16th century"), without contradicting the gold.

Edge cases:
- **Hedging:** "Probably X" is graded on X. A hedge that names nothing specific ("not sure, it seems to be a church") is **Not attempted**.
- **Wrong object, right town** (place questions): if the answer names a *different* landmark than the gold one ("San Martino church in Poschiavo" for San Vittore), it is **Incorrect** even though the town is right.
- **Village instead of municipality:** naming a village or locality inside the gold municipality (Cinuos-chel for S-chanf) is **Incorrect**; the question asks for the municipality.
- **Similar names:** a similar but different name ("Museo cantonale d'arte e di storia" for "Museo Cantonale d'Arte") is **Incorrect**.
- **Trick questions** (the question states a false town): **Incorrect** if the answer accepts the false town *or* names a landmark that is not the gold one; **Correct** if it names the gold landmark or rejects the false town; **Not attempted** if it declines.
- **Only the right canton** (place questions, no municipality): **Not attempted**; a wrong canton or another country is **Incorrect**.
- **Spelling:** spelling variants, missing accents and exonyms (Genève = Genf = Geneva) are fine.
- **Saint or type names only:** if the gold says *[only with the town]*, a bare "St. Antonius chapel" without the right town is **Not attempted**.
- **Shared town names:** for places marked *also the name of another municipality*, the canton must be right too.
- **Foreign-language answers:** if the answer is in a language you don't read, use the English machine translation shown under it. Tick **"used translation"**.

Worked examples:

| Question (FR) | Gold | Answer | Label |
|---|---|---|---|
| Quel est ce monument ? | Fontaine de la Justice (Lausanne) | "La Fontaine de la Justice, place de la Palud." | Correct |
| Quel est ce monument ? | Fontaine de la Justice (Lausanne) | "La fontaine des Trois Grâces à Berne." | Incorrect |
| Quel est ce monument ? | Fontaine de la Justice (Lausanne) | "Une fontaine historique en Suisse." | Not attempted |
| Où se trouve… ? | Lausanne, VD | "Probablement à Lausanne." | Correct |
| Où se trouve… ? | Lausanne, VD | "À Lausanne ou à Vevey." | Incorrect |
| En quelle année… ? | 1585 (window 1580–1590) | "Au XVIe siècle." | Not attempted |
| Ce monument se trouve à Berne… ? | Lausanne | "Ce n'est pas Berne : c'est la Fontaine de la Justice à Lausanne." | Correct |

**As registered (protocol audit-v4, 15 Oct ~12:47):** three annotators (A1, A2, A3) each label 194 answers blind,
on a fillable PDF that shows no grade of any kind (`tools/audit_online/build_audit_v4.py`,
`build_check_pdf.py --blind`): 164 of their own and a 30-item overlap that all three label (Fleiss' κ). The 522
items are the pre-registered 20 % sample minus the landmarks the photo screening removed. Work alone, without
looking anything up, and do not discuss items until all three have finished. Human label = the annotator's label;
on the overlap, the majority of the three. A second AI's grades of the same sample are reported separately as an
AI cross-check, never as Task G.

**As run:** the team lead (A1) graded all three parts (stated 15 Oct), so the labels are one annotator's: 522
answers, of which 499 are still in the dataset after the third photo check; judge–human agreement is computed on
these 499, and there is no agreement between people. The second and third labels of the 30 shared items (27 still
in the dataset) are kept as repeats (the overlap was known, so this is not a blind test-retest).

**Top-up (16 Oct, registered before labelling):** after items were removed and `photo_alt`/`trap_lowinfo` added,
the 499 covered 15 % of the 70B core answers. `tools/audit_online/build_audit_topup.py` (seed 20261020) drew 171
more, stratum by stratum (arm × language × judge label), until every stratum is at least 20 % human-labelled; A1
graded them on one blind PDF (same layout, English gloss for non-French answers; read with `read_topup_pdf.py`).
Now 670 labelled answers in the dataset (20.5 %).
