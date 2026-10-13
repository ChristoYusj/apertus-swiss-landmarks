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

from .normalize import TYPE_WORDS, normalize, specific_tokens, usable_alias

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


def hedged(text: str) -> bool:
    """An abstention phrase WITH a guess ("not sure, but it seems to be ..."): graded on what the guess says."""
    t = normalize(text)
    return bool(_ABSTAIN.search(t)) and bool(_GUESS.search(t))


# Fix v5 (pre-registered rule "vague answers = not attempted"): a hedged guess that names nothing specific
# ("Non sono sicuro, ma sembra una chiesa") is not an attempt. Capitalised words that are NOT names in the
# answers (German nouns, hedging vocabulary; listed from every capitalised mid-sentence word of the run):
GENERIC_CAPS = {
    "kanton", "gemeinde", "bild", "schweiz", "informationen", "suisse", "namen", "hinweise", "svizra", "svizzera",
    "gebaudes", "lage", "canton", "denkmals", "baujahr", "kennzeichnungen", "schweizer", "sie", "name", "bezeichnung",
    "details", "merkmale", "landmarken", "angabe", "europa", "ortsschilder", "zuordnung", "ort", "umgebung",
    "inschriften", "beschriftungen", "schilder", "orte", "architektur", "lokalisierung", "chantun", "kennzeichen",
    "baudaten", "jahr", "region", "alpen", "bauwerk", "uhr", "standort", "strassenschilder", "identifizierung", "alpi",
    "kontext", "sicherheit", "jahrhunderte", "elementen", "merkmalen", "erbauungsjahr", "steinbrucke", "herrenhaus",
    "kirchen", "angaben", "regionen", "architekturmerkmale", "see", "mittelalter", "abbildung", "gegend", "errichtung",
    "jahreszahl", "gemeinden", "recherche", "bahnhofs", "anwesen", "antwort", "wappen", "eisenbahnviadukt",
    "svitzerland", "svitzer", "quellen", "dokumente", "beschreibung", "aufschrift", "holzhaus", "holzbrucke",
    "wohnhaus", "dorfszene", "stadtansicht", "befestigungsanlage", "gasthaus", "fassade", "dach", "turmspitze",
    "volkskultur", "landschaft", "gewissheit", "epoche", "stil", "gotik", "romanik", "barock", "renaissance",
    "mittelalterliche", "europe", "europaische", "suisse", "italie", "image", "photo", "foto", "immagine", "unsicher",
    "informazioni", "information", "dettagli", "contesto", "funtauna", "chasa", "edifizi", "monument", "vischnanca",
    "swiss", "switzerland", "alps", "alpes", "mineralien", "museumsprasentation", "wehrturm", "wehrmauern",
    "stadtbefestigung", "bogenbrucke", "kirchturm", "dorf", "berg", "bergdorf", "altstadt", "landsitz", "landsitzes",
    # added in the second v5 audit (plurals and common nouns that looked like names)
    "burgen", "brucken", "kapellen", "turme", "schlosser", "hauser", "wehrturms", "muhlengebaude", "torhaus",
    "anlage", "aquadukt", "kirchengebaude", "sakralbau", "berglandschaft", "sehenswurdigkeit", "sprache", "hugel",
    "deutschschweiz", "zentralschweiz", "innerschweiz", "ostschweiz", "westschweiz", "vierwaldstattersee",
    "eisenbahnbrucke", "landmark", "weiler", "objekt", "institution", "tippfehler", "irrtum", "verwechslung",
    "beschriftung", "ortsangaben", "frage", "punkt", "punkte", "interesse", "fasnacht",
}
_SAINT_NAME = re.compile(r"\b(?:St|Sankt|San|Santa|Santo|Sant|Saint|Sainte|Ste|Sogn|Sontga|Son|SS|Santi|S)\.?[\s\-']+"
                         r"(?P<n>[A-ZÀ-Þ][\w'’-]+)")
_TOWN_CUE = re.compile(r"\b(?:Gemeinde|Stadt|Ortschaft|Dorf|commune|ville|village|comune|città|villaggio|paese|"
                       r"vischnanca|Vischnanca|citad|municipality|town)\s*:?\s+(?:(?:de|d'|di|da|von|of|du)\s*)?"
                       r"(?P<n>[A-ZÀ-Þ][\w'’-]+)")
