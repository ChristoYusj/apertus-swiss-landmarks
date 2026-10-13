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
    "romisch", "romische", "roemisch", "roemische", "katholischen", "reformierten", "evangelisch", "evangelische",
    "evangelisch reformierte", "christkatholisch", "pfarrei", "kirchgemeinde", "ehemalige", "ehemaliges", "ehemaliger",
    "romaine", "romain", "protestante", "protestant", "paroissiale", "ancienne", "eglise", "cattolica", "cattolico",
    "romana", "romano", "evangelica", "riformata", "prepositurale", "collegiata", "parish", "roman", "former",
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
# Frozen copy used by the dataset BUILDER (step 1: which objects and aliases enter the dataset), exactly as it
# was when the 264 landmarks were drawn (seed 20261013). The audited, larger list below is used for grading and
# question validity only; changing the builder's vocabulary would change the sample on a rebuild.
_ADDED_IN_FIX_V2_V3 = {  # added to TYPE_WORDS after the run (CHANGELOG, fixes v2/v3); not part of step 1
    "cattolica", "cattolico", "christkatholisch", "collegiata", "ehemalige", "ehemaliger", "ehemaliges", "evangelica",
    "evangelisch", "evangelisch reformierte", "former", "katholischen", "kirchgemeinde", "parish", "paroissiale",
    "pfarrei", "prepositurale", "protestant", "protestante", "reformierten", "riformata", "roemisch", "roemische",
    "romain", "romaine", "roman", "romana", "romano", "romisch", "romische"}
TYPE_WORDS_V1 = frozenset(TYPE_WORDS - _ADDED_IN_FIX_V2_V3)  # = TYPE_WORDS at the pre-registration commit a73986e

