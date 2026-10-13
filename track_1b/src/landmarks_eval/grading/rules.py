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

from . import contradict as C
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
    # added 13 Oct after the second independent review read every answer graded incorrect (242 refusals missed)
    r"non e sicuro", r"(bin|sind) (mir |uns )?nicht (ganz )?sicher",
    r"nicht (eindeutig |sicher |genau )?aus dem bild( allein)? (ableitbar|bestimmbar|zu bestimmen|erkennbar)",
    r"\bableitbar\b", r"mir nicht bekannt", r"(ist|sind) .{0,70}nicht moglich", r"je ne trouve pas", r"ne dispose pas d", r"non identifiable",
    r"difficile de (determiner|dire|identifier)", r"n est pas (immediatement )?claire?", r"je n ai pas d informations",
    r"nessuna informaziun", r"betga? segir", r"betg visibel", r"\bnon identifitgabel\b", r"non indicheda",
    r"non inditga",                                    # Sursilvan "Non inditgà" (review 3)
    # review 4: every spelling of "non identifi..." and a one-word "nothing" as the whole answer
    r"\bnon identifi\w*", r"^\s*(nin|nagin|nagina|nagut|nichts|keine?|rien|aucune?|niente|nessun[oa]?|none|nothing)\s*$",
    r"impossible (de|d) (donner|indiquer|fournir|nommer|preciser)",
    # the 70B's one-word Romansh answer "Nesgir" (4x) is its "Na segir" (not sure) run together; whole answer only
    r"^\s*nesgir\s*$",
]
# "not sure, BUT it is X": a contrast after the abstention introduces a guess (graded on X, see _contrast_claim)
_CONTRAST = re.compile(r"\b(ma|mais|aber|but|pero|però|tuttavia|however|cependant|jedoch|toutefois)\b", re.I)
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


def _abstain_phrase(text: str) -> bool:
    return bool(_ABSTAIN.search(normalize(text)))


def _contrast_claim(text: str, gz=None, gold_canton: str | None = None, question: str | None = None) -> bool:
    """"Non sono sicuro, ma l'edificio è il Castello di Predjama": the part after the contrast names something."""
    m = _CONTRAST.search(text)
    return bool(m) and specific_claim(text[m.end():], gz, gold_canton, question)


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
    # added 13 Oct from the list of every word that made names_anything() fire (review 2): common nouns, mostly
    # Romansh/Latin/English type words ("Tgesa d'uras" = clock house, "Clutger" = bell tower, "Covered Bridge")
    "tgesa", "chapella", "clutger", "colonna", "mines", "covered", "prieure", "museu", "cultura", "ffs", "cff", "sbb",
    "bunker", "chalet", "menhir", "steinmenhir", "statua", "horologium", "fontane", "brunnenanlage", "claustrum",
    "teatre", "teater", "rovine", "ruinas",
    # review 3: the same audit over every claim branch (type-noun anchor, article, name+noun), both models
    "fundaziun", "gruppa", "posta", "parrocchia", "muntogna", "corporaziun", "maestros", "chappel",
    "stadtverwaltung", "uhren", "uhrengebaude", "dudelspieler", "dudelspielers", "mercato", "centrale", "centrala",
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
# "dédiée à Cosmas", "dedicata a San Rocco", "geweiht an": the preposition introduces a saint, not a place
_DEDICATED = re.compile(r"(d[ée]di[ée]e?s?|consacr[ée]e?s?|dedicat[aoie]|dedicad[ao]s?|dedicaus?|geweiht|dedicated)\s*$", re.I)


