"""Grading edge cases (pre-registered rules). A failing case here = a wrong grade in the paper."""

import pytest

from landmarks_eval.grading.rules import abstains, first_year, grade_name, grade_place, grade_premise, grade_year

NAMES = ["Fontaine de la Justice", "Gerechtigkeitsbrunnen (Lausanne)", "Justice Fountain"]
PLACES = ["Lausanne", "Losanna"]
CANTONS = ["Vaud", "Waadt", "VD", "canton de Vaud"]


@pytest.mark.parametrize("text,label", [
    ("C'est la Fontaine de la Justice, sur la place de la Palud.", "correct"),
    ("Das ist der Gerechtigkeitsbrunnen (Lausanne).", "correct"),
    ("This is the justice fountain in Lausanne.", "correct"),          # case-insensitive
    ("C’est la fontaine de la justice", "correct"),                    # typographic apostrophe
    ("Il s'agit de la Fontaine des Trois Grâces à Berne.", "incorrect"),
    ("Je ne peux pas identifier ce monument avec certitude.", "not_attempted"),
    ("Ich kann das Denkmal nicht eindeutig bestimmen.", "not_attempted"),
    ("Non sono in grado di identificare il monumento.", "not_attempted"),
    ("Jau na sai betg tge monument quai è.", "not_attempted"),
    ("I don't know which fountain this is.", "not_attempted"),
])
def test_name(text, label):
    assert grade_name(text, NAMES).label == label


def test_generic_alias_never_matches():
    # an alias made only of type words must not turn "a fountain" into a correct answer
    assert grade_name("C'est une fontaine.", ["Fontaine"]).label == "incorrect"


@pytest.mark.parametrize("text,label,canton", [
    ("Lausanne, canton de Vaud", "correct", True),
    ("Il se trouve à Losanna (Vaud).", "correct", True),
    ("In Bern, Kanton Bern.", "incorrect", False),
    ("Dans le canton de Vaud, mais je ne sais pas quelle commune.", "not_attempted", True),
    ("Lausanne-Ouchy? No: it is in Lausanne.", "correct", None),
])
def test_place(text, label, canton):
    g = grade_place(text, PLACES, CANTONS)
    assert g.label == label
    if canton is not None:
        assert g.canton_correct is canton


def test_bilingual_town_names():
    places = ["Biel/Bienne", "Biel", "Bienne"]
    assert grade_place("Es steht in Biel.", places, ["Bern"]).label == "correct"
    assert grade_place("Situé à Bienne.", places, ["Berne"]).label == "correct"
    assert grade_place("In Bielersee region", places, ["Bern"]).label == "incorrect"


@pytest.mark.parametrize("text,label", [
    ("Elle a été construite en 1585.", "correct"),
    ("Erbaut 1582, renoviert 1890.", "correct"),        # first year is the answer
    ("Construite en 1722.", "incorrect"),
    ("Erbaut im 16. Jahrhundert.", "not_attempted"),     # century only: too vague
    ("Construite au XVIe siècle", "not_attempted"),      # roman numerals: no year found
    ("Je ne sais pas.", "not_attempted"),
])
def test_year(text, label):
    assert grade_year(text, (1580, 1590)).label == label


def test_first_year_ignores_long_numbers():
    assert first_year("Tel. 0213151515, construit en 1600") == 1600
    assert first_year("about 12000 visitors") is None


@pytest.mark.parametrize("text,label", [
    ("Ce n'est pas à Berne : il s'agit de la Fontaine de la Justice à Lausanne.", "correct"),
    ("Dieser Brunnen steht nicht in Bern.", "correct"),
    ("Cette fontaine de Berne date de 1722.", "incorrect"),
    ("Je ne sais pas.", "not_attempted"),
])
def test_premise(text, label):
    assert grade_premise(text, ["Bern", "Berne", "Berna"], PLACES, NAMES).label == label


def test_premise_exonym_is_still_detected():
    # question said "Bern", answer says "Berne": still adopting the false premise
    assert grade_premise("Cette fontaine de Berne date de 1722.", ["Bern"], PLACES, NAMES).label == "not_attempted"
    assert grade_premise("Cette fontaine de Berne date de 1722.", ["Bern", "Berne"], PLACES, NAMES).label == "incorrect"


def test_abstain_does_not_fire_on_answers():
    assert not abstains("La Fontaine de la Justice, construite en 1585, se trouve à Lausanne.")


def test_nondistinctive_name_needs_the_town():
    weak, places = ["Kapelle St. Antonius"], ["Zernez"]
    assert grade_name("Das ist die Kapelle St. Antonius.", [], weak, places).label == "not_attempted"
    assert grade_name("Die Kapelle St. Antonius in Zernez.", [], weak, places).label == "correct"
    assert grade_name("Die Kapelle St. Antonius.", weak).label == "correct"  # if listed as strong