# Audit 2026-10-13 (post-run, documented in CHANGELOG): every token that made a name alias or a shown label
# "specific" was listed (786 tokens) and each was classified by hand as a proper name or a generic word.
# Generic words found: building types, religious-order compounds, dedications shared by many churches,
# museum/railway/military vocabulary, function words. Kept as specific on purpose: national qualifiers
# (suisse, swiss, svizzero: "Musée suisse des douanes" is unique), figure names of fountains, every
# compound that contains a proper name (Grimmenturm, Hergiswaldbrücke, Pfyfferbrunnen), and words that are
# also place or family names in this dataset ("château de Villa" in Sierre, "Château Grenier" in Bex).
GENERIC_WORDS_AUDIT = {
    # function words and numbers
    "with", "mit", "avec", "con", "its", "son", "sein", "eines", "then", "puis", "dann", "spater", "soit", "als",
    "auf", "aus", "fur", "uber", "vom", "over", "sul", "alle", "delle", "dell", "two", "deux", "due", "zwei",
    "sept", "iii", "all", "tous", "known", "bekannt", "heisst", "part", "teil",
    # generic buildings and parts
    "building", "buildings", "batiment", "batiments", "gebaude", "nebengebaude", "nebengebauden", "nebenbauten",
    "nebenb", "museumsgebaude", "bahnhofsgebaude", "outbuilding", "outbuildings", "annexes", "dependance",
    "dependances", "communs", "house", "houses", "maison", "maisons", "casa", "case", "chasa", "palazzo",
    "palais", "palas", "residence", "residenz", "sitz", "landsitz", "manor", "herrenhausern", "maitre", "farmhouse",
    "bauernhaus", "paysanne", "barn", "grange", "granary", "speicher", "turmspeicher", "muhlespeicher",
    "zehntenspeicher", "kornhaus", "zeughaus", "kaufhaus", "stadthaus", "amthaus", "landhaus", "guterschuppen",
    "kuhlkeller", "cantine", "store", "department", "factory", "mill", "spinning", "cotton", "baumwollspinnerei",
    "fabrikantenvilla", "owner", "school", "boarding", "internat", "pensionnat", "novitiate", "noviziat",
    "infirmary", "infirmerie", "hospiz", "ospiz", "rectory", "parrochiale", "janitor", "portierhaus", "conciergerie",
    "office", "prefecture", "tribunal", "gerichts", "pretorio", "municipal", "municipale", "comunale", "comune",
    "comuni", "commune", "gemendeverwaltung", "kantonshauses", "standes", "state", "civico", "rathausplatz",
    "piazza", "place", "park", "parc", "gardens", "jardins", "gartenanlage", "gartenhaus", "grounds", "estate",
    "domaine", "site", "gelande", "siedlungen", "village", "dorf", "stadt", "city", "pond", "teich", "bassin",
    "river", "tomb", "grabmal", "funeral", "funeraire", "friedhof", "cimitero", "cimetry", "cemetery", "kreuzweg",
    "via", "crucis", "sale", "gemeinschaftsraumen", "bell", "clock", "horloge", "orologio", "uhrturm",
    "glockenturm", "clocher", "schlossturm", "gemeindeturm", "meierturm", "sendeturm", "communication",
    "rathausbrunnen", "springbrunnen", "dreitrog", "dreitrogbrunnen", "fountains", "fontaines", "romerbrucke",
    "vogteischloss", "viztumsschloss", "vogtei", "landvogts", "castel", "mur", "wall", "walls",
    # churches, monasteries, orders
    "abtei", "abbazia", "chloster", "chloschter", "clostra", "monastere", "monastero", "convent", "basilica",
    "basilika", "baptistere", "baptistery", "baptisterium", "battistero", "cathedral", "cattedrale", "duomo",
    "santuario", "sanctuaire", "oratory", "oratorium", "plebana", "plebian", "kollegiatkirche", "stiftskirche",
    "wehrkirche", "rundkirche", "martinskirche", "remigiuskirche", "dreifaltigkeitskirche", "michaeliskapelle",
    "grabkapelle", "kirchenburg", "wehrchille", "kapalle", "caplutta", "kirchenbezirk", "klosterkomplex",
    "augustinerkloster", "benediktinerabtei", "benediktinerkloster", "benediktinerklosters",
    "benediktinerinnenkloster", "dominikanerinnenkloster", "franziskanerkloster", "franziskanerkirche",
    "kapuzinerkloster", "trappistinnenkloster", "konventualenkloster", "johanniterkommende", "johanniterkomturei",
    "commandery", "benedictine", "benedictin", "benedictina", "benedettino", "franciscan", "franziskaner",
    "cordeliers", "agostiniane", "conventuali", "frati", "minori", "evangelical", "reforme", "refurmeda",
    "refurmada", "rifurmada", "catolica", "catolic", "protestantische", "complex", "complesso",
    # dedications shared by many churches (like saints' names)
    "maria", "marie", "mary", "notre", "dame", "madonna", "vergine", "vierge", "virgin", "beata", "jungfrau",
    "himmelfahrt", "assunta", "assunzione", "assomption", "assumption", "annunziata", "immaculee", "immacolata",
    "conception", "grazie", "pieta", "douleurs", "angeli", "angioli", "anges", "coeur", "herz", "jesu", "sacre",
    "sacred", "sacro", "heart", "holy", "heilig", "heilige", "heiligen", "croix", "kreuz", "cross", "trinity",
    "dreifaltigkeit", "auferstehung", "resurrection", "resurrezione", "salvator", "allerheiligen", "allerhailige",
    "saints", "santi", "monte",
    # museums and collections
    "musee", "museo", "kunstmuseum", "heimatmuseum", "klostermuseum", "stadtmuseum", "gemeindemuseum",
    "zollmuseum", "archaologiemuseum", "collezioni", "archiv", "archive", "kunsthaus", "kunsthuus", "art", "arts",
    "arte", "beaux", "kunst", "history", "histoire", "storia", "historical", "historisches", "natural",
    "naturelle", "naturale", "naturhistorisches", "archaeology", "archeologie", "archaologie", "archeologico",
    "archeologiche", "ethnography", "ethnographie", "ethnologie", "ethnographisches", "etnografico", "culture",
    "cultures", "kulturen", "customs", "douanes", "dogane", "doganale",
    # railways, bridges, fortifications
    "railway", "bahn", "dampfbahn", "bergstrecke", "train", "cogwheel", "steam", "line", "ligne", "staziun",
    "viaduct", "viaduc", "viadukt", "viadotto", "kehrviadukt", "kreisviadukt", "spiral", "helicoidal",
    "elicoidale", "cff", "sbb", "rhatischen", "arsenal", "fort", "forte", "forts", "fortini", "befestigungen",
    "befestigungsanlagen", "festungsanlagen", "fortifications", "fortificazioni", "fortified", "fortifie",
    "fortifiee", "fortificata", "defensive", "defensif", "enceinte", "enclosure", "ramparts", "remparts",
    "muraria", "murata", "cinta", "hunger", "hungerfestungen",
    # descriptors, languages, titles, inventory codes
    "ehemals", "altem", "antico", "nuovo", "neu", "grande", "petit", "piccolo", "inferiore", "bassa", "mezzo",
    "round", "ronde", "wooden", "country", "countryside", "campagna", "campagne", "rural", "landlich",
    "mittelalterliche", "prahistorische", "century", "jahrhundert", "nineteenth", "neunzehnten", "ottocentesche",
    "predecessor", "vorgangerbauten", "francais", "anglaise", "englische", "franzosische", "italian", "italiana",
    "captain", "hptm", "father", "pater", "pere", "switzerland", "bru", "vittime", "lavoro", "opfer",
    "ruina", "abbey", "eveche",
}
TYPE_WORDS |= GENERIC_WORDS_AUDIT