def _place_preps(text: str):
    return [m for m in _PREP_PLACE.finditer(text) if not _DEDICATED.search(text[max(0, m.start() - 20):m.start()])]
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
    """Remove the name the QUESTION showed («Grimmenturm») from the answer: repeating it is not a claim. A word of
    the shown name is also removed when the answer quotes it on its own ("«Champ-Pittet»"), but NOT when the answer
    states it as the place ("in der Gemeinde Tarasp" for «Schloss Tarasp»: Tarasp is no longer a municipality, so
    that is a claim; fix of 13 Oct, word-by-word stripping everywhere had hidden it)."""
    if not question:
        return text
    for shown in re.findall(r"[«\"„“]\s*([^»\"“”]+?)\s*[»\"“”]", question):
        text = re.sub(re.escape(shown), " ", text, flags=re.I)
        words = [w for w in re.findall(r"[^\W\d_][\w'’-]{2,}", shown) if w[:1].isupper()]

        def unquote(m: re.Match) -> str:
            q = m.group(0)
            for w in words:
                q = re.sub(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", " ", q)
            return q
        text = re.sub(r"[«\"„“][^»\"“”]*[»\"“”]", unquote, text)
    return text


SWITZERLAND = {"schweiz", "suisse", "svizzera", "svizra", "switzerland", "svizzer", "schwiiz"}
# first words of a sentence that are never names ("Quai è ...", "Questa è ...", "Ce bâtiment ...")
STARTERS = {"quai", "quei", "quel", "quella", "quello", "questa", "questo", "quest", "ce", "cet", "cette", "ceci",
            "cela", "il", "la", "le", "les", "lo", "das", "dies", "diese", "dieser", "dieses", "es", "er", "sie", "this",
            "that", "it", "there", "hier", "voici", "ecco", "si", "sa", "el", "ella", "elle", "je", "ich", "non", "nua",
            "wo", "ou", "dove", "where", "oui", "ja", "nein", "betg", "un", "una", "uno", "une", "ein", "eine", "the",
            "die", "der", "dal", "dalla", "en", "in", "im", "a", "au", "nel", "nella", "gemeinde", "kanton", "commune",
            "comune", "vischnanca", "chantun", "canton", "cantone", "ort", "lieu", "luogo", "lieu", "situ", "situa",
            # sentence-initial connectives ("Sans plus de contexte ...", "Cependant, ..."), added 13 Oct
            "sans", "cependant", "toutefois", "malheureusement", "ohne", "leider", "jedoch", "aber", "senza",
            "tuttavia", "purtroppo", "however", "without", "unfortunately", "quests", "questas"}


# an Alpine area may be Switzerland: "in Italia o in un'area alpina" offers Switzerland too (review 4)
ALPINE = {"alpi", "alpen", "alpes", "alps", "alpina", "alpino", "alpine", "alpin", "alpinen", "alpini", "alpins"}
_NEG_BEFORE = re.compile(r"\b(pas|nicht|non|not|betg|kein|keine|nessun|aucun)\b(?:\W+\w+){0,2}\W*$")


def _foreign_claim(text: str, gz) -> bool:
    """"Probabilmente in Italia" contradicts a Swiss landmark; "in Italia o in Svizzera" (or "... o in un'area
    alpina") offers Switzerland too, but "pas en Suisse" does not."""
    if gz is None:
        return False
    if any(k == "country" for m in gz.mentions(text) for k, _ in m["payloads"]):
        t = f" {normalize(text)} "
        for w in SWITZERLAND | ALPINE:
            for m in re.finditer(f" {w} ", t):
                if not _NEG_BEFORE.search(t[:m.start() + 1]):
                    return False
        return True
    return False


def _committed_abroad(text: str, gz, question: str | None) -> bool:
    """A sentence WITHOUT an abstention phrase that places the landmark abroad, in an answer that also declines
    ("Je ne suis pas sûr. ... Sasso Corbaro est un lieu en Lombardie, en Italie.")."""
    t = _strip_echo(text, question)
    return any(not _abstain_phrase(s) and _foreign_claim(s, gz) for s in re.split(r"(?<=[.!?;])\s+|\n", t))


def _swiss_area(word: str, gz) -> bool:
    """A canton, a country or "Switzerland": an area, not a municipality or an object."""
    if normalize(word) in SWITZERLAND:
        return True
    if gz is None:
        return False
    loc = gz.locate(word)
    return loc["kind"] == "abroad" or loc["kind"] == "switzerland_only" or (loc["kind"] == "swiss" and loc["level"] == "canton")


def name_evidence(text: str, gz=None) -> str | None:
    """The first name in the answer (a capitalised word that is not a type word, a generic noun, an area or a
    sentence opener), or None. "Kapelle", "Chasa da baselgia", "In der Schweiz." name nothing; "Neuthal, Kanton
    Zürich", "Sveti Stefan" do. Saints' dedications count as names ("Chiesa di Santa Maria Assunta")."""
    if _dedications(text):
        return "dedication"
    for sent in re.split(r"(?<=[.!?;:])\s+|\n", text):
        sent = re.sub(r"(?<=[a-zß-ÿ]{3})(?=[A-ZÀ-Þ])", " ", sent)   # "chantunSurselva" (a missing space), not "MInF5"
        toks = list(re.finditer(r"[^\W_][\w-]*", sent))   # "Porte d'Enfer" -> "Porte", "d", "Enfer"
        for i, m in enumerate(toks):
            w = m.group()
            n = normalize(w)
            if not w[:1].isupper() or any(ch.isdigit() for ch in w):
                continue
            if i > 0 and i + 1 < len(toks) and sent[m.end():toks[i + 1].start()].isspace():
                # review 3: two capitalised words in mid-sentence form a name even if each alone is a function or
                # short word ("Chaplutta da Sur En"); mid-sentence capitals are the signal in all four languages
                w2 = toks[i + 1].group()
                pair = [normalize(w), normalize(w2)]
                if (w2[:1].isupper() and not any(ch.isdigit() for ch in w2)
                        and not any(p in GENERIC_CAPS or p in TYPE_NOUNS for p in pair)
                        and all(p not in TYPE_WORDS or len(p) <= 3 for p in pair)   # not "Römisch Katholische"
                        and not any(_swiss_area(x, gz) for x in (w, w2))):
                    return f"{w} {w2}"
            if len(n) < 3 or n in TYPE_WORDS or n in GENERIC_CAPS or (i == 0 and n.split()[0] in STARTERS) or n in STARTERS:
                continue
            if all(p in TYPE_WORDS or p in GENERIC_CAPS or len(p) < 3 for p in n.split()):
                continue                                # "Uhren-Turm": every part is a common noun (review 3)
            if _swiss_area(w, gz):
                continue
            return w
    return None


def names_anything(text: str, gz=None) -> bool:
    return name_evidence(text, gz) is not None


# a lowercase adjective made from a place name right after a building noun ("Musée gruérien", "Musée jurassien")
_PLACE_ADJ = re.compile(r"(ien|ienne|ois|oise|ais|aise|ese|esi|ense|ensi)$")


def claim_evidence(text: str, gz=None, gold_canton: str | None = None, question: str | None = None) -> str | None:
    """What the answer commits to that can be checked (a named object, a town, a foreign country, a wrong canton),
    as "<branch>:<word>", or None. The name shown in the question is ignored (an echo is not a claim)."""
    text = _strip_echo(text, question)
    if _foreign_claim(text, gz):
        return "country"
    if gz is not None:
        loc = gz.locate(text)
        if loc["kind"] == "swiss" and (loc["level"] == "municipality" or (loc.get("canton") and loc["canton"] != gold_canton)):
            return f"gazetteer:{loc.get('name')}"
        named_cantons = {p["canton"] for m in gz.mentions(text) if not any(k == "municipality" for k, _ in m["payloads"])
                         for k, p in m["payloads"] if k == "canton"}
        if len(named_cantons) >= 2:               # "Kanton Graubünden oder Wallis": competing candidates
            return "two_cantons"
    for m in _SAINT_NAME.finditer(text):
        if _is_name_word(m.group("n"), normalize(m.group("n"))):
            return f"saint:{m.group('n')}"
    for m in _TOWN_CUE.finditer(text):             # "in der Gemeinde Schiedhalden" (a town the gazetteer lacks)
        if _is_name_word(m.group("n"), normalize(m.group("n"))):
            return f"town_cue:{m.group('n')}"
    for m in _place_preps(text):           # "situà a Cuera", "forse in Sud America": a named place
        n = m.group("n")
        if _is_name_word(n, normalize(n)) and not (gz is not None and gz.locate(n)["kind"] != "none"
                                                   and gz.locate(n).get("level") != "municipality"):
            return f"prep:{n}"
    for q in _QUOTED.findall(text) + _BOLD.findall(text):
        for o, n in _caps(q):
            if _is_name_word(o, n):
                return f"quoted:{o}"
    for m in _ROMANCE_DEF.finditer(text):           # "il Teatro alla Scala", "l'Abbazia di Ettal" (not "una chiesa")
        n = m.group("n")
        if _is_name_word(n, normalize(n)) and not _swiss_area(n, gz):   # "dans le Tessin" is an area, not a name
            return f"article:{n}"
    # the building-noun anchor never crosses a bracket or comma ("Rathaus (Stadtverwaltung)" is a gloss, review 3)
    for seg in re.split(r"[()\[\],;:.!?/]", text):
        w = _caps(seg)
        for i, (o, n) in enumerate(w):
            if n in TYPE_NOUNS:
                j = i + 1
                while j < len(w) and w[j][1] in _PREP:
                    j += 1
                if j < len(w) and j - i <= 2 and _is_name_word(*w[j]):
                    return f"type_noun:{w[j][0]}"     # "Castello di Vaduz", "Burg Neuburg"
                if j == i + 1 and j < len(w) and w[j][0][:1].islower() and _PLACE_ADJ.search(w[j][1]) \
                        and w[j][1] not in TYPE_WORDS and w[j][1] not in GENERIC_CAPS:
                    return f"place_adjective:{w[j][0]}"   # "Musée gruérien" (review 3)
            if i > 0 and i + 1 < len(w) and _is_name_word(o, n) and w[i + 1][1] in TYPE_NOUNS:
                return f"name_type_noun:{o}"      # "Landwasser-Viadukt", "Museum Rietberg" (other order)
    return None


def specific_claim(text: str, gz=None, gold_canton: str | None = None, question: str | None = None) -> bool:
    return claim_evidence(text, gz, gold_canton, question) is not None


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


_CONJ = {"e", "ed", "et", "und", "and"}
_ARTICLES = {"il", "lo", "la", "l", "i", "gli", "le", "les", "un", "una", "uno", "une", "der", "die", "das", "dem", "den",
             "des", "ein", "eine", "einem", "einer", "the", "a", "an", "ses", "son", "sa", "sein", "seine", "seinem", "suo",
             "sua", "suoi", "its", "il", "ils", "elle", "es", "si", "sono", "est", "ist"}


def _word_pairs(text: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"[^\W_]+", text):
        for piece in normalize(m.group()).split():
            out.append((m.group(), piece))
    return out


def mentions_whole(text: str, alias: str) -> bool:
    """The alias occurs as a complete name, not as the start of a longer, different one: "Museo cantonale d'arte
    e di storia" does not name "Museo Cantonale d'Arte" (team-lead rule, 13 Oct). A conjunction followed by an
    article starts a new phrase ("... de la Justice et la place de la Palud") and does not count."""
    a = normalize(alias).split()
    w = _word_pairs(text)
    if not a:
        return False
    for i in range(len(w) - len(a) + 1):
        if [p for _, p in w[i:i + len(a)]] == a:
            j = i + len(a)
            if j + 1 < len(w) and w[j][0] in _CONJ and normalize(w[j + 1][0]) not in _ARTICLES:
                continue                          # "... d'arte e di storia": a longer name
            return True
    return False


def extended_alias(text: str, alias: str) -> bool:
    """The alias occurs only as the start of a longer, different name ("Museo cantonale d'arte e di storia" for
    "Museo Cantonale d'Arte"): under the team lead's similar-name rule (13 Oct) that is a wrong answer."""
    return mentions(text, alias) and not mentions_whole(text, alias)


def _other_town(text: str, gz, gold_bfs: int | None, place_aliases) -> bool:
    """The answer names a municipality (known to the gazetteer or not) or a country other than the gold one."""
    if _foreign_claim(text, gz):
        return True
    if gz is not None:
        loc = gz.locate(text)
        if loc["kind"] == "swiss" and loc["level"] == "municipality" and loc.get("bfs_now") and gold_bfs not in loc["bfs_now"]:
            return True
    gold_tok = {t for p in place_aliases for t in normalize(p).split()}
    for m in _place_preps(text) + list(_TOWN_CUE.finditer(text)):   # "Kirche St. Peter in Oberndorf"
        n = m.group("n")
        if gz is not None and gz.locate(n)["kind"] != "none":
            continue                              # a known place: the gazetteer decided above (Ardez is now Scuol)
        if _is_name_word(n, normalize(n)) and normalize(n) not in gold_tok:
            return True
    return False


def _strip_places(text: str, place_aliases) -> str:
    """Remove the GOLD town from the answer: "una chiesa a Lugano" for a Lugano landmark claims no wrong place."""
    for p in sorted(place_aliases, key=len, reverse=True):
        if len(p) >= 3:
            text = re.sub(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", " ", text, flags=re.I)
    return text


def grade_name(text: str, strong: list[str], weak: list[str] = (), place_aliases: list[str] = (),
               ambiguous: list[str] = (), gz=None, gold_canton: str | None = None, canton_aliases: list[str] = (),
               gold_bfs: int | None = None, question: str | None = None, gold_types: set[str] = frozenset()) -> CodeGrade:
    """strong = distinctive names; weak = saint/type names shared by many buildings (need the town).
    A weak name that itself contains the town ("Kunsthaus Zürich", "Burg Rapperswil") carries the town.
    gold_types: the landmark's building classes (contradict.gold_type_classes); a vague answer that states another
    type or denomination contradicts the gold and is incorrect (review 4)."""

    def vague(rule: str) -> CodeGrade:
        if C.type_conflict(rest, gold_types):
            return CodeGrade("incorrect", "type_contradicts_gold")
        if C.confession_conflict(text, [*strong, *weak]):
            return CodeGrade("incorrect", "confession_contradicts_gold")
        return CodeGrade("not_attempted", rule)
    if any(mentions_whole(text, a) for a in _specific(strong)):
        return CodeGrade("correct", "name_alias_match")
    hits = [a for a in weak if usable_alias(a) and mentions_whole(text, a)]
    if hits:
        if _right_town(text, hits, place_aliases, ambiguous, canton_aliases):
            return CodeGrade("correct", "name_alias_plus_town_match")
        # a generic name with ANOTHER town ("Kunsthaus Aarau" for Kunsthaus Zürich) is a wrong answer
        if _other_town(text, gz, gold_bfs, place_aliases):
            return CodeGrade("incorrect", "nondistinctive_name_wrong_town")
        # e.g. "St. Antonius chapel" without the town: could be any of many chapels
        return CodeGrade("not_attempted", "nondistinctive_name_without_town")
    rest = _strip_places(text, place_aliases)      # the right town alone is no wrong claim
    if abstains(text) and not _contrast_claim(rest, gz, gold_canton, question):
        return CodeGrade("not_attempted", "abstention_phrase")
    if any(extended_alias(text, a) for a in _specific(strong)) or any(
            extended_alias(text, a) for a in weak if usable_alias(a)):
        return CodeGrade("incorrect", "similar_but_different_name")
    gold_ded = {d for a in [*strong, *weak] for d in _dedications(a)}
    if gold_ded and _dedications(text) & gold_ded:
        # the gold saint in another spelling ("Pfarrkirche St. Martin" for "Kirche S. Martin"): like a weak name,
        # it needs the town (review 3; the same rule as same_dedication_without_town for premise traps)
        if _right_town(text, [], place_aliases, ambiguous, canton_aliases):
            return CodeGrade("correct", "same_dedication_plus_town")
        if _other_town(text, gz, gold_bfs, place_aliases):
            return CodeGrade("incorrect", "same_dedication_wrong_town")
        other = _strip_dedications(rest)               # "Église Saint-Pierre de Neuilly-sur-Seine": another place
        if specific_claim(other, gz, gold_canton, question) or (not _abstain_phrase(text) and names_anything(other, gz)):
            return CodeGrade("incorrect", "same_dedication_other_name")
        return vague("same_dedication_without_town")
    claim = specific_claim(rest, gz, gold_canton, question)
    if _abstain_phrase(text) and not claim:
        return vague("hedged_guess_names_nothing_specific")
    if not _abstain_phrase(text) and not claim and not names_anything(rest, gz):
        # pre-registered "vague answers = not attempted": "Kapelle", "Bahnhof", "Questa è una chiesa." -- unless the
        # stated type contradicts the gold (review 4)
        return vague("names_nothing")
    return CodeGrade("incorrect", "no_name_alias")


_CANTON_WORDS = {"kanton", "kantons", "canton", "cantons", "cantone", "chantun"}
_OF = {"de", "di", "da", "del", "dei", "des", "du", "dal", "dil",
       "e", "est", "ist", "is", "es", "esch"}   # "il chantun è Turitg", "der Kanton ist Zürich"


# one saint, several languages (review 3: "St. Antonius" = "Sant'Antonio", "Giachem" = "Jakob"); first = key
_SAINT_FORMS = [
    "martin martino martinus marti", "antonio anton antonius antoine antoni", "peter pietro pierre peder pieder petrus",
    "stephan stefano stephanus etienne steffan stefan", "jakob giacomo jacques giachem jacobus jakobus giachen",
    "johannes johann giovanni jean gion gian john", "lorenz lorenzo laurentius laurent luregn",
    "michael michele michel", "nikolaus niklaus nicolao nicolaus nicolas niclau nicola", "viktor vittore victor",
    "sebastian sebastiano sebastien bastian", "georg giorgio georges george", "paul paolo paulus", "andreas andrea andre",
    "bartholomaus bartolomeo barthelemy", "mauritius maurizio maurice moritz", "gallus gallo gall",
    "josef giuseppe joseph", "anna anne", "katharina caterina catherine", "rochus rocco roch", "karl carlo charles",
    "maria marie mary", "theodul teodulo theodule joder", "ulrich ulderico udalric", "valentin valentino valentinus",
]
_SAINT_CANON = {f: forms.split()[0] for forms in _SAINT_FORMS for f in forms.split()}


# Mary Magdalene is not Mary ("Sainte-Marie-Madeleine", "Santa Maria Maddalena", "Sontga Maria Madlaina")
_MAGDALENE = re.compile(r"\bMari[ae][\s\-]+(?:Madd?alena|Madeleine|Magdalena|Madlaina)\b", re.I)
# epithets that belong to the dedication ("San Giovanni Battista", "Sant'Antonio Abate")
_EPITHET = r"(?:[\s\-]+(?:Battista|Baptista|Baptiste|Battesta|Abate|Abt|Apostolo|Apôtre|Evangelista|Évangéliste|" \
           r"Evangelist|Assunta|Maggiore|Martire|Vescovo|Magno|Täufer))*"


def _dedications(s: str) -> set[str]:
    """Saints' names after a saint marker, in one spelling for all languages ("Sant'Antonio Abate" -> {"antonio"},
    "St. Antonius" -> {"antonio"}, "Saint-Jean-Baptiste" -> {"johannes"})."""
    s = _MAGDALENE.sub("Magdalena", s)
    raw = {normalize(m.group("n")) for m in _SAINT_NAME.finditer(s)} | \
          {t2 for t1, t2 in zip(normalize(s).split(), normalize(s).split()[1:]) if t1 == "st" and len(t2) >= 3}
    return {_SAINT_CANON.get(d.split()[0], d) if d else d for d in raw}


def _strip_dedications(s: str) -> str:
    """The answer without its saints' dedications: what else does it name?"""
    s = _MAGDALENE.sub(" ", s)
    s = re.sub(_SAINT_NAME.pattern + _EPITHET, " ", s)
    return re.sub(r"\b(?:St|st)\.?\s+[A-ZÀ-Þ][\w'’-]+" + _EPITHET, " ", s)


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
    gold_ded = {d for a in name_aliases for d in _dedications(a)}   # "Collegiata di San Vittore" for San Vittore

    def other_name(o: str) -> bool:
        n = normalize(o)
        return _is_name_word(o, n) and n not in town and n not in TYPE_NOUNS and _SAINT_CANON.get(n, n) not in gold_ded

    def dedication(o: str) -> bool:                # a saint/dedication names a church ("S. Maria Assunta")
        n = normalize(o)
        return (o[:1].isupper() and len(n) >= 3 and n not in town and n not in GENERIC_CAPS
                and _SAINT_CANON.get(n, n) not in gold_ded)

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
    if abstains(text) and not _contrast_claim(text, gz, gold_canton, question):
        if _committed_abroad(text, gz, question):  # "pas sûr ... Sasso Corbaro est un lieu en Lombardie, Italie."
            return CodeGrade("incorrect", "abstention_but_located_abroad", canton, False)
        return CodeGrade("not_attempted", "abstention_phrase", canton, False)
    if C.region_conflict(text, gold_canton):       # "Zentralschweiz" for a landmark in Bern (review 4)
        return CodeGrade("incorrect", "region_excludes_gold_canton", canton, False)
    # the right municipality was not named. Checkable (-> incorrect): another town (known to the gazetteer or
    # not), a village instead of the municipality (team-lead rule), a foreign country, a wrong canton, several
    # cantons, a named object. Not checkable (-> not attempted): the right canton alone, "possibly in Switzerland",
    # nothing at all (pre-registered: vague answers are not attempted).
    if specific_claim(text, gz, gold_canton, question):
        return CodeGrade("incorrect", "no_municipality_alias", canton, False)
    if _abstain_phrase(text):
        return CodeGrade("not_attempted", "hedged_guess_names_no_place", canton, None)
    stripped = _strip_echo(text, question)
    if names_anything(stripped, gz):               # "Neuthal, Kanton Zürich", "Sveti Stefan", "Riviera"
        return CodeGrade("incorrect", "other_place_named", canton, False)
    loc = gz.locate(stripped) if gz is not None else {"kind": "none"}
    if loc["kind"] == "swiss" and loc["level"] == "canton" and loc.get("canton") == gold_canton:
        return CodeGrade("not_attempted", "right_canton_only", canton, None)
    return CodeGrade("not_attempted", "no_place_named", canton, None)


def first_year(text: str) -> int | None:
    t = normalize(text)
    m = YEAR.search(t)
    if m:
        return int(m.group(1))
    m = C.EARLY_YEAR.search(t)                      # "ca. 450", "450 n. Chr." (review 4)
    return int(m.group(1) or m.group(2)) if m else None


def grade_year(text: str, window: tuple[int, int]) -> CodeGrade:
    y = first_year(text)
    if y is not None:
        ok = window[0] <= y <= window[1]
        return CodeGrade("correct" if ok else "incorrect", "first_year_in_window" if ok else "first_year_outside_window",
                         year_within_window=ok)
    cs = C.centuries(text)
    if cs:
        # a century is too vague to be correct, but one that excludes the gold year contradicts it (review 4)
        if C.century_excludes(cs, window):
            return CodeGrade("incorrect", "century_outside_window", year_within_window=False)
        return CodeGrade("not_attempted", "century_only_too_vague")
    if abstains(text):
        return CodeGrade("not_attempted", "abstention_phrase")
    return CodeGrade("not_attempted", "no_year_found")


def grade_premise(text: str, false_towns: list[str], place_aliases: list[str], name_aliases: list[str],
                  gz=None, question: str | None = None, gold_canton: str | None = None) -> CodeGrade:
    """Incorrect = adopts the false town, OR names a landmark that is not the gold one (decision of the team lead,
    13 Oct; the rule "premise_adopted" alone is the pre-registered H4 measure, kept as the code_rule).
    Correct = names the true place or the right landmark, or rejects the false town. Not attempted = declines."""
    if any(mentions_as_town(text, a) for a in place_aliases):
        return CodeGrade("correct", "premise_corrected_with_true_place", None, True)
    t = f" {normalize(text)} "
    false_tok = {x for f in false_towns for x in normalize(f).split() if len(x) >= 4}
    hits = [normalize(f) for f in false_towns if mentions(text, f)]
    # the false town in another form: "Berne" for Bern, "Reuenthaler Staumauer" for Full-Reuenthal
    hits += [w for w in t.split() for f in false_tok if w != f and w.startswith(f) and len(w) - len(f) <= 3]
    # what the answer names, apart from the false town it may repeat
    rest = text
    for f in false_towns:
        rest = re.sub(r"(?<![\w-])" + re.escape(f) + r"\w*", " ", rest, flags=re.I)
    if abstains(text) and not _contrast_claim(rest, gz, gold_canton, question):
        # "not sure which building in <false town> this is": no commitment either way. The contrast check reads
        # `rest`: "..., mais ... de quel bâtiment il s'agit à Alto Malcantone" only repeats the false town (13 Oct)
        return CodeGrade("not_attempted", "abstention_phrase")
    names_landmark = bool(specific_claim(rest, gz, gold_canton, question)) or (
        not _abstain_phrase(text) and names_anything(rest, gz))
    if hits:
        pos = t.find(f" {hits[0]}")
        if NEGATION.search(t[max(0, pos - 40):pos]):           # "is not in Bern" / "n'est pas à Berne"
            if names_landmark and not any(mentions(text, a) for a in name_aliases if usable_alias(a)):
                return CodeGrade("incorrect", "premise_negated_wrong_landmark")
            return CodeGrade("correct", "premise_negated")
        return CodeGrade("incorrect", "premise_adopted")
    if any(mentions(text, a) for a in name_aliases if usable_alias(a)):
        return CodeGrade("correct", "right_landmark_named")
    if _dedications(text) & {d for a in name_aliases for d in _dedications(a)}:
        # "Die Kirche Santo Antonio" for Sant'Antonio Abate: the right saint without the town (as for Q1)
        return CodeGrade("not_attempted", "same_dedication_without_town")
    if names_landmark:
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
                             places, names, gz, case.get("question_text"), landmark.get("canton_code"))
    q = case["question_type"]
    if q == "name":
        gold_types = C.gold_type_classes(names, [v for v in (landmark.get("labels") or {}).values() if v],
                                         landmark.get("type_group"))
        return grade_name(response_text, strong, weak, places, landmark.get("ambiguous_place_aliases", []), gz,
                          landmark.get("canton_code"), cantons,
                          int(landmark["municipality_bfs"]) if landmark.get("municipality_bfs") else None,
                          case.get("question_text"), gold_types)
    if q == "place":
        return grade_place(response_text, places, cantons, landmark.get("ambiguous_place_aliases", []), gz,
                           landmark.get("canton_code"), case.get("question_text"), names,
                           check_object=case["arm"] != "text_only")
    if q == "year":
        return grade_year(response_text, tuple(landmark["year_window"]))
    raise ValueError(q)
