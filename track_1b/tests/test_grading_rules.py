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
    # an alias made only of type words must not turn "a fountain" into a correct answer. Since review 2 (13 Oct)
    # a bare type answer is not attempted (pre-registered "vague = not attempted"); before, the token "C'est" was
    # wrongly read as a name and made it incorrect.
    assert grade_name("C'est une fontaine.", ["Fontaine"]).label == "not_attempted"


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
    # "Kunsthaus" alone is no alias; since the second review a bare type word is vague (pre-registered: not attempted)
    assert grade_name("Das Kunsthaus.", strong, weak, ["Zürich"]).label == "not_attempted"


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


# --- Review 2 (13 Oct): a second independent reviewer read every answer graded incorrect --------------------
# Each case is a real answer from the official run (70B or 8B); comments name the reviewer's finding.
_GZ2 = Gazetteer({
    "cantons": {"GR": {"names": ["graubunden", "grischun", "grisons", "grigioni"], "region": None},
                "VS": {"names": ["wallis", "valais"], "region": None}, "ZH": {"names": ["zurich"], "region": "DE"},
                "GE": {"names": ["genf", "geneve"], "region": "FR"}, "AG": {"names": ["aargau"], "region": "DE"},
                "OW": {"names": ["obwalden"], "region": "DE"}, "TI": {"names": ["tessin", "ticino"], "region": "IT"},
                "FR": {"names": ["freiburg", "fribourg"], "region": None}, "VD": {"names": ["waadt", "vaud"], "region": "FR"}},
    "municipalities": [
        {"bfs": 3762, "names": ["scuol"], "canton": "GR", "region": "RM", "current": True},
        {"bfs": 3763, "names": ["sent"], "canton": "GR", "region": "RM", "current": False, "successors": [3762]},
        {"bfs": 3764, "names": ["tarasp"], "canton": "GR", "region": "RM", "current": False, "successors": [3762]},
        {"bfs": 3901, "names": ["chur", "cuera"], "canton": "GR", "region": "DE", "current": True},
        {"bfs": 2196, "names": ["fribourg", "freiburg"], "canton": "FR", "region": "FR", "current": True},
        {"bfs": 2097, "names": ["romont fr", "romont"], "canton": "FR", "region": "FR", "current": True},
        {"bfs": 5192, "names": ["lugano"], "canton": "TI", "region": "IT", "current": True}],
    "countries": {"IT": ["italia", "italien", "italie"], "FR": ["france", "francia"], "SI": ["slovenia"], "EE": ["estonia"],
                  "DK": ["danimarca"]}})


@pytest.mark.parametrize("text", [
    # must-fix 1: refusals the patterns did not know (242 had been graded incorrect)
    "Non è sicuro identificare con precisione l'edificio o monumento basandosi solo sull'immagine fornita.",
    "Die genaue Bezeichnung des Gebäudes ist nicht eindeutig aus dem Bild ableitbar. Es handelt sich um eine Kirche "
    "mit Turm und Uhr, aber ohne weitere Informationen oder sichtbare Beschriftungen kann der exakte Name nicht bestimmt werden.",
    "Die genaue Bezeichnung des Gebäudes ist mir nicht bekannt.",
    "Betga segir", "Nessuna informaziun disponibla", "Il num exact n'è betg visibel en l'immagine.", "Non identifitgabel",
    "Nesgir",
    "Sans plus de contexte ou d'informations spécifiques sur l'emplacement ou les caractéristiques uniques du bâtiment, "
    "il est impossible de donner un nom précis. Cependant, il s'agit d'une petite maison ou d'un bâtiment résidentiel "
    "situé dans un paysage naturel avec une cascade en arrière-plan.",
])
def test_review2_name_refusals(text):
    assert grade_name(text, NAMES, gz=_GZ2, gold_canton="VD").label == "not_attempted"


