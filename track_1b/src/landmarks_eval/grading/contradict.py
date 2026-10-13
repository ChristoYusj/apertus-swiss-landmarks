"""Contradictions in otherwise vague answers (review 4, 14 Oct; post-hoc, see CHANGELOG).

SimpleQA's NOT_ATTEMPTED requires that the answer does not contradict the gold. An independent adjudication of
all 192 judge-vs-code disagreements (two reads) found that a vague answer is still an error when it states
something the gold excludes:
  * a building TYPE the landmark is not ("Chasa communala" = town hall for a church; a "mill" for a castle);
    a type that fits ("Chasa da baselgia" for a church) stays not attempted;
  * a denomination the landmark does not have ("reformed" for a Catholic church);
  * a CENTURY that excludes the gold year ("13th century" for 765); a century containing it stays vague;
  * a Swiss REGION that excludes the gold canton ("Zentralschweiz" for a landmark in Bern).
"""

from __future__ import annotations

import re

from .normalize import normalize

# coarse building classes; a word maps to one class (German compounds end in their type: "Rathausbrunnen")
_CLASS_WORDS = {
    "religious": "kirche kapelle chiesa cappella eglise chapelle baselgia baselgetta caplutta chaplutta church chapel "
                 "kloster abtei abbazia abbaye abbey convento couvent monastero monastere monastery claustrum clostra "
                 "kathedrale cattedrale cathedrale cathedral duomo dom munster basilica basilika basilique oratorio "
                 "oratorium oratory temple santuario sanctuaire collegiata collegiale stiftskirche pfarrkirche "
                 "klosterkirche baptisterium battistero baptistere preiera clutger campanile campanaria glockenturm "
                 "clocher kirchturm prieure priorat parrocchiale",
    "castle": "schloss burg burgruine castello castel chateau chaste casti castle festung fortezza forte fort bunker "
              "fortifications festungsanlagen befestigung",
    "tower": "turm torre tour tower tur uhrturm",
    "bridge": "brucke bruecke ponte pont punt bridge viadukt viadotto viaduc viaduct",
    "museum": "museum museo musee museu",
    "station": "bahnhof stazione gare station staziun funiculara",
    "townhall": "rathaus municipio communala comunale stadthaus gemeindehaus",
    "fountain": "brunnen fontana fontaine fountain funtauna",
    "theatre": "teatro theater theatre teatre teater",
    "statue": "statue statua menhir steinmenhir",
    "column": "colonna column saule",
    "house": "haus maison casa chalet villa patriziana herrenhaus",
    "post": "posta post",
    "mill": "mulino muhle moulin mill",
}
TYPE_CLASS = {w: c for c, ws in _CLASS_WORDS.items() for w in ws.split()}
_PHRASES = {"hotel de ville": "townhall", "chasa da la citad": "townhall", "town hall": "townhall",
            "palazzo civico": "townhall", "palazzo comunale": "townhall", "casa comunale": "townhall"}
# pairs that can describe the same object (a fountain with a statue, a castle used as a house or museum)
_COMPAT = {frozenset(p) for p in [("statue", "fountain"), ("house", "castle"), ("house", "museum"), ("house", "tower")]}
# the inventory's coarse type group, used where it is reliable; NOT "museum" (it also files heritage railways and
# collections there: "Dampfbahn Furka-Bergstrecke" is a railway whose photo shows a viaduct)
_GROUP_CLASS = {"church": "religious", "castle": "castle", "bridge": "bridge",
                "fountain": "fountain", "tower_gate": "tower", "monument": "statue"}
# "a church OR a historic building": a generic alternative commits to no type
_GENERIC_ALT = set("gebaude bauwerk bau anlage edificio edifici costruzione struttura batiment construction structure "
                   "building edifizi rudere ruine ruina rovine ruins ruin monument monumento denkmal monumentu".split())
_DISJ = {"o", "oder", "ou", "or", "u", "oppure", "ovvero", "resp"}


def type_classes(s: str, phrases: bool = True) -> set[str]:
    t = f" {normalize(s)} "
    out = {c for p, c in _PHRASES.items() if f" {p} " in t} if phrases else set()
    for tok in t.split():
        if tok in TYPE_CLASS:
            out.add(TYPE_CLASS[tok])
        else:
            for k in sorted(TYPE_CLASS, key=len, reverse=True):
                if len(k) >= 4 and tok.endswith(k) and len(tok) > len(k) + 2:
                    out.add(TYPE_CLASS[k])
                    break
    return out