# Nouns that anchor a proper name next to them ("Burg Neuburg", "Landwasser-Viadukt"). Unlike TYPE_WORDS this has
# no function words or adjectives ("der", "sein", "mittelalterliche" must never anchor a name).
TYPE_NOUNS = {
    "kirche", "kapelle", "chiesa", "cappella", "eglise", "chapelle", "baselgia", "caplutta", "chaplutta", "church",
    "chapel", "schloss", "burg", "burgruine", "castello", "castel", "chateau", "chaste", "castle", "turm", "torre",
    "tour", "tower", "brucke", "ponte", "pont", "punt", "bridge", "viadukt", "viadotto", "viaduc", "viaduct", "museum",
    "museo", "musee", "kloster", "abtei", "abbazia", "abbaye", "abbey", "convento", "couvent", "monastero", "monastere",
    "monastery", "palazzo", "palais", "palace", "rathaus", "municipio", "brunnen", "fontana", "fontaine", "fountain",
    "bahnhof", "stazione", "gare", "station", "kathedrale", "cattedrale", "cathedrale", "cathedral", "duomo",
    "basilica", "basilika", "oratorio", "oratorium", "ruine", "festung", "fortezza", "forte", "fort", "teatro",
    "theater", "theatre", "biblioteca", "bibliothek", "bibliotheque", "library", "collegiata", "collegiale",
    "santuario", "sanctuaire", "stiftskirche", "pfarrkirche", "klosterkirche", "munster", "dom", "kaserne",
}
# a capitalised word right after a locative preposition names a place; cantons, countries and generic words
# ("in Graubünden", "in Svizzera", "in Europa") are excluded by the caller and GENERIC_CAPS
_PREP_PLACE = re.compile(r"(?:\b(?:a|in|nel|nella|en|vicino a|près de)|(?<!\w)à)\s+(?P<n>[A-ZÀ-Þ][\w'’-]+)")
_BOLD = re.compile(r"\*\*([^*]{3,80})\*\*")
# Italian/French definite article + capitalised word mid-sentence: in these languages a capitalised noun after the
# article is a name ("il Castello di Mir"); German capitalises every noun, so German articles are not used.
_ROMANCE_DEF = re.compile(r"(?<![.!?:]\s)(?<![.!?:])\b(?:il|lo|la|gli|le|les|l['’])\s*(?P<n>[A-ZÀ-Þ][\w'’-]+)")
_QUOTED = re.compile(r"[«\"„“]([^»\"“”]{3,80})[»\"“”]")
_PREP = {"di", "de", "da", "von", "of", "du", "della", "del", "dal", "dalla", "des", "d", "l", "la", "le", "il", "dello",
         "dei", "degli", "delle", "dil", "dals", "der", "the"}


def _caps(text: str) -> list[tuple[str, str]]:
    """(original word, normalized) for every word."""
    return [(m.group(), normalize(m.group())) for m in re.finditer(r"[^\W_]+", text)]


def _is_name_word(orig: str, norm: str) -> bool:
    return (orig[:1].isupper() and len(norm) >= 3 and norm not in TYPE_WORDS and norm not in GENERIC_CAPS
            and not any(ch.isdigit() for ch in norm))


def _strip_echo(text: str, question: str | None) -> str:
    """Remove the name the QUESTION showed («Grimmenturm») from the answer: repeating it is not a claim."""
    if not question:
        return text
    for shown in re.findall(r"[«\"„“]\s*([^»\"“”]+?)\s*[»\"“”]", question):
        text = re.sub(re.escape(shown), " ", text, flags=re.I)
    return text


