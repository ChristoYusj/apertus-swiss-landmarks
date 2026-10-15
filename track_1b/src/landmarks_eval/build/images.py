"""Step 2: fetch, licence-filter and re-encode the photos for every selected landmark.

Per landmark:
  main  = the Wikidata main image (P18). If its licence/author is not acceptable the
          landmark is replaced by a reserve from the same cell (never a silent swap).
  alt   = up to 3 candidate photos of the same object from its Commons category
          (licence ok, perceptual-hash distance >= ALT_MIN_DIST from main, preferring
          other authors and post-cutoff uploads). The photo screening (Task P) accepts at
          most one as the 2nd view (exterior view, object clearly visible, no people).
Every shipped file gets an images.jsonl record with its licence, author, TASL
attribution, hashes and privacy-screening fields.
"""

from __future__ import annotations

import collections
import json
import random
from pathlib import Path
from urllib.parse import unquote

from ..schema import ImageRecord
from . import commons

ALT_MIN_DIST = 12
ALT_CANDIDATES = 3


def _record(lm_qid: str, role: str, image_id: str, info: dict, enc: dict, main_hash: str | None) -> dict:
    rec = {
        "image_id": image_id, "landmark_qid": lm_qid, "role": role,
        "commons_title": info["title"], "commons_page_url": info["page_url"],
        "author": info["author"], "license_short": info["license_short"] or info["license_code"],
        "license_spdx": commons.license_spdx(info["license_code"]), "license_url": info["license_url"],
        "attribution_text": commons.attribution(info), "modifications": commons.MODIFICATION,
        "commons_sha1": info["sha1"], "shipped_sha256": enc["shipped_sha256"],
        "orig_w": info["orig_w"], "orig_h": info["orig_h"], "shipped_w": enc["shipped_w"], "shipped_h": enc["shipped_h"],
        "upload_timestamp": info["upload_ts"], "taken_timestamp": info["taken"] or None,
        "post_cutoff": commons.is_post_cutoff(info), "phash": enc["dhash"],
        "phash_dist_to_main": commons.hamming(enc["dhash"], main_hash) if main_hash else None,
        "faces_detected": enc["faces_detected"], "pii_decision": "pending", "pii_reason": None,
        "pii_reviewer_ids": [], "retrieved_at": commons.now(),
    }
    ImageRecord.model_validate(rec)
    return rec


def _p18_title(lm: dict) -> str:
    return "File:" + unquote(lm["p18_file"].rsplit("/", 1)[-1]).replace("_", " ")


def build_images(work: Path, workers: int = 4) -> dict:
    import concurrent.futures as cf

    landmarks = [json.loads(l) for l in open(work / "landmarks.jsonl", encoding="utf-8")]
    reserves = [json.loads(l) for l in open(work / "reserves.jsonl", encoding="utf-8")]
    img_dir = work / "images"
    commons.CACHE_DIR = work / "commons_cache"
    stats = collections.Counter()

    # Phase A: licence/author metadata of every main photo in a few batched calls
    infos = commons.file_info(sorted({_p18_title(x) for x in landmarks + reserves}))

    def main_info(lm):
        info = infos.get(_p18_title(lm))
        if not info:
            return None, "P18 file not found on Commons"
        reason = commons.reject_reason(info)
        return (info, None) if not reason else (None, reason)

    # Phase B: sequential, deterministic replacement by reserves of the same cell
    by_cell = collections.defaultdict(list)
    for r in reserves:
        by_cell[r["stratum"]].append(r)
    final, replaced = [], []
    for lm in landmarks:
        cand = lm
        info, reason = main_info(cand)
        while info is None:
            stats[f"main_rejected: {reason.split(':')[0]}"] += 1
            entry = {"out": cand["qid"], "reason": reason}
            cand = by_cell[lm["stratum"]].pop(0) if by_cell[lm["stratum"]] else None
            entry["in"] = cand["qid"] if cand else None
            replaced.append(entry)
            if cand is None:
                break
            info, reason = main_info(cand)
        if cand is not None:
            final.append((cand, info))

    # Phase C: downloads in parallel (each landmark independent; seeded per landmark)
    def process(item):
        cand, info = item
        rng = random.Random(f"20261013-{cand['qid']}")
        image_id = f"{cand['qid']}-main"
        enc = commons.download_and_reencode(info, img_dir / f"{image_id}.jpg")
        recs = [_record(cand["qid"], "main_p18", image_id, info, enc, None)]
        local = collections.Counter()
        alts = []
        if cand.get("commons_category"):
            titles = [t for t in commons.category_files(cand["commons_category"]) if t != info["title"]]
            ainfos = commons.file_info(titles) if titles else {}
            ok = [i for t in titles if (i := ainfos.get(t)) and not commons.reject_reason(i)]
            rng.shuffle(ok)
            ok.sort(key=lambda i: (i["author"] == info["author"], not commons.is_post_cutoff(i)))
            for alt in ok[:8]:
                if len(alts) >= ALT_CANDIDATES:
                    break
                aid = f"{cand['qid']}-alt{len(alts) + 1}"
                enc_a = commons.download_and_reencode(alt, img_dir / f"{aid}.jpg")
                if commons.hamming(enc_a["dhash"], enc["dhash"]) < ALT_MIN_DIST:
                    (img_dir / f"{aid}.jpg").unlink()
                    local["alt_near_duplicate"] += 1
                    continue
                alts.append(_record(cand["qid"], "alt", aid, alt, enc_a, enc["dhash"]))
        local["landmarks_with_alt_candidates"] += bool(alts)
        local["alt_candidates"] += len(alts)
        cand = dict(cand, main_image_id=image_id)
        return cand, recs + alts, local

    records, done = [], []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (cand, recs, local) in enumerate(pool.map(process, final), 1):
            done.append(cand)
            records += recs
            stats.update(local)
            if i % 20 == 0:
                print(f"  {i}/{len(final)} landmarks", flush=True)

    with open(work / "landmarks_final.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for lm in done:
            f.write(json.dumps(lm, ensure_ascii=False) + "\n")
    with open(work / "images.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = {"landmarks": len(done), "images": len(records), "replaced": replaced, "stats": dict(stats),
              "faces_flagged": sum(r["faces_detected"] > 0 for r in records),
              "licences": collections.Counter(r["license_spdx"] for r in records),
              "post_cutoff": sum(r["post_cutoff"] for r in records)}
    (work / "images_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report
