"""Unit tests for the dataset-construction rules (answer keys must be right)."""

from landmarks_eval.build.candidates import year_gold
from landmarks_eval.build.commons import license_spdx
from landmarks_eval.build.sample import tier_of
from landmarks_eval.grading.normalize import contains_phrase, is_generic, normalize, split_bilingual

N = "http://wikiba.se/ontology#NormalRank"
P = "http://wikiba.se/ontology#PreferredRank"
D = "http://wikiba.se/ontology#DeprecatedRank"


def test_year_precision_year():
    y, w, raw, p = year_gold([("1585-01-01T00:00:00Z", 9, N)])
    assert (y, w, p) == (1585, (1580, 1590), 9)


def test_year_month_precision_counts_as_year():
    assert year_gold([("1918-05-01T00:00:00Z", 10, N)])[:2] == (1918, (1913, 1923))


def test_year_decade_window_covers_decade_plus_5():
    assert year_gold([("1587-01-01T00:00:00Z", 8, N)])[:2] == (1580, (1575, 1594))


def test_century_precision_has_no_gold():
    assert year_gold([("1100-01-01T00:00:00Z", 7, N)])[0] is None


def test_conflicting_years_have_no_gold():
    assert year_gold([("1500-01-01T00:00:00Z", 9, N), ("1650-01-01T00:00:00Z", 9, N)])[0] is None


def test_preferred_rank_wins_and_deprecated_ignored():
    assert year_gold([("1500-01-01T00:00:00Z", 9, N), ("1650-01-01T00:00:00Z", 9, P)])[0] == 1650
    assert year_gold([("1500-01-01T00:00:00Z", 9, D), ("1650-01-01T00:00:00Z", 9, N)])[0] == 1650


def test_mixed_precision_is_not_used():
    assert year_gold([("1650-01-01T00:00:00Z", 9, N), ("1600-01-01T00:00:00Z", 7, N)])[0] is None


def test_tiers_from_wikipedia_articles():
    assert [tier_of(n) for n in (0, 1, 2, 3, 40)] == ["low", "mid", "mid", "high", "high"]


def test_normalize_accents_eszett_and_saints():
    assert normalize("Gerechtigkeitsbrunnen, Bern") == "gerechtigkeitsbrunnen bern"
    assert normalize("Straße") == "strasse"
    assert normalize("Église Saint-Pierre") == normalize("Eglise St. Pierre") == "eglise st pierre"
    assert normalize("San Vittore") == "st vittore"


def test_generic_labels():
    assert is_generic("Reformierte Kirche")
    assert is_generic("Église réformée")
    assert not is_generic("Reformierte Kirche Wängi")
    assert not is_generic("Gerechtigkeitsbrunnen")


def test_bilingual_split_and_phrase():
    assert split_bilingual("Biel/Bienne") == ["Biel/Bienne", "Biel", "Bienne"]
    assert split_bilingual("Bulle") == ["Bulle"]
    assert contains_phrase("Kunsthalle Bern", "Bern") and not contains_phrase("Bernhardzell", "Bern")


def test_license_mapping():
    assert license_spdx("cc-by-sa-4.0") == "CC-BY-SA-4.0"
    assert license_spdx("cc-by-2.0") == "CC-BY-2.0"
    assert license_spdx("cc0") == "CC0-1.0"
    assert license_spdx("pd") == "PDM-1.0"
    assert license_spdx("cc-by-nc-sa-4.0") is None
    assert license_spdx("gfdl") is None
    assert license_spdx(None) is None
