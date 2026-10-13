"""Grading edge cases (pre-registered rules). A failing case here = a wrong grade in the paper."""

import pytest

from landmarks_eval.analysis import Gazetteer
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
    # without the exonym the adoption itself is not detected, but since the lead's rule (13 Oct) naming a place or
    # landmark that is not the gold one is incorrect anyway
    assert grade_premise("Cette fontaine de Berne date de 1722.", ["Bern"], PLACES, NAMES).label == "incorrect"
    assert grade_premise("Cette fontaine de Berne date de 1722.", ["Bern", "Berne"], PLACES, NAMES).rule == "premise_adopted"


def test_lead_rules_13_oct():
    # premise: another landmark without the false town is wrong; the right landmark is correct; declining is NA
    assert grade_premise("Die Abtei Saint-Maurice", ["Bern"], ["Celerina"], ["San Gian (Celerina)"]).label == "incorrect"
    assert grade_premise("Es handelt sich um die Reuenthaler Staumauer.", ["Full-Reuenthal"], ["Airolo"],
                         ["Forte Airolo"]).label == "incorrect"
    assert grade_premise("C'est la Fontaine de la Justice.", ["Bern"], PLACES, NAMES).label == "correct"
    assert grade_premise("Fontaine", ["Bern"], PLACES, NAMES).label == "not_attempted"
    # place (photo): right town + another object is wrong; type word + town is not "another object"
    alias = ["San Vittore", "Saint Victor"]
    assert grade_place("Questa è la chiesa parrocchiale di San Martino a Poschiavo.", ["Poschiavo"], ["GR"],
                       name_aliases=alias, check_object=True).label == "incorrect"
    assert grade_place("Il monument è la Fortezza di Airolo, situata ad Airolo.", ["Airolo"], ["TI"],
                       name_aliases=["Forte Airolo"], check_object=True).label == "correct"
    assert grade_place("Das Gebäude befindet sich in Lugano, Kanton Tessin.", ["Lugano"], ["TI"],
                       name_aliases=["Palazzo Civico"], check_object=True).label == "correct"
    # "chantun Turitg" is the canton, not the town Zürich
    assert grade_place("Il tur appartegn a la vischnanca da Stein am Rhein ed il chantun è Turitg.", ["Zürich", "Turitg"],
                       ["Turitg"]).label == "incorrect"
    assert grade_place("Il tur è a Turitg, chantun Turitg.", ["Zürich", "Turitg"], ["Turitg"]).label == "correct"


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
    # changed in fix v4: 'kunsthaus' is generic (Kunsthaus Zug, Glarus, Aarau...); the alias still grades
    # correct because it contains the town (test_name_containing_the_town_carries_the_town)
    assert not distinctive("Kunsthaus Zürich", {"zurich"})
    assert distinctive("Zürcher Kunsthaus", {"zurich"})
    assert distinctive("Valère Castle", {"sion"})


def test_premise_abstention_repeating_the_town_is_not_adoption():
    t = "Je ne suis pas sûr. L'image montre une église, mais il est difficile de dire quel bâtiment de Centovalli c'est."
    # contains a guess marker? no ("mais il est difficile" is not a guess) -> abstention
    assert grade_premise(t, ["Centovalli"], ["Alto Malcantone"], ["San Michele"]).label == "not_attempted"
    assert grade_premise("L'église de Rothrist", ["Rothrist"], ["Holderbank"], ["Reformierte Kirche Holderbank"]).label == "incorrect"


def test_no_specific_name_abstention_de():
    assert abstains("Es gibt zahlreiche römisch-katholische Pfarrkirchen in der Schweiz. Ohne einen spezifischen Namen kann ich keine genaue Gemeinde nennen.")


# --- Fix v4 (13 Oct, post-run audit of every code-"correct" name grade and of all 786 name tokens) ---------
def _split(names, towns):
    from landmarks_eval.grading.normalize import distinctive, normalize
    tt = {t for p in towns for t in normalize(p).split()}
    return [n for n in names if distinctive(n, tt)], [n for n in names if not distinctive(n, tt)]


