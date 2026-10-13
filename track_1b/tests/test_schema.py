"""Step-0 checkpoint: valid rows are accepted, deliberately broken rows are rejected."""

import copy

import pytest
from pydantic import ValidationError

from landmarks_eval.schema import ImageRecord, Judgement, Landmark, Response, TestCase

SHA = "a" * 64

LANDMARK = dict(
    qid="Q1", labels={"fr": "Fontaine de la Justice", "de": None, "it": None, "rm": None, "en": None},
    name_aliases=[{"text": "Fontaine de la Justice", "lang": "fr", "source": "wikidata:label"}],
    p31=["Q483453"], type_group="fountain", heritage_class="B", kgs_number="9999",
    canton_qid="Q12771", canton_code="VD",
    canton_aliases=[{"text": "Vaud", "lang": "fr", "source": "wikidata:label"}],
    municipality_bfs="5586", municipality_name="Lausanne",
    place_aliases=[{"text": "Lausanne", "lang": "fr", "source": "bfs:name"}],
    language_region="FR", sitelinks=1, fame_tier="low", fame_rank_in_region=0.9,
    coords=(46.5216, 6.6325), p18_file="Fontaine.jpg",
    inception_raw="1585-01-01T00:00:00Z", inception_precision=9, gold_year=1585, year_window=(1580, 1590),
    name_leaks_place=False, stratum="FR|low", selection_seed=20261013,
)

CASE = dict(
    item_id="Q1-photo_main-name-fr", landmark_qid="Q1", arm="photo_main", question_type="name",
    lang="fr", template_id="name.v1", prompt_version="p1", question_text="Quel est ce monument ?",
    image_id="img1", expected_behavior="answer",
)

IMAGE = dict(
    image_id="img1", landmark_qid="Q1", role="main_p18", commons_title="File:F.jpg",
    commons_page_url="https://commons.wikimedia.org/wiki/File:F.jpg", author="Someone",
    license_short="CC BY-SA 4.0", license_spdx="CC-BY-SA-4.0",
    attribution_text="F.jpg by Someone, CC BY-SA 4.0, via Wikimedia Commons", modifications="resized to 500 px; EXIF removed",
    commons_sha1="b" * 40, shipped_sha256=SHA, orig_w=4000, orig_h=3000, shipped_w=500, shipped_h=375,
    faces_detected=0, pii_decision="keep", retrieved_at="2026-10-13T12:00:00Z",
)

RESPONSE = dict(
    item_id="Q1-photo_main-name-fr", model="swiss-ai/Apertus-v1.5-70B", endpoint_host="api.example",
    params={"temperature": 0}, prompt_version="p1", request_sha256=SHA, response_text="La Fontaine de la Justice.",
    status="ok", run_id="r1", harness_version="0.1.0", timestamp="2026-10-14T10:00:00Z",
)

JUDGEMENT = dict(
    item_id="Q1-photo_main-name-fr", response_sha256=SHA, code_label="correct", code_rule="alias_match",
    final_label="correct", final_source="code",
)


def mutate(base, **changes):
    d = copy.deepcopy(base)
    for k, v in changes.items():
        if v is KeyError:
            d.pop(k)
        else:
            d[k] = v
    return d


@pytest.mark.parametrize("model,row", [
    (Landmark, LANDMARK),
    (Landmark, mutate(LANDMARK, gold_year=None, year_window=None, inception_precision=7)),
    (Landmark, mutate(LANDMARK, lookalike_set_id="justice-fountain", fame_tier="high", fame_rank_in_region=0.0)),
    (TestCase, CASE),
    (TestCase, mutate(CASE, item_id="Q1-text_only-place-de", arm="text_only", question_type="place", lang="de", image_id=None)),
    (TestCase, mutate(CASE, item_id="Q1-trap_premise-year-fr", arm="trap_premise", question_type="year",
                      expected_behavior="reject_premise", false_premise_claim="Bern", trap_type="premise_sibling_town")),
    (ImageRecord, IMAGE),
    (ImageRecord, mutate(IMAGE, license_spdx="CC0-1.0", role="alt", phash="ff00", phash_dist_to_main=30)),
    (ImageRecord, mutate(IMAGE, pii_decision="exclude", faces_detected=2, pii_reason="faces")),
    (Response, RESPONSE),
    (Response, mutate(RESPONSE, status="api_error", response_text=None, error="HTTP 500")),
    (Response, mutate(RESPONSE, finish_reason="stop", usage={"total_tokens": 10}, latency_s=0.5)),
    (Judgement, JUDGEMENT),
    (Judgement, mutate(JUDGEMENT, judge_label="incorrect", final_label="incorrect", final_source="judge")),
    (Judgement, mutate(JUDGEMENT, code_label=None, final_label=None, final_source="none")),
])
def test_valid_rows_accepted(model, row):
    model.model_validate(row)


@pytest.mark.parametrize("model,row", [
    (Landmark, mutate(LANDMARK, qid="123")),                         # not a QID
    (Landmark, mutate(LANDMARK, gold_year=1700)),                    # year outside window
    (Landmark, mutate(LANDMARK, coords=(48.8566, 2.3522))),          # Paris, not Switzerland
    (Landmark, mutate(LANDMARK, unexpected="x")),                    # extra field
    (TestCase, mutate(CASE, image_id=None)),                         # photo item without image
    (TestCase, mutate(CASE, item_id="Q2-photo_main-name-fr")),       # id does not match fields
    (TestCase, mutate(CASE, expected_behavior="reject_premise")),    # premise only on premise traps
    (ImageRecord, mutate(IMAGE, license_spdx="CC-BY-NC-4.0")),       # NC not allowed
    (ImageRecord, mutate(IMAGE, shipped_sha256="xyz")),              # bad hash
    (ImageRecord, mutate(IMAGE, author="")),                         # attribution needs an author
    (Response, mutate(RESPONSE, response_text=None)),                # ok without text
    (Response, mutate(RESPONSE, status="weird")),
    (Response, mutate(RESPONSE, request_sha256="short")),
    (Judgement, mutate(JUDGEMENT, final_source="me")),
    (Judgement, mutate(JUDGEMENT, code_label="maybe")),
    (Judgement, mutate(JUDGEMENT, response_sha256=KeyError)),
])
def test_broken_rows_rejected(model, row):
    with pytest.raises(ValidationError):
        model.model_validate(row)