# Words that do not even say what KIND of object it is: an alias made only of these and function words
# ("bâtiment", "Building") is never used for grading, not even together with the town.
NON_NAMES = {"building", "buildings", "batiment", "batiments", "gebaude", "edifice", "bau", "bauwerk", "structure",
             "complex", "complesso", "site", "object", "objekt", "objet", "oggetto", "part", "teil"}


def usable_alias(alias: str) -> bool:
    """False for aliases like "bâtiment" that name no kind of object; True for "Rathausbrunnen", "Torre comunale"."""
    return any(len(t) >= 3 and not _has_digit(t) and t not in NON_NAMES and t not in _FUNCTION_WORDS
               for t in tokens(alias))


_FUNCTION_WORDS = {
    "the", "of", "and", "with", "its", "then", "two", "all", "over", "der", "die", "das", "des", "dem", "den", "und",
    "von", "zum", "zur", "mit", "sein", "eines", "dann", "als", "auf", "aus", "fur", "uber", "vom", "zwei", "les",
    "des", "aux", "sur", "avec", "son", "puis", "soit", "deux", "sept", "del", "della", "dei", "degli", "con", "due",
    "sul", "alle", "delle", "dell", "dal", "dalla", "former", "old", "ehemalige", "ehemaliges", "ehemaliger",
    "ancien", "ancienne", "antico", "alte", "alter", "altes", "neue", "neuer", "neu", "nuovo",
}


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
    return [t for t in tokens(label) if t not in TYPE_WORDS and len(t) >= 3 and not _has_digit(t)]


def _has_digit(t: str) -> bool:
    """Years and inventory codes ("1833", "009a") never name an object."""
    return any(ch.isdigit() for ch in t)


def is_generic(label: str | None) -> bool:
    return not label or not specific_tokens(label)


# ---- frozen step-1 (dataset builder) versions: TYPE_WORDS_V1 and the original digit rule -------------------
def specific_tokens_v1(label: str) -> list[str]:
    return [t for t in tokens(label) if t not in TYPE_WORDS_V1 and len(t) >= 3 and not t.isdigit()]


def is_generic_v1(label: str | None) -> bool:
    return not label or not specific_tokens_v1(label)


def distinctive_v1(alias: str, town_tokens: set[str]) -> bool:
    """distinctive() as at step 1 (only a single saint name after "st" was skipped)."""
    toks = tokens(alias)
    for i, t in enumerate(toks):
        if t in TYPE_WORDS_V1 or len(t) < 3 or t.isdigit() or t in town_tokens:
            continue
        if i > 0 and toks[i - 1] == "st":
            continue
        return True
    return False


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


def distinctive(alias: str, town_tokens: set[str], _words=None, _digit=None) -> bool:
    """True if the alias names THIS object: it has a specific word that is not a saint's name
    ("Kapelle St. Antonius" is not distinctive) and not a town name."""
    words = TYPE_WORDS if _words is None else _words
    has_digit = _has_digit if _digit is None else _digit
    toks = tokens(alias)
    saint = set()
    for i, t in enumerate(toks):  # "st peter und paul", "ss pietro e paolo", "st lorenzo ed agata"
        if t in ("st", "ss", "sts", "santi", "sainte", "saints"):
            j = i + 1
            while j < len(toks):
                saint.add(j)
                if j + 2 < len(toks) and toks[j + 1] in ("und", "et", "e", "ed", "and", "y"):
                    j += 2
                    continue
                break
    for i, t in enumerate(toks):
        if t in words or len(t) < 3 or has_digit(t) or t in town_tokens or i in saint:
            continue
        return True
    return False