def test_meaningless_alias_cannot_turn_an_abstention_into_correct():
    # real answer from the official run; Wikidata lists "bâtiment" as an alias of the landmark
    strong, weak = _split(["bâtiment", "Building", "Grange-à-l'Évêque"], ["Sion"])
    text = "Je ne suis pas sûr du nom précis de ce bâtiment ou monument sans informations supplémentaires."
    assert grade_name(text, strong, weak, ["Sion"]).label == "not_attempted"


def test_generic_type_phrase_is_not_a_name():
    # real answer: "a public clock tower" for the Tour de l'Horloge in Vevey
    names = ["tour de l'Horloge", "Torre dell'orologio", "Uhrturm und Brunnen"]
    strong, weak = _split(names, ["Vevey"])
    assert strong == []
    text = "Non sono sicuro al 100% senza ulteriori informazioni, ma sembra essere una torre dell'orologio pubblica."
    assert grade_name(text, strong, weak, ["Vevey"]).label == "not_attempted"
    assert grade_name("È la torre dell'orologio di Vevey.", strong, weak, ["Vevey"]).label == "correct"


def test_generic_name_plus_town_is_correct_even_if_no_word_is_specific():
    strong, weak = _split(["Rathausbrunnen"], ["Lenzburg"])
    assert grade_name("Der Rathausbrunnen in Lenzburg.", strong, weak, ["Lenzburg"]).label == "correct"
    assert grade_name("Ein Rathausbrunnen.", strong, weak, ["Lenzburg"]).label == "not_attempted"


def test_name_containing_the_town_carries_the_town():
    # "Rapperswil" is a former municipality, only "Rapperswil-Jona" is a place alias
    strong, weak = _split(["Burg Rapperswil (Neu-Rapperswil)", "Schloss Rapperswil"], ["Rapperswil-Jona"])
    assert grade_name("Das ist Schloss Rapperswil.", strong, weak, ["Rapperswil-Jona"]).label == "correct"
    strong, weak = _split(["Kunsthaus Zürich", "Zürcher Kunsthaus"], ["Zürich", "Zurich"])
    assert grade_name("Kunsthaus Zürich", strong, weak, ["Zürich", "Zurich"]).label == "correct"
    assert grade_name("Das Kunsthaus.", strong, weak, ["Zürich"]).label == "incorrect"  # "Kunsthaus" alone is no alias


def test_ambiguous_town_inside_a_name_does_not_count():
    # corrected after the independent review: "Gossau" (ZH or SG) identifies the town only with the canton
    strong, weak = _split(["Kirche Gossau"], ["Gossau"])
    cantons = ["St. Gallen", "SG"]
    assert grade_name("Kirche Gossau", strong, weak, ["Gossau"], ["Gossau"], canton_aliases=cantons).label == "not_attempted"
    assert grade_name("Kirche Gossau im Kanton St. Gallen", strong, weak, ["Gossau"], ["Gossau"],
                      canton_aliases=cantons).label == "correct"
    assert grade_name("Kirche Gossau", strong, weak, [], ["Gossau"]).label == "not_attempted"
    # the canton-suffixed alias must not leak the ambiguous token ("Holderbank (AG)" -> "holderbank")
    strong, weak = _split(["Reformierte Kirche Holderbank"], ["Holderbank (AG)", "Holderbank"])
    assert grade_name("Die reformierte Kirche Holderbank im Kanton Solothurn", strong, weak, ["Holderbank (AG)", "Holderbank"],
                      ["Holderbank"], canton_aliases=["Aargau", "AG"]).label == "not_attempted"


