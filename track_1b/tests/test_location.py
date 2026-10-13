"""Location extraction (which place does an answer name?) and the multiple-testing helpers.
Every case below is a real answer pattern from the official run that an earlier version got wrong."""

import pytest

from landmarks_eval.analysis import Gazetteer
from landmarks_eval.metrics import bootstrap_p, holm

GZ = Gazetteer({
    "cantons": {"ZG": {"names": ["zug", "zoug"], "region": "DE"}, "GR": {"names": ["graubunden", "grischun", "grigioni"], "region": None},
                "BE": {"names": ["bern", "berna", "berne"], "region": None}, "SG": {"names": ["st gallen", "sankt gallen"], "region": "DE"},
                "AG": {"names": ["aargau"], "region": "DE"}},
    "municipalities": [
        {"bfs": 1711, "names": ["zug"], "canton": "ZG", "region": "DE", "current": True},
        {"bfs": 351, "names": ["bern", "berne", "berna"], "canton": "BE", "region": "DE", "current": True},
        {"bfs": 934, "names": ["oberhofen", "oberhofen am thunersee"], "canton": "BE", "region": "DE", "current": True},
        {"bfs": 4174, "names": ["oberhofen"], "canton": "AG", "region": "DE", "current": False},
        {"bfs": 3787, "names": ["st moritz"], "canton": "GR", "region": "DE", "current": True},
        {"bfs": 3762, "names": ["scuol"], "canton": "GR", "region": "RM", "current": True},
        {"bfs": 3763, "names": ["tarasp"], "canton": "GR", "region": None, "current": False},
        {"bfs": 3595, "names": ["roten"], "canton": "GR", "region": None, "current": False},
        {"bfs": 3274, "names": ["buchs"], "canton": "SG", "region": "DE", "current": True},
        {"bfs": 4004, "names": ["buchs"], "canton": "AG", "region": "DE", "current": True},
        {"bfs": 6153, "names": ["st jean"], "canton": "VS", "region": "FR", "current": False},
        {"bfs": 2236, "names": ["st martin"], "canton": "FR", "region": "FR", "current": True},
    ],
    "countries": {"LI": ["liechtenstein", "vaduz"], "FR": ["frankreich", "france"], "DE": ["deutschland"]},
})


def where(text):
    loc = GZ.locate(text)
    return loc.get("canton") if loc["kind"] == "swiss" else (f"abroad:{loc['country']}" if loc["kind"] == "abroad" else loc["kind"])


@pytest.mark.parametrize("text,expected", [
    ("Eisenbahnbrücke mit Zug in einer bergigen Landschaft.", "none"),          # Zug = train
    ("Das Schloss liegt in Zug.", "ZG"),
    ("Il Chastè da Tarasp è situà en la vischnanca da Tarasp, en il chantun Grischun.", "GR"),  # former municipality
    ("Das Bild zeigt ein historisches Gebäude mit einem roten Dach.", "none"),  # lower-case adjective, not the village
    ("Castel Vaduz", "abroad:LI"),
    ("Die Kirche von Saint-Jean-Baptiste in Saint-Jean-Baptiste, Frankreich.", "abroad:FR"),  # hyphenated longer name
    ("Die Stiftskirche St. Peter und Paul in Konstanz, Deutschland.", "abroad:DE"),
    ("La baselgia da St. Martin", "none"),                                       # a church, not the town
    ("In der Gemeinde **Buchs** im Kanton **Sankt Gallen**, Schweiz.", "SG"),   # ambiguous town + canton
    ("Il casti da Oberhofen è situà en la vischnanca da Oberhofen ed il chantun da Berna.", "BE"),
    ("Das Gebäude befindet sich in der Gemeinde St. Moritz im Kanton Graubünden.", "GR"),
    ("Je ne suis pas sûr de l'emplacement exact de ce bâtiment.", "none"),
    ("Un château typique de Suisse.", "switzerland_only"),
])
def test_locate(text, expected):
    assert where(text) == expected


def test_region_and_level():
    loc = GZ.locate("Questa è la chiesa di San Giovanni a Scuol, nel Canton Grigioni.")
    assert (loc["level"], loc["canton"], loc["region"], loc["bfs"]) == ("municipality", "GR", "RM", 3762)
    loc = GZ.locate("Im Kanton Graubünden.")
    assert (loc["level"], loc["canton"], loc["region"]) == ("canton", "GR", None)  # multilingual canton: no region


def test_holm_and_bootstrap_p():
    h = holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert h["a"]["p_holm"] == pytest.approx(0.03) and h["c"]["p_holm"] == pytest.approx(0.06)
    assert h["b"]["p_holm"] == pytest.approx(0.06)          # monotone step-down
    assert [k for k, v in h.items() if v["reject_at_0.05"]] == ["a"] and "d" not in h
    assert bootstrap_p([0.1] * 99 + [-0.1]) == pytest.approx(0.02)
    assert bootstrap_p([0.0] * 10) == 1.0
