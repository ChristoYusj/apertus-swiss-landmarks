"""Frozen data schema for every file in the dataset and the harness.

Every JSONL row written or read by the pipeline is validated against one of these
models. `extra="forbid"` makes unexpected fields an error, so silent schema drift
is caught by the tests instead of by the jury.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QID = str  # e.g. "Q123"
LANGS = ("fr", "de", "it", "rm")
LABEL_LANGS = ("en", "fr", "de", "it", "rm")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


def _check_qid(v: str) -> str:
    if not (isinstance(v, str) and v.startswith("Q") and v[1:].isdigit()):
        raise ValueError(f"not a Wikidata QID: {v!r}")
    return v


class Region(str, Enum):
    DE = "DE"  # German-speaking (BFS SPRGEB2020 = 1)
    FR = "FR"  # French-speaking (= 2)
    IT = "IT"  # Italian-speaking (= 3)
    RM = "RM"  # Romansh-speaking (= 4)


class FameTier(str, Enum):
    high = "high"
    mid = "mid"
    low = "low"


class HeritageClass(str, Enum):
    A = "A"          # Q8274529 class A, national significance
    B = "B"          # Q12126757 class B, regional significance
    local = "local"  # Q28971394 cantonal or local significance


class TypeGroup(str, Enum):
    church = "church"
    castle = "castle"
    bridge = "bridge"
    fountain = "fountain"
    tower_gate = "tower_gate"
    civic = "civic"
    museum = "museum"
    monument = "monument"


class Arm(str, Enum):
    photo_main = "photo_main"      # main Wikidata photo (P18)
    photo_alt = "photo_alt"        # different Commons photo of the same object
    text_only = "text_only"        # name given in text, no image
    trap_lowinfo = "trap_lowinfo"  # photo with too little information: abstaining is fine
    trap_premise = "trap_premise"  # question states a false town (look-alike sibling's town)
    photo_mc = "photo_mc"          # main photo + 4 named options (extension E2, docs/extensions_plan.md)
    photo_main_w2 = "photo_main_w2"  # main photo, second wording of the name/place question (extension E3)


class QType(str, Enum):
    name = "name"
    place = "place"
    year = "year"


class Expected(str, Enum):
    answer = "answer"
    answer_or_abstain = "answer_or_abstain"
    reject_premise = "reject_premise"


class Label3(str, Enum):
    """SimpleQA three-way grade. API errors get no grade (they stay a response status)."""
    correct = "correct"
    incorrect = "incorrect"
    not_attempted = "not_attempted"


class Alias(Strict):
    text: str = Field(min_length=1)
    lang: str
    source: str  # e.g. "wikidata:label", "wikidata:alias", "wikidata:sitelink", "bfs:name"
    distinctive: bool = True  # name aliases only: False = saint/type name shared by many buildings


class Landmark(Strict):
    qid: QID
    labels: dict[str, Optional[str]]
    name_aliases: list[Alias]
    p31: list[QID]
    type_group: TypeGroup
    heritage_class: HeritageClass
    kgs_number: Optional[str] = None
    canton_qid: QID
    canton_code: str = Field(pattern=r"^[A-Z]{2}$")
    canton_aliases: list[Alias]
    municipality_bfs: str = Field(pattern=r"^\d{1,4}$")
    municipality_name: str
    place_aliases: list[Alias]  # current + former/merged municipality + locality names
    language_region: Region
    region_method: Literal["BFS SPRGEB2020"] = "BFS SPRGEB2020"
    sitelinks: int = Field(ge=0)
    wikipedia_articles: int = Field(ge=0)
    fame_tier: FameTier
    fame_rank_in_region: float = Field(ge=0, le=1)  # 0 = most famous in its region
    coords: tuple[float, float]  # (lat, lon)
    commons_category: Optional[str] = None
    p18_file: str
    inception_raw: Optional[str] = None
    inception_precision: Optional[int] = None
    gold_year: Optional[int] = None
    year_window: Optional[tuple[int, int]] = None
    name_leaks_place: bool
    name_needs_place: bool = False  # no distinctive name (e.g. "Kapelle St. Antonius"): Q1 also needs the town
    ambiguous_place_aliases: list[str] = []  # town names shared with another municipality: need the canton too
    lookalike_set_id: Optional[str] = None
    # heritage objects with the same name stem in OTHER municipalities: [{"qid": ..., "municipality": ...}]
    lookalike_siblings: list[dict] = []
    stratum: str
    selection_seed: int

    _q = field_validator("qid", "canton_qid")(_check_qid)

    @field_validator("p31")
    @classmethod
    def _p31(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("p31 must not be empty")
        return [_check_qid(x) for x in v]

    @field_validator("coords")
    @classmethod
    def _coords(cls, v: tuple[float, float]) -> tuple[float, float]:
        lat, lon = v
        if not (45.7 <= lat <= 47.9 and 5.8 <= lon <= 10.6):
            raise ValueError(f"coordinates outside Switzerland: {v}")
        return v

    @model_validator(mode="after")
    def _year(self) -> "Landmark":
        if (self.gold_year is None) != (self.year_window is None):
            raise ValueError("gold_year and year_window must be both set or both null")
        if self.year_window and not (self.year_window[0] <= (self.gold_year or 0) <= self.year_window[1]):
            raise ValueError("gold_year must lie inside year_window")
        if not self.name_aliases:
            raise ValueError("at least one name alias required")
        if not self.place_aliases or not self.canton_aliases:
            raise ValueError("place and canton aliases required")
        expected_tier = "low" if self.wikipedia_articles == 0 else "mid" if self.wikipedia_articles <= 2 else "high"
        if self.fame_tier.value != expected_tier:
            raise ValueError(f"fame_tier {self.fame_tier.value} inconsistent with {self.wikipedia_articles} Wikipedia articles")
        return self


class TestCase(Strict):
    __test__ = False  # not a pytest test class
    item_id: str
    landmark_qid: QID
    arm: Arm
    question_type: QType
    lang: Literal["fr", "de", "it", "rm"]
    template_id: str
    prompt_version: str
    question_text: str = Field(min_length=5)
    image_id: Optional[str] = None
    expected_behavior: Expected
    trap_type: Optional[str] = None
    false_premise_claim: Optional[str] = None
    false_premise_aliases: list[str] = []
    paired_control_item_id: Optional[str] = None
    confusable_with: list[QID] = []
    options: list[str] = []                      # photo_mc: the four options, in letter order A-D
    option_qids: list[QID] = []                  # photo_mc: the landmark behind each option
    answer_option: Optional[Literal["A", "B", "C", "D"]] = None
    split: Literal["main", "dev"] = "main"

    _q = field_validator("landmark_qid")(_check_qid)

    @model_validator(mode="after")
    def _consistency(self) -> "TestCase":
        needs_image = self.arm != Arm.text_only
        if needs_image and not self.image_id:
            raise ValueError(f"{self.arm} item needs an image_id")
        if not needs_image and self.image_id:
            raise ValueError("text_only item must not have an image")
        expect_id = f"{self.landmark_qid}-{self.arm.value}-{self.question_type.value}-{self.lang}"
        if not self.item_id.startswith(expect_id):
            raise ValueError(f"item_id must start with {expect_id}")
        if self.arm == Arm.trap_premise:
            if self.expected_behavior != Expected.reject_premise or not self.false_premise_claim:
                raise ValueError("premise traps need reject_premise + false_premise_claim")
        elif self.expected_behavior == Expected.reject_premise:
            raise ValueError("reject_premise only allowed on premise traps")
        if self.arm == Arm.trap_lowinfo and self.expected_behavior != Expected.answer_or_abstain:
            raise ValueError("low-info traps must be answer_or_abstain")
        if self.arm == Arm.photo_mc:
            if len(self.options) != 4 or len(self.option_qids) != 4 or not self.answer_option:
                raise ValueError("photo_mc items need 4 options, their QIDs and the answer letter")
            if self.option_qids["ABCD".index(self.answer_option)] != self.landmark_qid or len(set(self.options)) != 4:
                raise ValueError("photo_mc: the answer must be the landmark itself and the options must differ")
        elif self.options or self.option_qids or self.answer_option:
            raise ValueError("options only on photo_mc items")
        return self


ALLOWED_LICENSES = {
    "CC0-1.0", "PDM-1.0", "CC-BY-1.0", "CC-BY-SA-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0",
    "CC-BY-SA-2.0", "CC-BY-SA-2.5", "CC-BY-SA-3.0", "CC-BY-SA-4.0", "LAL-1.3",
}


class ImageRecord(Strict):
    image_id: str
    landmark_qid: QID
    role: Literal["main_p18", "alt", "trap"]
    commons_title: str
    commons_page_url: str
    author: str = Field(min_length=1)
    license_short: str
    license_spdx: str
    license_url: Optional[str] = None
    attribution_text: str = Field(min_length=10)
    modifications: str
    commons_sha1: str
    shipped_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    orig_w: int
    orig_h: int
    shipped_w: int
    shipped_h: int
    upload_timestamp: Optional[str] = None
    taken_timestamp: Optional[str] = None
    post_cutoff: bool = False
    phash: Optional[str] = None
    phash_dist_to_main: Optional[int] = None
    faces_detected: int = Field(ge=0)
    pii_decision: Literal["keep", "exclude", "pending"]
    pii_reason: Optional[str] = None
    pii_reviewer_ids: list[str] = []
    retrieved_at: str

    _q = field_validator("landmark_qid")(_check_qid)

    @field_validator("license_spdx")
    @classmethod
    def _lic(cls, v: str) -> str:
        if v not in ALLOWED_LICENSES:
            raise ValueError(f"license not on allowlist: {v}")
        return v


class Response(Strict):
    item_id: str
    model: str
    returned_model_id: Optional[str] = None
    endpoint_host: str
    params: dict
    prompt_version: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_text: Optional[str]
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    latency_s: Optional[float] = None
    status: Literal["ok", "api_error", "skipped_no_vision"]
    error: Optional[str] = None
    run_id: str
    harness_version: str
    timestamp: str

    @model_validator(mode="after")
    def _status(self) -> "Response":
        if self.status == "ok" and self.response_text is None:
            raise ValueError("ok responses need response_text")
        return self


class Judgement(Strict):
    item_id: str
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_label: Optional[Label3]
    code_rule: str
    judge_label: Optional[Label3] = None
    judge_raw: Optional[str] = None
    judge_model: Optional[str] = None
    judge_prompt_version: Optional[str] = None
    predicted_place: Optional[str] = None
    canton_correct: Optional[bool] = None
    municipality_correct: Optional[bool] = None
    year_within_window: Optional[bool] = None
    final_label: Optional[Label3]
    final_source: Literal["judge", "code", "none"]


class HumanLabel(Strict):
    item_id: str
    annotator_id: Literal["A1", "A2", "A3"]
    label: Label3
    in_overlap: bool
    guideline_version: str
    timestamp: str
    used_translation: bool = False  # relied on the English machine gloss of the answer
    unsure: bool = False


SCHEMAS = {
    "landmarks": Landmark,
    "test_cases": TestCase,
    "images": ImageRecord,
    "responses": Response,
    "judgements": Judgement,
    "human_audit": HumanLabel,
}