def test_generic_name_with_the_wrong_town_is_incorrect():
    gz = Gazetteer({"cantons": {"AG": {"names": ["aargau"], "region": "DE"}},
                    "municipalities": [{"bfs": 4001, "names": ["aarau"], "canton": "AG", "region": "DE", "current": True},
                                       {"bfs": 261, "names": ["zurich"], "canton": "ZH", "region": "DE", "current": True},
                                       {"bfs": 3741, "names": ["ardez"], "canton": "GR", "region": "RM", "current": False,
                                        "successors": [3762]}],
                    "countries": {}})
    strong, weak = _split(["Kunsthaus Zürich", "Zürcher Kunsthaus"], ["Zürich"])
    assert grade_name("Das ist das Kunsthaus Aarau.", strong, weak, ["Zürich"], gz=gz, gold_bfs=261).label == "incorrect"
    strong, weak = _split(["Kapelle St. Antonius"], ["Zürich"])
    assert grade_name("Die Kapelle St. Antonius.", strong, weak, ["Zürich"], gz=gz, gold_bfs=261).label == "not_attempted"
    assert grade_name("Die Kapelle St. Antonius in Aarau.", strong, weak, ["Zürich"], gz=gz, gold_bfs=261).label == "incorrect"
    # a FORMER name of the right town is not "another town" (Ardez is now part of Scuol, 3762)
    strong, weak = _split(["Reformierte Kirche"], ["Scuol"])
    assert grade_name("Reformierte Kirche in Ardez", strong, weak, ["Scuol"], gz=gz, gold_bfs=3762).label == "not_attempted"
    assert grade_name("Reformierte Kirche in Aarau", strong, weak, ["Scuol"], gz=gz, gold_bfs=3762).label == "incorrect"


def test_proper_names_that_look_generic_stay_distinctive():
    from landmarks_eval.grading.normalize import distinctive
    assert distinctive("château de Villa", {"sierre"})        # Villa is a locality in Sierre
    assert distinctive("Château Grenier", {"bex"})            # family name
    assert distinctive("Musée suisse des douanes", {"lugano"})
    assert not distinctive("Bahnhof SBB", {"renens"})
    assert not distinctive("Rundkirche Mariä Himmelfahrt", {"saas", "balen"})
    assert not distinctive("Torre comunale 009a", {"locarno"})  # inventory codes are not names


# --- Fix v5 (13 Oct): pre-registered "vague answers = not attempted", applied to hedged guesses ----------------
# Every text below is a real answer from the official run (the 145 changed labels were all read by hand).
from landmarks_eval.analysis import Gazetteer as _Gz

_GZ = _Gz({"cantons": {"TG": {"names": ["thurgau"], "region": "DE"}, "GR": {"names": ["graubunden", "grischun"], "region": None},
                       "VS": {"names": ["wallis"], "region": None}},
           "municipalities": [{"bfs": 3901, "names": ["chur"], "canton": "GR", "region": "DE", "current": True}],
           "countries": {"LI": ["liechtenstein", "vaduz"]}})


@pytest.mark.parametrize("text,label", [
    ("Unsicher. Es könnte eine Kirche sein, aber der genaue Name ist nicht erkennbar.", "not_attempted"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere una chiesa o un edificio "
     "religioso storico, probabilmente situato in Europa.", "not_attempted"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma questo edificio sembra essere il Castello di Vaduz, "
     "situato a Vaduz, Liechtenstein.", "incorrect"),
    ("Non sono sicuro al 100%, ma sembra essere la Chiesa di San Martino a Malles Venosta, in Alto Adige, Italia.", "incorrect"),
    ("Unsicher, vermutlich ist es das Schloss Thun.", "incorrect"),
    ("Die Kirche heißt St. Martin.", "incorrect"),                     # unhedged: unchanged by v5
])
def test_v5_hedged_name_guesses(text, label):
    assert grade_name(text, NAMES, gz=_GZ, gold_canton="VD").label == label


