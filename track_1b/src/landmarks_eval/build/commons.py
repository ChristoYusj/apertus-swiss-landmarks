"""Wikimedia Commons: licence/author metadata, 500 px thumbnails, EXIF stripping, face pre-flag.

Licence policy (dataset T&C: every item's licence must be stated and redistributable):
  allowed  CC0, public domain, CC BY 1.0-4.0, CC BY-SA 1.0-4.0, Free Art License 1.3
  rejected NC, ND, GFDL-only, unknown/missing licence, missing author, files nominated
           for deletion, files tagged with personality-rights warnings
Images are shipped as 500 px wide JPEG re-encodes with all metadata removed; the
modification is recorded per image as required by CC BY(-SA).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import re
import time
from pathlib import Path

import requests

from .sparql import USER_AGENT

API = "https://commons.wikimedia.org/w/api.php"
WIDTH = 500
MODIFICATION = "downscaled to 500 px width and re-encoded as JPEG; embedded metadata (EXIF) removed"
CUTOFF = "2026-07-14"  # earliest documented existence of Apertus 1.5 (images strictly after = unseen)

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


CACHE_DIR: Path | None = None  # set by the builder; caches API answers and thumbnails


def _get(params: dict, retries: int = 6) -> dict:
    import json as _json
    key = hashlib.sha256(_json.dumps(params, sort_keys=True).encode()).hexdigest()
    cpath = CACHE_DIR / "api" / f"{key}.json" if CACHE_DIR else None
    if cpath and cpath.exists():
        return _json.loads(cpath.read_text(encoding="utf-8"))
    data = _get_live(params, retries)
    if cpath:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _get_live(params: dict, retries: int) -> dict:
    for attempt in range(retries):
        r = _session.get(API, params={"format": "json", "formatversion": "2", **params}, timeout=60)
        if r.status_code in (429, 503):
            time.sleep(min(10 * 2 ** attempt, 120))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Commons API kept rate-limiting")


def license_spdx(code: str | None) -> str | None:
    """Map Commons extmetadata 'License' codes to SPDX ids; None = not allowed."""
    if not code:
        return None
    c = code.strip().lower()
    if c in ("cc0", "cc-zero", "cc0-1.0"):
        return "CC0-1.0"
    if c in ("pd", "public domain", "pdm", "pd-self", "pd-old", "pd-author", "pd-art") or c.startswith("pd-"):
        return "PDM-1.0"
    if c in ("lal", "fal", "lal-1.3", "free art license"):
        return "LAL-1.3"
    m = re.fullmatch(r"cc-by(-sa)?-(1\.0|2\.0|2\.5|3\.0|4\.0)(-[a-z]{2,3})?", c)
    if m:
        return f"CC-BY{'-SA' if m.group(1) else ''}-{m.group(2)}"
    return None


def clean_html(s: str | None) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


BLOCK_CATEGORY_PATTERNS = (r"deletion request", r"personality rights", r"copyright violation", r"possibly unfree")


def file_info(titles: list[str]) -> dict[str, dict]:
    """Batch-fetch licence/author/size/thumbnail metadata for Commons file titles."""
    out = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        d = _get({"action": "query", "titles": "|".join(chunk), "prop": "imageinfo|categories",
                  "iiprop": "url|size|sha1|extmetadata|timestamp|mime", "iiurlwidth": WIDTH, "cllimit": "max",
                  "iiextmetadatafilter": "LicenseShortName|License|LicenseUrl|Artist|Credit|DateTimeOriginal|Restrictions"})
        norm = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for p in d["query"]["pages"]:
            if p.get("missing") or not p.get("imageinfo"):
                continue
            ii, em = p["imageinfo"][0], p["imageinfo"][0].get("extmetadata", {})
            cats = [c["title"] for c in p.get("categories", [])]
            title = p["title"]
            out[norm.get(title, title)] = out[title] = {
                "title": title, "page_url": ii.get("descriptionurl"), "thumb_url": ii.get("thumburl"),
                "orig_w": ii.get("width"), "orig_h": ii.get("height"), "sha1": ii.get("sha1"), "mime": ii.get("mime"),
                "upload_ts": ii.get("timestamp"),
                "taken": clean_html(em.get("DateTimeOriginal", {}).get("value")),
                "license_code": em.get("License", {}).get("value"),
                "license_short": clean_html(em.get("LicenseShortName", {}).get("value")),
                "license_url": em.get("LicenseUrl", {}).get("value"),
                "author": clean_html(em.get("Artist", {}).get("value")),
                "credit": clean_html(em.get("Credit", {}).get("value")),
                "restrictions": clean_html(em.get("Restrictions", {}).get("value")),
                "categories": cats,
            }
    return out


def reject_reason(info: dict) -> str | None:
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp", "image/tiff"):
        return f"unsupported mime {info.get('mime')}"
    if not license_spdx(info.get("license_code")):
        return f"licence not allowed: {info.get('license_code')!r}"
    if not info.get("author"):
        return "no author for attribution"
    low = " ".join(info.get("categories", [])).lower() + " " + (info.get("restrictions") or "").lower()
    for pat in BLOCK_CATEGORY_PATTERNS:
        if re.search(pat, low):
            return f"blocked: {pat}"
    if (info.get("orig_w") or 0) < WIDTH:
        return "too small"
    return None


def attribution(info: dict) -> str:
    name = info["title"].removeprefix("File:")
    return f'"{name}" by {info["author"]}, {info["license_short"] or license_spdx(info["license_code"])}, via Wikimedia Commons ({info["page_url"]})'


def category_files(category: str, limit: int = 60) -> list[str]:
    d = _get({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
              "cmtype": "file", "cmlimit": str(limit)})
    return [m["title"] for m in d["query"]["categorymembers"]]


def download_and_reencode(info: dict, dest: Path) -> dict:
    """Download the 500 px thumbnail, strip metadata, write JPEG; return hashes and sizes."""
    from PIL import Image  # build-only dependency

    raw_path = CACHE_DIR / "thumbs" / f"{info['sha1']}_{WIDTH}.bin" if CACHE_DIR else None
    if raw_path and raw_path.exists():
        content = raw_path.read_bytes()
    else:
        for attempt in range(6):
            r = _session.get(info["thumb_url"], timeout=60)
            if r.status_code == 429:
                time.sleep(min(10 * 2 ** attempt, 120))
                continue
            r.raise_for_status()
            break
        content = r.content
        if raw_path:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(content)
        time.sleep(0.2)
    img = Image.open(io.BytesIO(content)).convert("RGB")
    if img.width != WIDTH:
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)  # no exif= argument -> no metadata written
    data = buf.getvalue()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"shipped_sha256": hashlib.sha256(data).hexdigest(), "shipped_w": img.width, "shipped_h": img.height,
            "dhash": dhash(img), "faces_detected": count_faces(data)}


def dhash(img, size: int = 8) -> str:
    """64-bit difference hash (perceptual), hex."""
    g = img.convert("L").resize((size + 1, size))
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (px[row * (size + 1) + col] > px[row * (size + 1) + col + 1])
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


_face_cascade = None
_face_lock = __import__("threading").Lock()


def count_faces(jpeg: bytes) -> int:
    with _face_lock:
        return _count_faces(jpeg)


def _count_faces(jpeg: bytes) -> int:
    """Pre-flag (not a decision): OpenCV Haar frontal+profile face detector on CPU."""
    global _face_cascade
    import cv2
    import numpy as np

    if _face_cascade is None:
        _face_cascade = [cv2.CascadeClassifier(cv2.data.haarcascades + n)
                         for n in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    n = 0
    for c in _face_cascade:
        n += len(c.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5, minSize=(18, 18)))
    return n


def is_post_cutoff(info: dict) -> bool:
    up = (info.get("upload_ts") or "")[:10]
    taken = (info.get("taken") or "")[:10].replace(":", "-")
    return up > CUTOFF and bool(re.match(r"\d{4}-\d{2}-\d{2}", taken)) and taken > CUTOFF


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