def gold_type_classes(name_aliases: list[str], labels: list[str], type_group: str | None) -> set[str]:
    """Per name: the building words in it ("Town hall fountain" -> fountain); a phrase ("Hôtel de Ville") only
    when the name has no single building word, so a modifier is not read as the object's type."""
    g = set()
    for s in [*name_aliases, *labels]:
        if s:
            g |= type_classes(s, phrases=False) or type_classes(s)
    if _GROUP_CLASS.get(type_group or ""):
        g.add(_GROUP_CLASS[type_group])
    return g


def _generic_alternative(s: str) -> bool:
    toks = normalize(s).split()
    return any(t in _GENERIC_ALT and any(x in _DISJ for x in toks[max(0, i - 4):i + 5]) for i, t in enumerate(toks))


def type_conflict(text: str, gold: set[str]) -> bool:
    """The answer states building types, none of which fits the gold's."""
    if not gold or _generic_alternative(text):
        return False
    a = type_classes(text)
    return bool(a) and not any(x == y or frozenset((x, y)) in _COMPAT for x in a for y in gold)


_CONF = {"catholic": "katholisch katholische katholischen catholique cattolica cattolico catholic romisch romische",
         "reformed": "reformiert reformierte reformierten reformee riformata evangelica evangelisch evangelische "
                     "protestant protestante refurmada evangelic reformed anglican anglikanische",
         "orthodox": "orthodox orthodoxe ortodossa"}
_CONF_OF = {w: c for c, ws in _CONF.items() for w in ws.split()}


def confession_conflict(text: str, name_aliases: list[str]) -> bool:
    a = {_CONF_OF[t] for t in normalize(text).split() if t in _CONF_OF}
    g = {_CONF_OF[t] for al in name_aliases for t in normalize(al).split() if t in _CONF_OF}
    return bool(a and g and not (a & g))


# centuries: "13th century", "XIIIe siècle", Romansh "16avel tschientaner"
_CENT_AR = re.compile(r"\b(\d{1,2})\s*(?:[a-z]{1,5})?\s*(siecle|jahrhundert|century|secolo|tschientaner)\b")
_CENT_RO = re.compile(r"\b(x{0,2}(?:ix|iv|v?i{0,3}))(?:e|er|eme|ieme)?\s+(siecle|secolo|jahrhundert|century|tschientaner)\b")
_ROMAN = {"i": 1, "v": 5, "x": 10}


def _roman(s: str) -> int:
    tot = 0
    for a, b in zip(s, s[1:] + " "):
        v = _ROMAN[a]
        tot += -v if b != " " and _ROMAN.get(b, 0) > v else v
    return tot


def centuries(text: str) -> list[int]:
    t = normalize(text)
    out = [int(m.group(1)) for m in _CENT_AR.finditer(t)] + [_roman(m.group(1)) for m in _CENT_RO.finditer(t) if m.group(1)]
    return [c for c in out if 1 <= c <= 21]


def century_excludes(cs: list[int], window: tuple[int, int]) -> bool:
    """Every century named lies wholly outside the gold window (the 13th century = 1201-1300)."""
    return bool(cs) and all(100 * (c - 1) + 1 > window[1] or 100 * c < window[0] for c in cs)


# a 3-digit year below 500 only next to an "about" or era marker ("ca. 450", "450 n. Chr.")
EARLY_YEAR = re.compile(r"(?:\b(?:ca|circa|um|vers|verso|intorno al|anno|an|year|jahr|nel|en)\s+(\d{3})(?!\d))|"
                        r"(?:(?<!\d)(\d{3})\s+(?:n chr|nach christus|apr j c|ap j c|apres j c|d c|dc|dopo cristo|ad|s cr|p chr)\b)")

REGIONS = {"zentralschweiz": "LU UR SZ OW NW ZG", "innerschweiz": "LU UR SZ OW NW ZG",
           "vierwaldstattersee": "LU UR SZ OW NW", "ostschweiz": "SG TG AR AI GL SH GR",
           "westschweiz": "GE VD NE JU FR VS BE", "romandie": "GE VD NE JU FR VS BE", "suisse romande": "GE VD NE JU FR VS BE",
           "nordwestschweiz": "BS BL AG SO", "svizzera centrale": "LU UR SZ OW NW ZG", "suisse centrale": "LU UR SZ OW NW ZG",
           "svizzera orientale": "SG TG AR AI GL SH GR", "suisse orientale": "SG TG AR AI GL SH GR"}


def region_conflict(text: str, gold_canton: str | None) -> bool:
    t = f" {normalize(text)} "
    named = [set(c.split()) for r, c in REGIONS.items() if f" {r} " in t]
    return bool(named) and bool(gold_canton) and all(gold_canton not in s for s in named)