def specific_claim(text: str, gz=None, gold_canton: str | None = None, question: str | None = None) -> bool:
    """Does the answer commit to something checkable: a named object, a town, a foreign country or a wrong canton?
    The name shown in the question is ignored (an echo is not a claim)."""
    text = _strip_echo(text, question)
    if gz is not None:
        loc = gz.locate(text)
        if loc["kind"] == "abroad":
            return True
        if loc["kind"] == "swiss" and (loc["level"] == "municipality" or (loc.get("canton") and loc["canton"] != gold_canton)):
            return True
    if any(_is_name_word(m.group("n"), normalize(m.group("n"))) for m in _SAINT_NAME.finditer(text)):
        return True
    for m in _TOWN_CUE.finditer(text):             # "in der Gemeinde Schiedhalden" (a town the gazetteer lacks)
        if _is_name_word(m.group("n"), normalize(m.group("n"))):
            return True
    for m in _PREP_PLACE.finditer(text):           # "situà a Cuera", "forse in Sud America": a named place
        n = m.group("n")
        if _is_name_word(n, normalize(n)) and not (gz is not None and gz.locate(n)["kind"] != "none"
                                                   and gz.locate(n).get("level") != "municipality"):
            return True
    for q in _QUOTED.findall(text) + _BOLD.findall(text):
        if any(_is_name_word(o, n) for o, n in _caps(q)):
            return True
    for m in _ROMANCE_DEF.finditer(text):           # "il Castello di Mir", "l'Abbazia di Ettal" (not "una chiesa")
        if _is_name_word(m.group("n"), normalize(m.group("n"))) or normalize(m.group("n")) in TYPE_NOUNS:
            return True
    w = _caps(text)
    for i, (o, n) in enumerate(w):
        if n in TYPE_NOUNS:
            j = i + 1
            while j < len(w) and w[j][1] in _PREP:
                j += 1
            if j < len(w) and j - i <= 2 and _is_name_word(*w[j]):
                return True                       # "Castello di Vaduz", "Burg Neuburg"
        if i > 0 and i + 1 < len(w) and _is_name_word(o, n) and w[i + 1][1] in TYPE_NOUNS:
            return True                           # "Landwasser-Viadukt", "Museum Rietberg" (other order)
    return False


def mentions(text: str, alias: str) -> bool:
    a = normalize(alias)
    return bool(a) and f" {a} " in f" {normalize(text)} "


def _specific(aliases: list[str]) -> list[str]:
    return [a for a in aliases if specific_tokens(a)]


def _right_town(text: str, hits: list[str], place_aliases, ambiguous, canton_aliases) -> bool:
    """Is the right municipality named, in the answer or inside the matched name? A town name shared by two
    municipalities (Holderbank AG/SO) counts only together with the right canton."""
    amb = {normalize(a) for a in ambiguous}
    amb_tokens = {t for a in amb for t in a.split()}
    canton = any(mentions(text, c) for c in canton_aliases)
    if any(mentions(text, p) for p in place_aliases if normalize(p) not in amb):
        return True
    if canton and any(mentions(text, p) for p in place_aliases if normalize(p) in amb):
        return True
    town_tokens = {t for p in place_aliases if normalize(p) not in amb for t in specific_tokens(p)} - amb_tokens
    in_name = set().union(*(set(normalize(a).split()) for a in hits)) if hits else set()
    return bool(town_tokens & in_name) or (canton and bool(amb_tokens & in_name))


def grade_name(text: str, strong: list[str], weak: list[str] = (), place_aliases: list[str] = (),
               ambiguous: list[str] = (), gz=None, gold_canton: str | None = None, canton_aliases: list[str] = (),
               gold_bfs: int | None = None, question: str | None = None) -> CodeGrade:
    """strong = distinctive names; weak = saint/type names shared by many buildings (need the town).
    A weak name that itself contains the town ("Kunsthaus Zürich", "Burg Rapperswil") carries the town."""
    if any(mentions(text, a) for a in _specific(strong)):
        return CodeGrade("correct", "name_alias_match")
    hits = [a for a in weak if usable_alias(a) and mentions(text, a)]
    if hits:
        if _right_town(text, hits, place_aliases, ambiguous, canton_aliases):
            return CodeGrade("correct", "name_alias_plus_town_match")
        # a generic name with ANOTHER town ("Kunsthaus Aarau" for Kunsthaus Zürich) is a wrong answer
        if gz is not None:
            loc = gz.locate(text)
            if loc["kind"] == "abroad" or (loc["kind"] == "swiss" and loc["level"] == "municipality"
                                           and loc.get("bfs_now") and gold_bfs not in loc["bfs_now"]):
                return CodeGrade("incorrect", "nondistinctive_name_wrong_town")
        # e.g. "St. Antonius chapel" without the town: could be any of many chapels
        return CodeGrade("not_attempted", "nondistinctive_name_without_town")
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase")
    if hedged(text) and not specific_claim(text, gz, gold_canton, question):
        return CodeGrade("not_attempted", "hedged_guess_names_nothing_specific")
    return CodeGrade("incorrect", "no_name_alias")


