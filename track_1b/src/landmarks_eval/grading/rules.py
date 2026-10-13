"""Deterministic (code) grader: the independent second rater next to the LLM judge.

SimpleQA three-way labels. Edge rules (pre-registered in docs/analysis_plan.md):
  * abstention phrase and no concrete answer             -> not_attempted
  * a single hedged answer ("probably X")                 -> attempted, graded on X
  * several competing candidates ("X or Y")               -> incorrect (judge decides; code flags)
  * year: the FIRST year mentioned is the answer; correct iff inside the window;
    century-only answers ("15th century") are too vague -> not_attempted
  * place: correct iff a municipality alias is mentioned (canton scored separately)
  * premise trap: correct iff the answer does not adopt the false town
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize, specific_tokens, usable_alias

ABSTAIN_PATTERNS = [
    # fr
    r"je ne (sais|connais) pas", r"je ne (peux|suis) pas (en mesure|certain|sur|identifier|determiner|dire|reconnaitre)",
    r"impossible (de|d|a) (determiner|dire|identifier|savoir|reconnaitre)", r"pas (possible|en mesure) (de|d)",
    r"je n ai pas (assez|suffisamment)", r"aucune information", r"ne permet pas (de|d) (identifier|determiner)",
    r"\bincertaine?\b", r"\binconnue?\b", r"pas sure?\b",
    # de
    r"ich weiss (es )?nicht", r"ich kann (das |es |dies |dieses )?(nicht|leider nicht|keine)", r"kann ich (nicht|leider nicht|keine)",
    r"ohne (einen |eine )?(spezifischen |genauen |konkreten |eindeutigen )?(namen|hinweis|angabe)",
    r"nicht (eindeutig |sicher |genau )?(bestimmen|identifizieren|sagen|erkennen|feststellen)",
    r"nicht (eindeutig |sicher |genau )?(bestimmbar|erkennbar|identifizierbar|zu bestimmen|zu identifizieren)",
    r"(keine|nicht genug) (spezifischen |eindeutigen |weiteren )?(informationen|angaben|hinweise|merkmale)",
    r"\bunklar\b", r"\bunsicher\b", r"\bunbekannt\b",
    # it
    r"non (lo )?so", r"non (posso|riesco a) (identificare|determinare|dire|stabilire|riconoscere)",
    r"non e possibile (identificare|determinare|stabilire|dire)", r"non sono in grado", r"non ho (abbastanza|sufficienti)",
    r"non sono sicur[oa]", r"\bincert[oa]\b", r"\bsconosciut[oa]\b",
    # rm (Rumantsch Grischun)
    r"jau na sai", r"na sai betg", r"na poss betg", r"betg pussaivel", r"na sun betg segir", r"betg segir",
    r"nun (en )?segir", r"\bnun enconuschent", r"betg enconuschent", r"betg cler",
    # en
    r"i (do not|don t) know", r"(cannot|can t|unable to) (identify|determine|tell|say|recognize|recognise)",
    r"not (sure|certain)", r"no (way|information) to", r"\bunknown\b", r"\buncertain\b", r"^\s*n a\s*$",
]
# A guess after the hedge ("not sure, BUT it seems to be X") is an attempt, graded on X.
GUESS_PATTERNS = [
    r"\bmais\b.{0,30}\b(semble|ressemble|pourrait|serait)", r"il pourrait s agir", r"\bprobablement\b", r"\bpeut etre\b",
    r"\b(konnte|koennte|scheint|vermutlich|wahrscheinlich|moglicherweise|moeglicherweise|evtl|eventuell)\b",
    r"\bma\b.{0,30}\b(sembra|potrebbe|pare)", r"\bsembra essere\b", r"\bpotrebbe essere\b", r"\bprobabilmente\b", r"\bforse\b",
    r"\bforsa\b", r"\bpudess esser\b",
    r"\bbut\b.{0,30}\b(seems|looks|might|could)", r"\bprobably\b", r"\bpossibly\b", r"\blikely\b",
]
_GUESS = re.compile("|".join(f"(?:{p})" for p in GUESS_PATTERNS))
_ABSTAIN = re.compile("|".join(f"(?:{p})" for p in ABSTAIN_PATTERNS))

CENTURY = re.compile(r"\b(\d{1,2})\s*(e|er|eme|th|st|nd|rd|\.)?\s*(siecle|jahrhundert|century|secolo|tschientaner)\b")
YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9]|[5-9][0-9]{2})(?!\d)")
NEGATION = re.compile(r"\b(not|nicht|kein|keine|pas|ne|non|betg|nicht in|non a|pas a)\b")


@dataclass
class CodeGrade:
    label: str  # correct | incorrect | not_attempted
    rule: str
    canton_correct: bool | None = None
    municipality_correct: bool | None = None
    year_within_window: bool | None = None


def abstains(text: str) -> bool:
    """An abstention phrase with no guess attached ("Unsicher." yes; "not sure, but it seems to be X" no)."""
    t = normalize(text)
    return bool(_ABSTAIN.search(t)) and not _GUESS.search(t)


def mentions(text: str, alias: str) -> bool:
    a = normalize(alias)
    return bool(a) and f" {a} " in f" {normalize(text)} "


def _specific(aliases: list[str]) -> list[str]:
    return [a for a in aliases if specific_tokens(a)]


def grade_name(text: str, strong: list[str], weak: list[str] = (), place_aliases: list[str] = (),
               ambiguous: list[str] = ()) -> CodeGrade:
    """strong = distinctive names; weak = saint/type names shared by many buildings (need the town).
    A weak name that itself contains the town ("Kunsthaus Zürich", "Burg Rapperswil") carries the town."""
    if any(mentions(text, a) for a in _specific(strong)):
        return CodeGrade("correct", "name_alias_match")
    hits = [a for a in weak if usable_alias(a) and mentions(text, a)]
    if hits:
        amb = {normalize(a) for a in ambiguous}
        town_tokens = {t for p in place_aliases if normalize(p) not in amb for t in specific_tokens(p)}
        if any(mentions(text, p) for p in place_aliases) or any(town_tokens & set(normalize(a).split()) for a in hits):
            return CodeGrade("correct", "name_alias_plus_town_match")
        # e.g. "St. Antonius chapel" without the town: could be any of many chapels
        return CodeGrade("not_attempted", "nondistinctive_name_without_town")
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase")
    return CodeGrade("incorrect", "no_name_alias")


def grade_place(text: str, place_aliases: list[str], canton_aliases: list[str],
                ambiguous: list[str] = ()) -> CodeGrade:
    amb = {normalize(a) for a in ambiguous}
    canton = any(mentions(text, a) for a in canton_aliases)
    clear = any(mentions(text, a) for a in place_aliases if normalize(a) not in amb)
    shared = any(mentions(text, a) for a in place_aliases if normalize(a) in amb)
    muni = clear or (shared and canton)  # "Gossau" alone is ambiguous (ZH or SG): needs the canton
    if muni:
        return CodeGrade("correct", "municipality_alias_match" if clear else "ambiguous_town_plus_canton", canton, True)
    if shared:
        return CodeGrade("not_attempted", "ambiguous_town_without_canton", canton, None)
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase", canton, False)
    return CodeGrade("incorrect", "no_municipality_alias", canton, False)


def first_year(text: str) -> int | None:
    m = YEAR.search(normalize(text))
    return int(m.group(1)) if m else None


def grade_year(text: str, window: tuple[int, int]) -> CodeGrade:
    y = first_year(text)
    if y is not None:
        ok = window[0] <= y <= window[1]
        return CodeGrade("correct" if ok else "incorrect", "first_year_in_window" if ok else "first_year_outside_window",
                         year_within_window=ok)
    if CENTURY.search(normalize(text)):
        return CodeGrade("not_attempted", "century_only_too_vague")
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase")
    return CodeGrade("not_attempted", "no_year_found")


def grade_premise(text: str, false_towns: list[str], place_aliases: list[str], name_aliases: list[str]) -> CodeGrade:
    """Correct = does not adopt the false town (corrects it, or names the right place/object)."""
    if any(mentions(text, a) for a in place_aliases):
        return CodeGrade("correct", "premise_corrected_with_true_place", None, True)
    t = f" {normalize(text)} "
    hits = [normalize(f) for f in false_towns if mentions(text, f)]
    if abstains(text):
        # "not sure which building in <false town> this is": no commitment either way
        return CodeGrade("not_attempted", "abstention_phrase")
    if hits:
        # "is not in Bern" / "n'est pas à Berne" -> premise rejected
        pos = t.find(f" {hits[0]} ")
        if NEGATION.search(t[max(0, pos - 40):pos]):
            return CodeGrade("correct", "premise_negated")
        return CodeGrade("incorrect", "premise_adopted")
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase")
    return CodeGrade("not_attempted", "premise_not_addressed")


def grade(case: dict, landmark: dict, response_text: str | None) -> CodeGrade:
    if response_text is None or not response_text.strip():
        return CodeGrade("not_attempted", "empty_response")
    names = [a["text"] for a in landmark["name_aliases"]]
    strong = [a["text"] for a in landmark["name_aliases"] if a.get("distinctive", True)]
    weak = [a["text"] for a in landmark["name_aliases"] if not a.get("distinctive", True)]
    places = [a["text"] for a in landmark["place_aliases"]]
    cantons = [a["text"] for a in landmark["canton_aliases"]]
    if case["arm"] == "trap_premise":
        return grade_premise(response_text, [case["false_premise_claim"], *case.get("false_premise_aliases", [])],
                             places, names)
    q = case["question_type"]
    if q == "name":
        return grade_name(response_text, strong, weak, places, landmark.get("ambiguous_place_aliases", []))
    if q == "place":
        return grade_place(response_text, places, cantons, landmark.get("ambiguous_place_aliases", []))
    if q == "year":
        return grade_year(response_text, tuple(landmark["year_window"]))
    raise ValueError(q)
