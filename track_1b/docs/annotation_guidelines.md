# Annotation guidelines (v2)

Three team members (pseudonymous IDs **A1, A2, A3**) annotate. There are two tasks: photo screening (Task P) and the grading audit (Task G).

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

## Task G: grading audit (after the official run)
Task G is done **independently**: each annotator labels alone (sharing one computer is fine, one after the
other, each under their own ID), and no item is discussed until all three have submitted their labels.
Agreement between annotators is only meaningful if the labels are independent.

You see the question, the gold answer (with accepted alternatives) and the model's answer. You do **not** see the automatic grades. Choose exactly one label:

- **Correct:** the answer commits to the gold target and contradicts nothing in it. The name can be any recognisable name, translation or unique description of *this* object. The place must be the right municipality. A year must fall inside the gold window shown.
- **Incorrect:** the answer commits to something that contradicts the gold: another object, municipality or year outside the window. Also incorrect: several competing candidates, or (trick questions) going along with the false town stated in the question.
- **Not attempted:** the answer declines ("I can't tell"), or is too vague to check ("a church in Switzerland", "the 16th century"), without contradicting the gold.

Edge cases:
- **Hedging:** "Probably X" is graded on X.
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

Agreement on the 100 items all three annotators label is reported in the paper (Fleiss' κ). After labelling, disagreements on those items are resolved by discussion. The adjudicated label is stored separately, and the original labels are kept.
