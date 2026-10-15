"""Item metadata: the q-v1 template review statuses never carry over to the extension templates."""

from landmarks_eval.build.assemble import _translation


def test_q_v1_statuses():
    assert _translation({"prompt_version": "q-v1", "lang": "fr"})["translation_review_status"].startswith("reviewed by")
    assert _translation({"prompt_version": "q-v1", "lang": "de"})["translation_review_status"] == "back-translation checked"


def test_extension_templates_are_not_reviewed():
    for lang in ("fr", "de", "it"):
        t = _translation({"prompt_version": "q-v2-mc", "lang": lang})
        assert t["translation_review_status"] == "not reviewed (extension template)"
        assert "back-translation" not in t["translation_method"]
    assert "native speaker" in _translation({"prompt_version": "q-v2-w2", "lang": "rm"})["translation_review_status"]