def test_mixed_strong_and_weak_names():
    strong, weak, places = ["Stiftskirche Beromünster"], ["St. Michael"], ["Beromünster"]
    assert grade_name("Das ist St. Michael.", strong, weak, places).label == "not_attempted"
    assert grade_name("Die Stiftskirche Beromünster.", strong, weak, places).label == "correct"
    assert grade_name("St. Michael in Beromünster.", strong, weak, places).label == "correct"


def test_ambiguous_town_needs_the_canton():
    places, cantons = ["Gossau (SG)", "Gossau"], ["St. Gallen", "SG", "Kanton St. Gallen"]
    amb = ["Gossau"]
    assert grade_place("In Gossau.", places, cantons, amb).label == "not_attempted"
    assert grade_place("In Gossau, Kanton St. Gallen.", places, cantons, amb).label == "correct"
    assert grade_place("In Gossau (SG).", places, cantons, amb).label == "correct"
    assert grade_place("In Gossau, Kanton Zürich.", places, cantons, amb).label == "not_attempted"


def test_split_names_with_canton_suffix():
    from landmarks_eval.grading.normalize import distinctive, split_bilingual
    assert split_bilingual("Carouge (GE)") == ["Carouge (GE)", "Carouge"]
    assert split_bilingual("Biel/Bienne") == ["Biel/Bienne", "Biel", "Bienne"]
    assert not distinctive("Kapelle St. Antonius", {"zernez"})
    assert not distinctive("Reformierte Kirche Zernez", {"zernez"})
    assert distinctive("Gerechtigkeitsbrunnen", {"bern"})
    assert distinctive("Schloss Chillon", {"veytaux"})


@pytest.mark.parametrize("text", [
    "Unsicher.", "Unsicher, da keine spezifischen geografischen Hinweise im Bild vorhanden sind.", "Betg segir",
    "N/A", "Nun enconuschent", "Incertain", "Je ne suis pas sûr.", "Non sono sicuro.",
    "Das genaue Gebäude oder Denkmal ist nicht eindeutig identifizierbar. Unsicher.",
    "Nun en segir davart l'onn da construcziun.",
])
def test_short_abstentions_observed_in_the_official_run(text):
    # real answers of Apertus 1.5 70B (official run, 13 Oct 2026) that v1 of the grader missed
    assert abstains(text)
    assert grade_name(text, NAMES).label == "not_attempted"


@pytest.mark.parametrize("text", [
    "Non sono sicuro al 100% senza ulteriori informazioni, ma sembra essere la Chiesa di San Giacomo Maggiore a Pontebba.",
    "Non sono sicuro al 100%, ma sembra essere il Viadotto di Landwasser, in Svizzera.",
    "Je ne suis pas sûr, mais il semble que ce soit la cathédrale de Lausanne.",
    "Unsicher, vermutlich ist es das Schloss Thun.",
])
def test_hedged_guess_is_an_attempt(text):
    assert not abstains(text)
    assert grade_name(text, NAMES).label == "incorrect"


def test_saint_pairs_and_confession_words_are_not_distinctive():
    from landmarks_eval.grading.normalize import distinctive
    assert not distinctive("Pfarrkirche St. Peter und Paul", {"flumenthal"})
    assert not distinctive("Chiesa parrocchiale dei SS. Pietro e Paolo", set())
    assert not distinctive("Römisch-katholische Pfarrkirche", {"beinwil", "am", "see"})
    assert not distinctive("Église catholique romaine", set())
    assert distinctive("Kunsthaus Zürich", {"zurich"})  # 'kunsthaus' is specific
    assert distinctive("Valère Castle", {"sion"})


def test_premise_abstention_repeating_the_town_is_not_adoption():
    t = "Je ne suis pas sûr. L'image montre une église, mais il est difficile de dire quel bâtiment de Centovalli c'est."
    # contains a guess marker? no ("mais il est difficile" is not a guess) -> abstention
    assert grade_premise(t, ["Centovalli"], ["Alto Malcantone"], ["San Michele"]).label == "not_attempted"
    assert grade_premise("L'église de Rothrist", ["Rothrist"], ["Holderbank"], ["Reformierte Kirche Holderbank"]).label == "incorrect"


def test_no_specific_name_abstention_de():
    assert abstains("Es gibt zahlreiche römisch-katholische Pfarrkirchen in der Schweiz. Ohne einen spezifischen Namen kann ich keine genaue Gemeinde nennen.")
