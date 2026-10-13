"""OpenAI-compatible chat client (stdlib + requests only), used for both the tested model and the judge.

* Images are sent as base64 data URLs (`image_url`), the format Apertus 1.5 accepts on vLLM.
* Retries only on 429 / 5xx / timeouts / connection errors, with exponential backoff.
* `<think>...</think>` reasoning blocks are stripped from answers (thinking variants).
* Configured purely through environment variables: LLM_NAME, LLM_BASE_URL, LLM_API_KEY
  (judge: JUDGE_MODEL, JUDGE_BASE_URL, JUDGE_API_KEY). Keys are never logged or cached.
"""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class Endpoint:
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout: float = 180.0

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc

    @classmethod
    def from_env(cls, prefix: str = "LLM") -> "Endpoint | None":
        name_var = "LLM_NAME" if prefix == "LLM" else f"{prefix}_MODEL"
        model, base, key = os.environ.get(name_var), os.environ.get(f"{prefix}_BASE_URL"), os.environ.get(f"{prefix}_API_KEY")
        if not (model and base and key):
            return None
        return cls(model=model, base_url=base.rstrip("/"), api_key=key)


def image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


def build_messages(question: str, jpeg: bytes | None, system: str | None = None) -> list[dict]:
    msgs = [{"role": "system", "content": system}] if system else []
    content = ([image_part(jpeg)] if jpeg else []) + [{"type": "text", "text": question}]
    msgs.append({"role": "user", "content": content if jpeg else question})
    return msgs


@dataclass
class Result:
    text: str | None
    status: str  # ok | api_error
    finish_reason: str | None = None
    usage: dict | None = None
    latency_s: float | None = None
    returned_model: str | None = None
    error: str | None = None


def chat(ep: Endpoint, messages: list[dict], params: dict, retries: int = 6) -> Result:
    url = f"{ep.base_url}/chat/completions"
    body = {"model": ep.model, "messages": messages, **params}
    last = "unknown error"
    for attempt in range(retries):
        t0 = time.monotonic()
        try:
            r = requests.post(url, json=body, timeout=ep.timeout,
                              headers={"Authorization": f"Bearer {ep.api_key}", "Content-Type": "application/json"})
        except (requests.Timeout, requests.ConnectionError) as e:
            last = f"{type(e).__name__}"
            time.sleep(min(5 * 2 ** attempt, 90))
            continue
        latency = time.monotonic() - t0
        if r.status_code in RETRY_STATUS:
            last = f"HTTP {r.status_code}"
            ra = r.headers.get("Retry-After", "")
            time.sleep(int(ra) if ra.isdigit() else min(5 * 2 ** attempt, 90))
            continue
        if r.status_code >= 400:  # non-retryable (bad request, auth, model not allowed)
            return Result(None, "api_error", error=f"HTTP {r.status_code}: {r.text[:300]}", latency_s=latency)
        d = r.json()
        ch = (d.get("choices") or [{}])[0]
        text = (ch.get("message") or {}).get("content")
        if isinstance(text, list):  # some servers return content parts
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        text = THINK.sub("", text or "").strip()
        return Result(text, "ok", ch.get("finish_reason"), d.get("usage"), round(latency, 3), d.get("model"))
    return Result(None, "api_error", error=f"gave up after {retries} attempts: {last}")


def supports_images(ep: Endpoint, sample_jpeg: bytes) -> bool:
    """Probe with one real dataset image; models without vision get the text-only arm only."""
    res = chat(ep, build_messages("Reply with the word OK.", sample_jpeg), {"max_tokens": 5, "temperature": 0}, retries=3)
    return res.status == "ok"