_CANTON_WORDS = {"kanton", "kantons", "canton", "cantons", "cantone", "chantun"}
_OF = {"de", "di", "da", "del", "dei", "des", "du", "dal", "dil",
       "e", "est", "ist", "is", "es", "esch"}   # "il chantun è Turitg", "der Kanton ist Zürich"


def _dedications(s: str) -> set[str]:
    """Saints' names after a saint marker ("Sant'Antonio Abate" -> {"antonio"}; "Santo Antonio" -> {"antonio"})."""
    return {normalize(m.group("n")) for m in _SAINT_NAME.finditer(s)} | \
           {t2 for t1, t2 in zip(normalize(s).split(), normalize(s).split()[1:]) if t1 == "st" and len(t2) >= 3}


def mentions_as_town(text: str, alias: str) -> bool:
    """Like mentions(), but "chantun Turitg" / "Kanton Zürich" names the canton, not the town of that name."""
    a = normalize(alias).split()
    t = normalize(text).split()
    if not a:
        return False
    for i in range(len(t) - len(a) + 1):
        if t[i:i + len(a)] == a:
            prev = t[i - 1] if i >= 1 else ""
            prev2 = t[i - 2] if i >= 2 else ""
            if prev in _CANTON_WORDS or (prev in _OF and prev2 in _CANTON_WORDS):
                continue
            return True
    return False


def other_object(text: str, name_aliases: list[str], place_aliases: list[str]) -> bool:
    """Does the answer identify a DIFFERENT object than the gold one (another church, another castle)? A type word
    plus the town ("Fortezza di Airolo", "Palaz dal comun da Bellinzona") is not a different object."""
    if any(mentions(text, a) for a in name_aliases if usable_alias(a)):
        return False
    town = {t for p in place_aliases for t in normalize(p).split()}

    def other_name(o: str) -> bool:
        n = normalize(o)
        return _is_name_word(o, n) and n not in town and n not in TYPE_NOUNS

    def dedication(o: str) -> bool:                # a saint/dedication names a church ("S. Maria Assunta")
        n = normalize(o)
        return o[:1].isupper() and len(n) >= 3 and n not in town and n not in GENERIC_CAPS

    if any(dedication(m.group("n")) for m in _SAINT_NAME.finditer(text)):
        return True                               # "chiesa di San Martino a Poschiavo" (gold: San Vittore)
    for q in _QUOTED.findall(text) + _BOLD.findall(text):
        if any(other_name(o) for o, _ in _caps(q)):
            return True
    w = _caps(text)
    for i, (o, n) in enumerate(w):
        if n in TYPE_NOUNS:
            j = i + 1
            while j < len(w) and w[j][1] in _PREP:
                j += 1
            if j < len(w) and j - i <= 2 and other_name(w[j][0]):
                return True                       # "Palazzo dei Capitani"
    return False


