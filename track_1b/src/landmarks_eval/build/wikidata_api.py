"""Per-item details through the Wikidata MediaWiki API (wbgetentities), cached on disk.

Used for the selected landmarks only (a few hundred items): names in all
languages (labels, aliases, Wikipedia titles) and the names of every place on
the item's administrative chain (P131), which become the accepted answers for
"where is it?". The SPARQL endpoints are only used for the bulk candidate pull.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

from .sparql import USER_AGENT

API = "https://www.wikidata.org/w/api.php"
LANGS = ["en", "fr", "de", "it", "rm", "gsw", "de-ch"]
WIKIS = {"enwiki": "en", "frwiki": "fr", "dewiki": "de", "itwiki": "it", "rmwiki": "rm", "alswiki": "gsw"}
CANTON = "Q23058"

_s = requests.Session()
_s.headers["User-Agent"] = USER_AGENT


def get_entities(ids: list[str], cache: Path, props: str = "labels|aliases|sitelinks|claims") -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for i in range(0, len(ids), 50):
        chunk = sorted(set(ids[i:i + 50]))
        key = hashlib.sha256(("|".join(chunk) + props).encode()).hexdigest()
        path = cache / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            for attempt in range(6):
                r = _s.get(API, params={"action": "wbgetentities", "ids": "|".join(chunk), "props": props,
                                        "languages": "|".join(LANGS), "format": "json", "maxlag": "5"}, timeout=60)
                if r.status_code in (429, 503) or '"maxlag"' in r.text[:300]:
                    time.sleep(min(10 * 2 ** attempt, 120))
                    continue
                r.raise_for_status()
                data = r.json()
                break
            else:
                raise RuntimeError("Wikidata API kept rate-limiting")
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.5)
        out.update(data.get("entities", {}))
    return out


def _claim_ids(ent: dict, prop: str) -> list[str]:
    ids = []
    for c in ent.get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        dv = c.get("mainsnak", {}).get("datavalue", {})
        if dv.get("type") == "wikibase-entityid":
            ids.append(dv["value"]["id"])
    return ids


def _has(ent: dict, prop: str) -> bool:
    return bool(ent.get("claims", {}).get(prop))


def details(qids: list[str], work: Path) -> tuple[dict, dict]:
    """Return ({qid: [(text, lang, kind)]}, {qid: [(text, lang, place_qid, bfs_numbers)]})."""
    cache = work / "wbapi"
    items = get_entities(qids, cache)
    names = {}
    for q in qids:
        e = items.get(q, {})
        rows = [(v["value"], l, "label") for l, v in e.get("labels", {}).items()]
        rows += [(a["value"], l, "alias") for l, al in e.get("aliases", {}).items() for a in al]
        rows += [(v["title"], WIKIS[s], "sitelink") for s, v in e.get("sitelinks", {}).items() if s in WIKIS]
        names[q] = rows

    # Walk the P131 chain (max depth 5) and keep every place that is a municipality
    # (has a BFS number P771, current or former) or the item's direct locality.
    places = {q: [] for q in qids}
    frontier = {q: [(t, True) for t in _claim_ids(items.get(q, {}), "P131")] for q in qids}
    seen_ent: dict[str, dict] = {}
    for _depth in range(5):
        need = sorted({t for lst in frontier.values() for t, _ in lst} - set(seen_ent))
        if need:
            seen_ent.update(get_entities(need, cache, props="labels|claims"))
        nxt = {}
        for q, lst in frontier.items():
            for t, direct in lst:
                ent = seen_ent.get(t, {})
                if CANTON in _claim_ids(ent, "P31"):
                    continue  # stop at the canton (canton names are scored separately)
                if direct or _has(ent, "P771"):
                    bfs = [c["mainsnak"].get("datavalue", {}).get("value")
                           for c in ent.get("claims", {}).get("P771", []) if c.get("rank") != "deprecated"]
                    places[q] += [(v["value"], l, t, tuple(b for b in bfs if b)) for l, v in ent.get("labels", {}).items()]
                nxt.setdefault(q, []).extend((p, False) for p in _claim_ids(ent, "P131"))
        frontier = nxt
        if not frontier:
            break
    return names, places
