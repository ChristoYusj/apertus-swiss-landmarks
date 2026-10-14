"""Descriptive arm contrasts (photo_main vs photo_alt, photo_main vs trap_lowinfo): pairing and McNemar counts."""

from landmarks_eval.score import _paired


def _r(qid, arm, lang, qtype, label):
    return {"landmark_qid": qid, "arm": arm, "lang": lang, "qtype": qtype, "label": label}


def test_pairs_only_matching_landmark_language_and_question():
    rows = [_r("Q1", "photo_main", "fr", "name", "correct"), _r("Q1", "photo_alt", "fr", "name", "not_attempted"),
            _r("Q2", "photo_main", "fr", "name", "incorrect"), _r("Q2", "photo_alt", "fr", "name", "incorrect"),
            _r("Q3", "photo_main", "de", "name", "not_attempted"), _r("Q3", "photo_alt", "de", "name", "incorrect"),
            _r("Q1", "photo_main", "it", "name", "correct"),            # no alt in Italian: not paired
            _r("Q4", "photo_alt", "fr", "name", "correct"),              # no main: not paired
            _r("Q1", "photo_main", "fr", "place", "incorrect"), _r("Q1", "photo_alt", "fr", "place", "correct")]
    out = _paired(rows, "photo_main", "photo_alt", ("name", "place", "year"))
    assert set(out) == {"name", "place"}                                 # no year pairs -> no entry
    n = out["name"]
    assert (n["n_pairs"], n["landmarks"]) == (3, 3)
    assert n["photo_main"]["correct"] == 1 and n["photo_alt"]["incorrect"] == 2
    assert (n["correct_only_photo_main"], n["correct_only_photo_alt"]) == (1, 0)
    assert (n["incorrect_only_photo_main"], n["incorrect_only_photo_alt"]) == (0, 1)
    assert out["place"]["correct_only_photo_alt"] == 1 and 0 < out["place"]["correct_mcnemar_p"] <= 1