@pytest.mark.parametrize("text,question", [
    ("Ich bin mir nicht sicher, wo sich «Haus Jaura» befindet.", "Wo in der Schweiz befindet sich «Haus Jaura»?"),
    ("Je ne dispose pas d'informations fiables sur une « Cantoni House » en Suisse. Sans plus de contexte, je ne peux "
     "pas indiquer la commune et le canton avec certitude.", "Où se trouve « Haus Cantoni » en Suisse ?"),
    ("Vischnanca: Non indicheda; Chantun: Non indicheda", None),
    ("Das Bild zeigt eine kleine Kapelle in einer alpinen Umgebung, wahrscheinlich in der Schweiz. Ohne spezifische "
     "Kennzeichnungen oder zusätzliche Informationen ist eine genaue Bestimmung der Gemeinde und des Kantons nicht möglich.", None),
    ("Je ne trouve pas d'information fiable sur un lieu nommé « pont des Sauts » en Suisse.", None),
    # a fragment of the shown name quoted on its own is an echo
    ("Ich bin unsicher bezüglich der genauen Lage dieses spezifischen Landsitzes «Champ-Pittet» mit den genannten "
     "Merkmalen (Schloss, Springbrunnen, zwei Scheiterhaufen) in der Schweiz. Eine kurze Recherche konnte keine "
     "eindeutige Zuordnung zu einer Gemeinde und einem Kanton liefern.",
     "Wo in der Schweiz befindet sich «Landsitz Champ-Pittet, Schloss von Champ-Pittet mit Springbrunnen»?"),
    # "dédiée à Cosmas": the preposition introduces the saint, not a place
    ("Je ne dispose pas d'informations fiables sur une église catholique dédiée à Cosmas et Damien située en Suisse. "
     "Si une telle église existe, elle est probablement très petite ou locale, et je ne peux pas en confirmer "
     "l'emplacement avec certitude.", "Où se trouve « catholic church Cosmas and Damian » en Suisse ?"),
])
def test_review2_place_refusals(text, question):
    assert grade_place(text, ["Bregaglia"], ["Grisons"], gz=_GZ2, gold_canton="GR", question=question).label == "not_attempted"


def test_review2_similar_name_is_wrong():
    # must-fix 2 / team-lead rule: a longer, different name that starts with the gold alias is wrong
    strong = ["Museo Cantonale d'Arte", "Kantonales Kunstmuseum Lugano"]
    g = grade_name("Museo cantonale d'arte e di storia", strong, place_aliases=["Lugano"], gz=_GZ2, gold_canton="TI")
    assert (g.label, g.rule) == ("incorrect", "similar_but_different_name")
    assert grade_name("Museo Cantonale d'Arte", strong).label == "correct"
    assert grade_name("Il Museo Cantonale d'Arte e la piazza", strong).label == "correct"   # "e la": a new phrase


@pytest.mark.parametrize("text,gold,label", [
    # must-fix 4: villages, unknown wrong towns and countries are attempts (team-lead village rule)
    ("Neuthal, Kanton Zürich.", "ZH", "incorrect"),
    ("Vésenaz, Kanton Genf", "GE", "incorrect"),
    ("Setteln, Kanton Obwalden", "OW", "incorrect"),
    ("Baden, Kanton Aargau", "AG", "incorrect"),
    ("Italien, Tessin", "TI", "incorrect"),
    ("Sontga Maria", "TI", "incorrect"),
    # two cantons are competing candidates, whichever is the gold (was graded by order)
    ("Die genaue Gemeinde und der Kanton sind aus dem Bild nicht eindeutig zu bestimmen. Es handelt sich um ein "
     "typisches Dorf in den Schweizer Alpen, möglicherweise im Kanton Graubünden oder Wallis. Unsicher.", "GR", "incorrect"),
    ("Die genaue Gemeinde und der Kanton sind aus dem Bild nicht eindeutig zu bestimmen. Es handelt sich um ein "
     "typisches Dorf in den Schweizer Alpen, möglicherweise im Kanton Graubünden oder Wallis. Unsicher.", "VS", "incorrect"),
    # the right canton alone is still not attempted
    ("Die genaue Gemeinde ist unklar, es ist aber wahrscheinlich im Kanton Graubünden.", "GR", "not_attempted"),
    ("Quai è ina fontana cun ina statua en il center d'in quader urban, probabel en ina vischnanca da la Svizra. "
     "Il chantun n'è betg clar da la fotografia.", "GR", "not_attempted"),
    ("Quests edifizis appartegnan a vischnancas dil chantunSurselva.", "TG", "incorrect"),   # a missing space
    ("MInF5", "NE", "not_attempted"),
])
def test_review2_place_tail(text, gold, label):
    assert grade_place(text, ["Bäretswil"], ["Zürich"], gz=_GZ2, gold_canton=gold).label == label