def grade_place(text: str, place_aliases: list[str], canton_aliases: list[str],
                ambiguous: list[str] = (), gz=None, gold_canton: str | None = None,
                question: str | None = None, name_aliases: list[str] = (), check_object: bool = False) -> CodeGrade:
    """check_object (photo questions, decision of the team lead 13 Oct): the right town with a DIFFERENT object
    ("la chiesa di San Martino a Poschiavo" for San Vittore) is incorrect."""
    amb = {normalize(a) for a in ambiguous}
    canton = any(mentions(text, a) for a in canton_aliases)
    clear = any(mentions_as_town(text, a) for a in place_aliases if normalize(a) not in amb)
    shared = any(mentions_as_town(text, a) for a in place_aliases if normalize(a) in amb)
    muni = clear or (shared and canton)  # "Gossau" alone is ambiguous (ZH or SG): needs the canton
    if muni:
        if check_object and other_object(text, name_aliases, place_aliases):
            return CodeGrade("incorrect", "right_town_wrong_object", canton, True)
        return CodeGrade("correct", "municipality_alias_match" if clear else "ambiguous_town_plus_canton", canton, True)
    if shared:
        return CodeGrade("not_attempted", "ambiguous_town_without_canton", canton, None)
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase", canton, False)
    # fix v5, the right municipality was not named. Checkable (-> incorrect): another town (known to the
    # gazetteer or not), a foreign country, a wrong canton, a named object. Not checkable (-> not attempted):
    # the right canton alone; and, in a HEDGED answer, "possibly in Switzerland" / "in Europa" / nothing.
    # An unhedged bare answer stays incorrect ("Sveti Stefan", "Riviera": places, just not in the gazetteer).
    if not specific_claim(text, gz, gold_canton, question):
        loc = gz.locate(_strip_echo(text, question)) if gz is not None else {"kind": "none"}
        if loc["kind"] == "swiss" and loc["level"] == "canton" and loc.get("canton") == gold_canton:
            return CodeGrade("not_attempted", "right_canton_only", canton, None)
        if hedged(text):
            return CodeGrade("not_attempted", "hedged_guess_names_no_place", canton, None)
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


def grade_premise(text: str, false_towns: list[str], place_aliases: list[str], name_aliases: list[str],
                  gz=None, question: str | None = None) -> CodeGrade:
    """Incorrect = adopts the false town, OR names a landmark that is not the gold one (decision of the team lead,
    13 Oct; the rule "premise_adopted" alone is the pre-registered H4 measure, kept as the code_rule).
    Correct = names the true place or the right landmark, or rejects the false town. Not attempted = declines."""
    if any(mentions_as_town(text, a) for a in place_aliases):
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
    if any(mentions(text, a) for a in name_aliases if usable_alias(a)):
        return CodeGrade("correct", "right_landmark_named")
    if _dedications(text) & {d for a in name_aliases for d in _dedications(a)}:
        # "Die Kirche Santo Antonio" for Sant'Antonio Abate: the right saint without the town (as for Q1)
        return CodeGrade("not_attempted", "same_dedication_without_town")
    false_tok = {x for f in false_towns for x in normalize(f).split()}
    named = specific_claim(text, gz, None, question) or any(
        i > 0 and _is_name_word(o, n) and n not in false_tok for i, (o, n) in enumerate(_caps(text)))
    if named:
        return CodeGrade("incorrect", "wrong_landmark_named")   # "Die Abtei Saint-Maurice" (gold: San Gian, Celerina)
    return CodeGrade("not_attempted", "premise_not_addressed")


def grade(case: dict, landmark: dict, response_text: str | None, gz=None) -> CodeGrade:
    """gz: the dataset gazetteer (analysis.Gazetteer); without it the location-based rules of fix v5 are skipped."""
    if response_text is None or not response_text.strip():
        return CodeGrade("not_attempted", "empty_response")
    names = [a["text"] for a in landmark["name_aliases"]]
    strong = [a["text"] for a in landmark["name_aliases"] if a.get("distinctive", True)]
    weak = [a["text"] for a in landmark["name_aliases"] if not a.get("distinctive", True)]
    places = [a["text"] for a in landmark["place_aliases"]]
    cantons = [a["text"] for a in landmark["canton_aliases"]]
    if case["arm"] == "trap_premise":
        return grade_premise(response_text, [case["false_premise_claim"], *case.get("false_premise_aliases", [])],
                             places, names, gz, case.get("question_text"))
    q = case["question_type"]
    if q == "name":
        return grade_name(response_text, strong, weak, places, landmark.get("ambiguous_place_aliases", []), gz,
                          landmark.get("canton_code"), cantons,
                          int(landmark["municipality_bfs"]) if landmark.get("municipality_bfs") else None,
                          case.get("question_text"))
    if q == "place":
        return grade_place(response_text, places, cantons, landmark.get("ambiguous_place_aliases", []), gz,
                           landmark.get("canton_code"), case.get("question_text"), names,
                           check_object=case["arm"] != "text_only")
    if q == "year":
        return grade_year(response_text, tuple(landmark["year_window"]))
    raise ValueError(q)