@pytest.mark.parametrize("text,gold,label", [
    ("Je ne peux pas identifier avec certitude le bâtiment ou le monument sur cette image sans plus d'informations. "
     "Si vous avez des détails supplémentaires, je pourrai peut-être vous aider.", "VD", "not_attempted"),
    ("Unsicher über genaue Lage; Bild zeigt eine kleine Kapelle, wahrscheinlich in der Schweiz (typische Architektur), "
     "aber ohne weitere Hinweise kann Gemeinde und Kanton nicht bestimmt werden.", "VD", "not_attempted"),
    ("Die genaue Gemeinde ist unklar, es ist aber wahrscheinlich im Kanton Graubünden.", "GR", "not_attempted"),  # right canton only
    ("Die genaue Gemeinde ist unklar, es ist aber wahrscheinlich im Kanton Thurgau.", "GR", "incorrect"),        # wrong canton
    ("Die Burg Schiedberg befindet sich in der Gemeinde Schiedhalden im Kanton Thurgau.", "TG", "incorrect"),   # unknown town
    ("Sveti Stefan", "GR", "incorrect"),            # a bare place name the gazetteer does not know stays an attempt
    ("Riviera", "TI", "incorrect"),
    ("Vischnanca: Cuera   Chantun:Surselva", "GR", "incorrect"),
])
def test_v5_place(text, gold, label):
    assert grade_place(text, PLACES, CANTONS, gz=_GZ, gold_canton=gold).label == label


# --- Fix v5b (13 Oct, second audit of every hedged answer; all real answers from the run) -----------------
@pytest.mark.parametrize("text,question,label", [
    # vague hedges that the first detector mistook for names
    ("Unsicher. Das Bild zeigt eine Ruine, die typisch für mittelalterliche Burgen in der Schweiz sein könnte, "
     "aber ohne spezifische Kennzeichen lässt sich die Gemeinde nicht bestimmen.", None, "not_attempted"),
    ("Unsicher. Das Bild zeigt einen auffälligen Sendeturm auf einem Hügel, der typisch für viele Regionen in der "
     "Schweiz sein könnte.", None, "not_attempted"),
    # the name repeated from the question is an echo, not a claim
    ("Ich bin unsicher, da es keinen bekannten Ort namens «Grimmenturm» in der Schweiz gibt. Es könnte sich um "
     "einen sehr kleinen Weiler handeln.", "Wo in der Schweiz befindet sich «Grimmenturm»?", "not_attempted"),
    # real claims stay incorrect
    ("Le palais Castelmur se trouve à Sent, dans le canton des Grisons, en Suisse.",
     "Où se trouve « Palais Castelmur » en Suisse ?", "incorrect"),
    ("Il monument è situà a Cuera, in vischnanca dal chantun Grischun en Svizra.", None, "incorrect"),
])
def test_v5b_place(text, question, label):
    gz = Gazetteer({"cantons": {"GR": {"names": ["graubunden", "grischun", "grisons"], "region": None}},
                    "municipalities": [{"bfs": 3742, "names": ["sent"], "canton": "GR", "region": "RM", "current": False,
                                        "successors": [3762]}],
                    "countries": {}})
    assert grade_place(text, ["Bregaglia"], ["Grisons"], gz=gz, gold_canton="GR", question=question).label == label


@pytest.mark.parametrize("text,label", [
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere il Teatro alla Scala di Milano.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio principale è probabilmente l'Abbazia di Ettal.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere il **Biblioteca Centrale di "
     "Birmingham**.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere un cortile di un monastero, "
     "forse in Sud America.", "incorrect"),
    ("Unsicher. Es könnte ein Kloster oder eine historische Anlage sein, aber ohne weitere Informationen kann ich den "
     "genauen Namen nicht nennen.", "not_attempted"),
    ("Ich bin unsicher. Es könnte eine alte Steinbrücke oder ein Aquädukt sein, aber ohne weitere Informationen kann "
     "ich den genauen Namen nicht nennen.", "not_attempted"),
])
def test_v5b_name(text, label):
    assert grade_name(text, NAMES, gz=None, gold_canton="VD").label == label


def test_sent_is_a_town_only_outside_dedications():
    gz = Gazetteer({"cantons": {}, "municipalities": [{"bfs": 3742, "names": ["sent"], "canton": "GR", "region": "RM",
                                                         "current": False, "successors": [3762]}], "countries": {}})
    assert gz.locate("Le palais se trouve à Sent.")["kind"] == "swiss"
    assert gz.locate("La baselgia da Sent Martin.")["kind"] == "none"