@pytest.mark.parametrize("text,question,label", [
    # the shown name's town stated as the place is a claim (it is no longer the municipality: village rule)
    ("Schloss Tarasp befindet sich in der Gemeinde Tarasp im Kanton Graubünden.", "Wo befindet sich «Schloss Tarasp»?", "incorrect"),
    ("Tarasp, Graubünden", "Wo befindet sich «Schloss Tarasp»?", "incorrect"),
    ("Le Château de Tarasp se trouve dans la commune de Tarasp, dans le canton des Grisons, en Suisse.",
     "Où se trouve « Château de Tarasp » ?", "incorrect"),
    ("In der Gemeinde Sent, Kanton Graubünden.", None, "incorrect"),
    ("Schloss Tarasp liegt in Scuol, Kanton Graubünden.", "Wo befindet sich «Schloss Tarasp»?", "correct"),
])
def test_review2_shown_name_town_is_a_claim(text, question, label):
    assert grade_place(text, ["Scuol"], ["Graubünden"], gz=_GZ2, gold_canton="GR", question=question).label == label


def test_review2_shown_name_word_hid_a_wrong_town():
    q = "Où se trouve « Festungsanlagen (Enceinte, Tour à Boyer, Tour de Billens, Tour de Fribourg) » en Suisse ?"
    for t in ("Fribourg, canton de Fribourg", "Ces fortifications se trouvent à Fribourg, dans le canton de Fribourg, en Suisse."):
        assert grade_place(t, ["Romont"], ["Fribourg"], gz=_GZ2, gold_canton="FR", question=q).label == "incorrect"


@pytest.mark.parametrize("text,label", [
    # must-fix 5: bare type words are vague (pre-registered: not attempted)
    ("Kapelle", "not_attempted"), ("Bahnhof", "not_attempted"), ("Chasa da baselgia", "not_attempted"),
    ("Covered Bridge", "not_attempted"), ("Tgesa d'uras da la citad", "not_attempted"),
    ("Clutger da la baselgia", "not_attempted"), ("Fountain in the town square", "not_attempted"),
    ("Tour de l'Horloge (Horloge Tower)", "not_attempted"),
    # a name after an elided article is still a name
    ("Tour de la Porte d'Enfer", "incorrect"),
    # "not sure, BUT it is X": graded on X (contrast claims; country claims count like "Italia")
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio in questione è il **Castello di Predjama**, "
     "situato in Slovenia.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'immagine mostra le torri della Città Vecchia di "
     "Tallinn, in Estonia, parte delle mura medievali della città.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere un castello storico, "
     "probabilmente situato in Europa, data la presenza della bandiera che potrebbe essere quella della Danimarca.", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere un castello o una residenza "
     "storica europea, forse in Francia o Svizzera.", "not_attempted"),          # offers Switzerland too
])
def test_review2_name_tail(text, label):
    assert grade_name(text, NAMES, gz=_GZ2, gold_canton="VD").label == label


def test_review2_weak_name_with_a_town_the_gazetteer_lacks():
    g = grade_name("Kirche St. Peter in Oberndorf", [], ["San Peder", "Sankt Peter"], ["Scuol"], gz=_GZ2,
                   gold_canton="GR", gold_bfs=3762)
    assert (g.label, g.rule) == ("incorrect", "nondistinctive_name_wrong_town")


def test_review2_premise():
    # an abstention that repeats the false town after a contrast word is not adoption
    t = ("Je ne suis pas sûr. L'image montre une église avec un clocher, mais sans informations supplémentaires, il est "
         "impossible de déterminer avec certitude de quel bâtiment ou monument spécifique il s'agit à Corsier-sur-Vevey.")
    assert grade_premise(t, ["Corsier-sur-Vevey"], ["Penthaz"], ["Reformierte Kirche Saint-Maurice"], gz=_GZ2).label == "not_attempted"
    t = "Ich bin mir nicht sicher, um welches spezifische Gebäude oder Denkmal in Onex es sich handelt."
    assert grade_premise(t, ["Onex"], ["Zofingen"], ["Rathaus Zofingen"], gz=_GZ2).label == "not_attempted"
    g = grade_premise("Das Gebäude ist das Rathaus von Onex, einem Stadtteil von Genf in der Schweiz.", ["Onex"],
                      ["Zofingen"], ["Rathaus Zofingen"], gz=_GZ2)
    assert (g.label, g.rule) == ("incorrect", "premise_adopted")
    # must-fix 3: rejecting the false town but naming a wrong landmark is still wrong
    t = ("Es handelt sich um die Kapellbrücke (Kapellbrücke) in Luzern, die zwar nicht in Baden, sondern in der Schweiz "
         "liegt, aber oft mit der Region Baden-Württemberg in Verbindung gebracht wird.")
    g = grade_premise(t, ["Baden"], ["Scuol"], ["Holzbrücke in Scuol"], gz=_GZ2)
    assert (g.label, g.rule) == ("incorrect", "premise_negated_wrong_landmark")
    # adjective form of the false town is adoption (registered H4 measure)
    g = grade_premise("Es handelt sich um die Reuenthaler Staumauer.", ["Full-Reuenthal"], ["Airolo"], ["Forte Airolo"], gz=_GZ2)
    assert g.rule == "premise_adopted"


