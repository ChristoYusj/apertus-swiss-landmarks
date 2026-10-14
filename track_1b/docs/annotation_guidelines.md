# Annotation guidelines (v2)

The guideline was written for three annotators (pseudonymous IDs **A1, A2, A3**); as run, the team has **one** annotator, A1
(see the protocol notes under each task and `CHANGELOG.md`). There are two tasks: photo screening (Task P) and the
grading audit (Task G).

## Task P: photo screening (guideline v2-team, joint decisions)
The team screens **together on one computer** and records **one joint decision per landmark** (no split, no
separate votes). Disagreements are discussed until the team agrees; if it cannot agree, the cautious option is
recorded. The page shows no model answers. One card per landmark:

1. **Main photo.** Choose **OK**, or **Exclude** if *any* of these is visible:
   - a recognisable person: a face, or a person close enough to be identifiable;
   - a readable car licence plate;
   - the inside of a private home;
   - any text with personal data (name plates, letters).

   People who are tiny and unrecognisable in a crowd or in the distance are fine. We **exclude and replace**
   photos; we never blur them, because blurring would modify a CC BY-SA work. Choose **Wrong object** if the
   photo does not show this landmark (another building, a map, a painting). An excluded or wrong main photo
   removes the landmark from the dataset; its existing answers are kept in `metadata/excluded_items.jsonl`.
2. **Second view.** Among the other photos, click **Use as 2nd view** on the best one: the **same object**, from
   the **outside** (or the main visible feature for a fountain, bridge or statue), clearly enough that someone
   who knows the object could recognise it, and with **no recognisable people** (rule 1). If none qualifies,
   click **None usable** (different building, interior, detail only, mostly scenery, old engraving or map).
3. **Low-information (optional).** Click **Too generic** on a photo (also with no people) that alone would not
   let even an expert know *which* object it is: a close-up of a generic door, a typical chapel interior, a
   plain wall. It becomes an "unknowable" trap item, where the correct behaviour is to say "I can't tell".

Only the photos picked in 2 and 3 are shipped besides the main photo; the others are never published.
If unsure, choose the more cautious option: **Exclude** for privacy, don't pick a second view.
Progress is saved in the browser after every click; **Save progress** downloads `screening_team.json`
at any time, and **Load saved file** resumes from it.

### Task P as run: protocol v3-ai-assisted (14 Oct, before any team decision existed)
The team did not have the hours for a joint screening of 917 photos, so the rules above were applied in three steps:

1. **AI screening.** Claude (Opus 5.5) applied rules 1–3 to every photo, viewing each one at the published size
   (8 parallel screeners, 33 landmarks each). Each photo got a structured record: people (none / distant and
   unrecognisable / recognisable), licence plate, private interior, personal text, whether it shows the landmark,
   the kind of view, and whether it is too generic.
2. **Independent AI re-check.** Two further Claude instances, without the first screener's reasons, re-checked
   every photo that step 1 would publish (main photo, 2nd view, too-generic photo) for the same privacy items and
   for the role ("same object as the main photo", "really too generic").
3. **Human check by A1** (`tools/screening_online/check.html`). Every landmark is one row showing only the photos
   that would be published. Rows are flagged first if the AI excluded the main photo, either AI pass saw any
   person, plate, private interior or personal text, the re-check disagreed, the AI was not highly confident, or
   the face detector fired. For each row A1 either clicks **Agree with AI ✓** or rejects a photo
   (*Person / private*, *Wrong object*, *Not same / unclear*, *Not generic*).

A1's verdict wins (`landmarks-eval combine-screening`): a photo is published only if A1 accepted it; a rejected
2nd view or too-generic photo becomes "none" (never silently replaced); a main photo A1 rejects drops the
landmark. A landmark A1 did not check stays pending, so the privacy gate (verify V7) fails until a person has
seen every published photo. The image records name both reviewers (`ai:claude-opus-5-5`, `A1`).

## Task G: grading audit (after the official run)
Task G is done **independently**: each annotator labels alone (sharing one computer is fine, one after the
other, each under their own ID), and no item is discussed until all annotators have submitted their labels.
Agreement between annotators is only meaningful if the labels are independent.
Two equivalent tools show the same items in the same order: the offline page (`landmarks-eval audit-page`) and an
online page for annotators on other devices (`tools/audit_online`, labels stored per annotator; the page only
shows your own). Answers not in French come with a labelled English machine gloss (same model as the judge;
proper names left untranslated); the original answer is authoritative, and you tick *used translation* if you
relied on the gloss.

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

As planned for three annotators: agreement on a 100-item overlap (Fleiss' κ), disagreements resolved by discussion, adjudicated labels stored separately. **As run (protocol v3, one annotator):** 40 sampled items are shown a second time, unannounced and at least 150 items later, and the annotator's self-consistency (raw agreement, Cohen's κ) is reported instead; judge-vs-human and code-vs-human agreement are reported as planned.
