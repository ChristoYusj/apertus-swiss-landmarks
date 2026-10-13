"""Tiny SPARQL client for the QLever Wikidata mirror, with an on-disk cache.

The official Wikidata Query Service was rate-limited to 1 request/minute during
the build (Oct 2026), so the frozen queries in ``queries/*.rq`` are run against
QLever (https://qlever.dev/api/wikidata), which serves the same Wikidata RDF.
Every result is cached under ``work/sparql/<sha256 of query>.json`` together with
the query text, endpoint and retrieval time, so the dataset build is replayable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import requests

ENDPOINT = "https://qlever.dev/api/wikidata"
USER_AGENT = "HackApertus-RedPandas/0.1 (student hackathon; https://github.com/ChristoYusj/apertus-swiss-landmarks)"
QUERY_DIR = Path(__file__).parent / "queries"

PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX schema: <http://schema.org/>
"""


def load_query(name: str, **fmt: str) -> str:
    text = (QUERY_DIR / f"{name}.rq").read_text(encoding="utf-8")
    for k, v in fmt.items():
        text = text.replace("{{" + k + "}}", v)
    return text


_last_call = [0.0]
MIN_INTERVAL_S = 4.0


def run(query: str, cache_dir: Path, refresh: bool = False, retries: int = 7) -> list[dict]:
    full = PREFIXES + query
    key = hashlib.sha256(full.encode("utf-8")).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))["rows"]
    last = None
    for attempt in range(retries):
        try:
            wait = MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.monotonic()
            # POST: long VALUES lists do not fit in a URL.
            r = requests.post(ENDPOINT, data={"query": full},
                              headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                              timeout=300)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else min(20 * 2 ** attempt, 240)
                last = RuntimeError(f"429 rate-limited (waiting {delay}s)")
                time.sleep(delay)
                continue
            r.raise_for_status()
            rows = r.json()["results"]["bindings"]
            path.write_text(json.dumps({
                "endpoint": ENDPOINT,
                "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "query": full, "rows": rows}, ensure_ascii=False), encoding="utf-8")
            return rows
        except Exception as e:  # network hiccups: retry with backoff
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"SPARQL query failed after {retries} attempts: {last}")


def val(row: dict, key: str) -> str | None:
    """Return a binding value; entity URIs are shortened to their QID."""
    if key not in row:
        return None
    v = row[key]["value"]
    if v.startswith("http://www.wikidata.org/entity/"):
        return v.rsplit("/", 1)[-1]
    return v