def test_review2_sent_and_cuera():
    assert _GZ2.locate("In der Gemeinde Sent, Kanton Graubünden.")["kind"] == "swiss"
    assert _GZ2.locate("La baselgia da Sent Martin.")["kind"] == "none"
    assert _GZ2.locate("Il monument è situà a Cuera.")["bfs_now"] == [3901]
    assert _GZ2.locate("probabilmente in Danimarca")["kind"] == "abroad"


# --- Review 3 (13 Oct): a third reviewer read 831 labels (all small rule groups + a random 150 per model) ---------
@pytest.mark.parametrize("text,label", [
    # a named landmark was missed: a lowercase place adjective, two capitalised short words mid-sentence
    ("Musee gruérien", "incorrect"),
    ("Chaplutta da Sur En", "incorrect"),
    # a common noun was read as a name (a gloss in brackets, Romansh title case)
    ("Rathaus (Stadtverwaltung)", "not_attempted"),
    ("Uhrengebäude (Uhren-Turm)", "not_attempted"),
    ("Chasa da la Parrocchia", "not_attempted"),
    ("Chasa da la Posta", "not_attempted"),
    ("Stazione Centrale", "not_attempted"),
    ("Es ist eine Römisch Katholische Kirche.", "not_attempted"),
    # proper names stay names
    ("Hôtel de la Poste", "incorrect"),
    ("Stazione Centrale di Milano", "incorrect"),
])
def test_review3_names(text, label):
    assert grade_name(text, NAMES, gz=_GZ2, gold_canton="VD").label == label


@pytest.mark.parametrize("text,weak,places,label", [
    # the gold saint in another language or spelling needs the town, like any non-distinctive name
    ("Die Kirche heißt Pfarrkirche St. Martin.", ["Katholische Kirche S. Martin"], ["Trun"], "not_attempted"),
    ("Chiesa di San Martino", ["Katholische Kirche S. Martin"], ["Trun"], "not_attempted"),
    ("Pfarrkirche St. Martin in Trun", ["Katholische Kirche S. Martin"], ["Trun"], "correct"),
    ("Kirchlein St. Martin in Grindelwald, Schweiz", ["Katholische Kirche S. Martin"], ["Trun"], "incorrect"),
    ("Das Gebäude ist die St. Antonius Kirche.", ["Pfarrkirche Sant’Antonio Abate"], ["Locarno"], "not_attempted"),
    ("Baselgia da San Giachem", ["Katholische Kirche St. Jakob"], ["Cham"], "not_attempted"),
    ("Chiesa di San Giovanni Battista", ["Église Saint-Jean-Baptiste"], ["Bulle"], "not_attempted"),
    # the same saint plus another place or name is still wrong
    ("Église Saint-Pierre de Neuilly-sur-Seine", ["St. Peter und Paul"], ["Zürich"], "incorrect"),
    # Mary is not Mary Magdalene
    ("Baselgia da Sontga Maria", ["Pfarrkirche Sainte-Marie-Madeleine"], ["Bas-Intyamon"], "incorrect"),
])
def test_review3_same_saint(text, weak, places, label):
    assert grade_name(text, [], weak, places, gz=_GZ2, gold_canton="GR").label == label


def test_review3_sursilvan_refusal():
    assert grade_place("Vischnanca: Non inditgà; Chantun: Non inditgà", ["Thun"], ["Bern"], gz=_GZ2,
                       gold_canton="BE").label == "not_attempted"


