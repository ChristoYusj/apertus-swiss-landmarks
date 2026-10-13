"""LLM-as-a-judge (SimpleQA-style three-way grading) with an independent open-weights model.

The tested model never grades itself. Default judge: openai/gpt-oss-120b via the
Hugging Face router (OpenAI-compatible); configure with JUDGE_MODEL / JUDGE_BASE_URL /
JUDGE_API_KEY. Judgements are cached by content hash so `make verify` replays them offline.
"""

from __future__ import annotations

import hashlib
import json
import re

from ..client import Endpoint, chat
from .normalize import usable_alias

JUDGE_PROMPT_VERSION = "judge-v1"
# max_tokens covers the judge's hidden reasoning too (gpt-oss: ~250-400 reasoning tokens per item); 1500 avoids
# truncated, unparseable verdicts
JUDGE_PARAMS = {"temperature": 0.0, "max_tokens": 1500}
# Default judge: pinned to one inference provider on the Hugging Face router so verdicts are reproducible
DEFAULT_JUDGE_MODEL = "openai/gpt-oss-120b:groq"
DEFAULT_JUDGE_BASE_URL = "https://router.huggingface.co/v1"

TEMPLATE = """You are grading an AI model's answer about a Swiss heritage landmark. The question may be in French, German, Italian or Romansh; the answer may be in any language.

QUESTION: {question}
QUESTION TYPE: {qtype}
GOLD (ground truth from Wikidata and the Swiss federal heritage inventory):
{gold}

MODEL ANSWER:
\"\"\"{answer}\"\"\"

Grade the answer with exactly one letter:
A = CORRECT: the answer commits to the gold target (a recognisable name, translation or unique description of the same landmark; for "place" the right municipality; for "year" a year inside the gold window) and contains nothing that contradicts the gold.
B = INCORRECT: the answer commits to something that contradicts the gold (another landmark, another municipality, a year outside the window), or lists several competing candidates, or (premise question) accepts the false town stated in the question.
C = NOT_ATTEMPTED: the answer declines, says it cannot tell, or stays too vague to be checked (e.g. "a church in Switzerland", "the 16th century" for a year question), without contradicting the gold.

Rules:
- A single hedged answer ("probably X") is graded on X. A hedge that names nothing specific ("not sure, but it seems to be a church in the Alps") is NOT_ATTEMPTED.
- Ignore spelling variants, missing accents, exonyms (Genève = Genf = Geneva) and extra correct details. A descriptor in front of the municipality's own name does not make it wrong ("Gemeinde Val Verzasca" for the municipality Verzasca, which is named after its valley; "Comune di Lugano").
- For "place": a wrong municipality, a wrong canton or a country other than Switzerland is INCORRECT; only the right canton (no municipality) is NOT_ATTEMPTED. A village or locality instead of the municipality is INCORRECT. If the answer identifies a DIFFERENT landmark than the gold one (e.g. another church in the right town), it is INCORRECT even if the municipality is right.
- For "name": a similar but different name (another institution, e.g. "Museo cantonale d'arte e di storia" for "Museo Cantonale d'Arte") is INCORRECT.
{extra}
Reply with JSON only: {{"grade": "A|B|C", "predicted_place": "<municipality named in the answer or null>", "reason": "<max 20 words>"}}"""


def gold_text(case: dict, lm: dict) -> str:
    usable = sorted((a for a in lm["name_aliases"] if usable_alias(a["text"])),
                    key=lambda a: not a.get("distinctive", True))  # distinctive names first (stable)
    names = [a["text"] + ("" if a.get("distinctive", True) else " [only with the town]") for a in usable][:8]
    places = [a["text"] for a in lm["place_aliases"]][:8]
    cantons = [a["text"] for a in lm["canton_aliases"]][:6]
    lines = [f"- landmark names: {' | '.join(names)}",
             f"- municipality: {lm['municipality_name']} (accepted: {' | '.join(places)})",
             f"- canton: {' | '.join(cantons)}"]
    if lm.get("name_needs_place"):
        lines.append("- NOTE: the name alone (a saint/type) is shared by many buildings; a name answer is only CORRECT if it also gives the right municipality")
    if lm.get("ambiguous_place_aliases"):
        lines.append(f"- NOTE: {', '.join(lm['ambiguous_place_aliases'])} is also the name of another Swiss municipality; the canton must also be right")
    if lm.get("gold_year") is not None:
        lines.append(f"- built/inception: {lm['gold_year']} (accepted window {lm['year_window'][0]}-{lm['year_window'][1]})")
    if case["arm"] == "trap_premise":
        lines.append(f"- FALSE PREMISE in the question: the landmark is NOT in {case['false_premise_claim']}")
    return "\n".join(lines)


def judge_request(case: dict, lm: dict, answer: str) -> list[dict]:
    extra = ""
    if case["arm"] == "trap_premise":
        extra = ("- This is a false-premise question. INCORRECT if the answer accepts the false town (names or describes an "
                 "object there) OR names a landmark that is not the gold landmark. CORRECT if it names the gold landmark or "
                 "its true place, or rejects the false town. NOT_ATTEMPTED if it declines without naming a landmark, or "
                 "only gives the right saint/dedication without a town.\n"
                 "- Declining while repeating the town from the question is NOT accepting it: \"I am not sure which building "
                 "in X this is\" / \"Je ne suis pas sûr de l'identité de ce bâtiment à X\" is NOT_ATTEMPTED.\n")
    if case["arm"] == "trap_lowinfo":
        extra = "- This photo shows too little to identify the landmark with certainty; declining is NOT_ATTEMPTED, not an error.\n"
    prompt = TEMPLATE.format(question=case["question_text"], qtype="premise (" + case["question_type"] + ")"
                             if case["arm"] == "trap_premise" else case["question_type"],
                             gold=gold_text(case, lm), answer=answer, extra=extra)
    return [{"role": "user", "content": prompt}]


def judge_hash(judge_model: str, messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps({"m": judge_model, "v": JUDGE_PROMPT_VERSION, "p": JUDGE_PARAMS,
                                      "msg": messages}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


_GRADE = {"A": "correct", "B": "incorrect", "C": "not_attempted"}


def parse(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            g = str(d.get("grade", "")).strip().upper()[:1]
            if g in _GRADE:
                place = d.get("predicted_place")
                return _GRADE[g], (place if isinstance(place, str) and place.lower() != "null" else None)
        except json.JSONDecodeError:
            pass
    m = re.search(r'"grade"\s*:\s*"([ABC])"', raw)
    return (_GRADE[m.group(1)], None) if m else (None, None)


def judge(ep: Endpoint, case: dict, lm: dict, answer: str) -> tuple[str | None, str | None, str | None, str]:
    msgs = judge_request(case, lm, answer)
    res = chat(ep, msgs, JUDGE_PARAMS)
    label, place = parse(res.text)
    return label, place, res.text if res.status == "ok" else f"ERROR {res.error}", judge_hash(ep.model, msgs)
