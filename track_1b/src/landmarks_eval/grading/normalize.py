"""Text normalisation shared by the dataset builder and the graders."""

from __future__ import annotations

import re
import unicodedata

_SAINT = {"st", "ste", "sankt", "saint", "sainte", "san", "santa", "santo", "sant", "sogn", "sontga"}

# Words that describe the TYPE of object or are function words; a label made only of
# these (e.g. "Reformierte Kirche") does not name a specific landmark.
TYPE_WORDS = {
    # de
    "kirche", "reformierte", "reformiert", "katholische", "katholisch", "christkatholische", "evangelische",
    "pfarrkirche", "kapelle", "wallfahrtskirche", "klosterkirche", "kloster", "stift", "dom", "munster", "muenster",
    "brunnen", "schloss", "burg", "burgruine", "ruine", "brucke", "bruecke", "holzbrucke", "turm", "tor", "stadttor",
    "rathaus", "gemeindehaus", "bahnhof", "museum", "denkmal", "statue", "festung", "befestigung", "kathedrale",
    "pfarrhaus", "haus", "der", "die", "das", "des", "dem", "den", "und", "von", "zum", "zur", "am", "im", "in", "bei", "alte", "alter", "altes", "neue", "neuer", "obere", "untere",
    # fr
    "eglise", "reformee", "catholique", "temple", "chapelle", "abbaye", "couvent", "cathedrale", "basilique", "collegiale",
    "fontaine", "chateau", "pont", "tour", "porte", "hotel", "ville", "gare", "musee", "monument", "ruines", "ruine",
    "de", "du", "des", "la", "le", "les", "l", "d", "et", "a", "au", "aux", "en", "sur", "vieux", "vieille", "ancien", "ancienne",
    # it
    "chiesa", "parrocchiale", "oratorio", "cappella", "convento", "fontana", "castello", "ponte", "torre", "municipio",
    "stazione", "museo", "monumento", "di", "del", "della", "dei", "degli", "e", "il", "lo", "i", "gli",
    # rm
    "baselgia", "baselgetta", "chaplutta", "claustra", "fontauna", "chaste", "punt", "tur", "dalla", "dal", "da",
    # en
    "church", "reformed", "catholic", "chapel", "monastery", "abbey", "fountain", "castle", "bridge", "tower", "gate",
    "town", "hall", "station", "museum", "monument", "ruins", "the", "of", "and", "old",
} | _SAINT


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize(s: str) -> str:
    """Lowercase, drop accents, ß→ss, punctuation→space, unify 'saint' forms, collapse spaces."""
    s = s.replace("ß", "ss").replace("’", "'")
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = ["st" if t in _SAINT else t for t in s.split()]
    return " ".join(toks)


def tokens(s: str) -> list[str]:
    return normalize(s).split()


def specific_tokens(label: str) -> list[str]:
    """Tokens of a label that are not type/function words (length >= 3)."""
    return [t for t in tokens(label) if t not in TYPE_WORDS and len(t) >= 3 and not t.isdigit()]


def is_generic(label: str | None) -> bool:
    return not label or not specific_tokens(label)


def contains_phrase(haystack: str, needle: str) -> bool:
    """True if the normalised needle occurs as whole words inside the normalised haystack."""
    h, n = f" {normalize(haystack)} ", normalize(needle)
    return bool(n) and f" {n} " in h


def split_bilingual(name: str) -> list[str]:
    """'Biel/Bienne' -> ['Biel/Bienne', 'Biel', 'Bienne']; 'Carouge (GE)' -> ['Carouge (GE)', 'Carouge']."""
    out = [name]
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if base and base != name:
        out.append(base)
    for n in list(out):
        parts = [p.strip() for p in re.split(r"\s*/\s*", n) if p.strip()]
        if len(parts) > 1:
            out += [p for p in parts if p not in out]
    return out


def distinctive(alias: str, town_tokens: set[str]) -> bool:
    """True if the alias names THIS object: it has a specific word that is not a saint's name
    ("Kapelle St. Antonius" is not distinctive) and not a town name."""
    toks = tokens(alias)
    for i, t in enumerate(toks):
        if t in TYPE_WORDS or len(t) < 3 or t.isdigit() or t in town_tokens:
            continue
        if i > 0 and toks[i - 1] == "st":
            continue
        return True
    return False