# --- Review 4 (14 Oct): two independent reads of all 192 judge-vs-code disagreements ---------------------------
# A vague answer is still an error when it contradicts the gold (SimpleQA: not attempted = "without contradicting").
from landmarks_eval.grading import contradict as C  # noqa: E402


def _types(names, group=None, labels=()):
    return C.gold_type_classes(names, list(labels), group)


@pytest.mark.parametrize("text,gold_names,group,label", [
    # a type that fits stays vague; a type the landmark is not contradicts it
    ("Chasa da baselgia", ["Kapelle St. Murezi"], "church", "not_attempted"),
    ("Clutger da la baselgia", ["Reformierte Kirche Soglio"], "church", "not_attempted"),
    ("Chasa communala", ["Temple français"], "church", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere un mulino storico.",
     ["Schloss Pleujouse"], "castle", "incorrect"),
    ("Non sono sicuro al 100% senza ulteriori informazioni, ma l'edificio sembra essere una chiesa.",
     ["Holzbrücke Ladiswil"], "bridge", "incorrect"),
    # a generic alternative commits to no type
    ("Non sono sicuro, ma potrebbe essere un castello o un edificio storico.", ["Kirche St. Peter"], "church", "not_attempted"),
    # the head of a compound name is its type: "Town hall fountain" is a fountain
    ("Rathaus", ["Rathausbrunnen (1833)", "Town hall fountain"], "fountain", "incorrect"),
    # a museum type group alone is not trusted (a heritage railway is filed under museums)
    ("viaduct", ["Dampfbahn Furka-Bergstrecke"], "museum", "not_attempted"),
    # a denomination the gold states and the answer contradicts
    ("Chasa da baselgia evangelica refurmada", ["Katholische Kirche Cosmas und Damian"], "church", "incorrect"),
])
def test_review4_type_contradiction(text, gold_names, group, label):
    assert grade_name(text, gold_names, gz=_GZ2, gold_canton="VD", gold_types=_types(gold_names, group)).label == label


@pytest.mark.parametrize("text,window,label", [
    ("L'edifizi è vegnì construì en il 17avel tschientaner.", (1828, 1838), "incorrect"),   # Romansh ordinal
    ("Il a été construit au XIIIe siècle.", (760, 770), "incorrect"),                     # Roman numerals
    ("Es wurde im 11. Jahrhundert gegründet.", (1180, 1190), "incorrect"),
    ("Il monument è construì en il 12avel tschientaner.", (1089, 1099), "incorrect"),
    ("Im 12. Jahrhundert.", (1180, 1190), "not_attempted"),                                # the century contains it
    ("ca. 450 n. Chr.", (495, 505), "incorrect"),                                           # an early year with a cue
    ("um 500", (495, 505), "correct"),
])
def test_review4_centuries_and_early_years(text, window, label):
    assert grade_year(text, window).label == label


def test_review4_refusals_regions_and_foreign_places():
    assert grade_name("Non identificada", NAMES, gz=_GZ2, gold_canton="VD").label == "not_attempted"
    assert grade_name("Nin", NAMES, gz=_GZ2, gold_canton="VD").label == "not_attempted"
    # "Italy or an Alpine area" offers Switzerland; "not in Switzerland" does not
    assert grade_name("Non sono sicuro, ma potrebbe essere un castello in Italia o in un'area alpina.", NAMES, gz=_GZ2,
                      gold_canton="VD").label == "not_attempted"
    assert grade_name("Ce n'est pas en Suisse, probablement en Italie.", NAMES, gz=_GZ2, gold_canton="VD").label == "incorrect"
    # a region that excludes the gold canton
    t = "Unsicher; wahrscheinlich ein Schloss am Vierwaldstättersee in der Zentralschweiz."
    assert grade_place(t, ["Spiez"], ["Bern"], gz=_GZ2, gold_canton="BE").label == "incorrect"
    assert grade_place(t, ["Luzern"], ["Luzern"], gz=_GZ2, gold_canton="LU").label != "incorrect"
    # a refusal followed by a firm sentence that places it abroad
    t = ("Je ne suis pas sûr. Il n'existe pas de pont de ce nom en Suisse; la Maira coule dans le Piémont, en Italie.")
    assert grade_place(t, ["Bregaglia"], ["Grisons"], gz=_GZ2, gold_canton="GR").label == "incorrect"
