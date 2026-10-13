"""Pull the candidate pool from Wikidata and apply the eligibility rules.

Eligibility (all must hold):
  E1 KGS heritage object (class A, B or cantonal/local) in Switzerland with a photo + coordinates
  E2 maps to exactly one *current* BFS municipality (or several in the same canton and region)
  E3 belongs to an allow-listed public-landmark type group (see TYPE_ROOTS)
  E4 is not an archaeological site / collection / archive
  E5 has a non-generic label (names a specific object, not just "Reformed church")
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

from ..grading.normalize import is_generic_v1 as is_generic, normalize, specific_tokens_v1 as specific_tokens, split_bilingual
from . import sparql
from .regions import load_bfs_table

HERITAGE = {"Q8274529": "A", "Q12126757": "B", "Q28971394": "local"}

# Root class -> type group. Priority order (first match wins) is GROUP_PRIORITY.
TYPE_ROOTS = {
    "Q23413": "castle", "Q751876": "castle", "Q17715832": "castle", "Q57821": "castle",
    "Q16970": "church", "Q44613": "church", "Q160742": "church", "Q2977": "church",
    "Q12280": "bridge",
    "Q483453": "fountain",
    "Q12518": "tower_gate", "Q82117": "tower_gate",
    "Q4989906": "monument", "Q179700": "monument", "Q5003624": "monument",
    "Q25550691": "civic", "Q543654": "civic", "Q55488": "civic",
    "Q33506": "museum", "Q24699794": "museum",
}
GROUP_PRIORITY = ["castle", "church", "bridge", "fountain", "tower_gate", "monument", "civic", "museum"]
HARD_EXCLUDE_TYPES = {"Q839954", "Q2668072", "Q166118", "Q27699276", "Q3950"}  # archaeological site, collection, archive, museum collection, villa

LABEL_LANG_BY_REGION = {"DE": ["de", "fr", "it", "rm", "en"], "FR": ["fr", "de", "it", "rm", "en"],
                        "IT": ["it", "de", "fr", "rm", "en"], "RM": ["rm", "de", "it", "fr", "en"]}


def _year(t: str) -> int | None:
    m = re.match(r"^\+?(-?\d{1,4})-", t)
    return int(m.group(1)) if m else None


def year_gold(statements: list[tuple[str, int, str]]) -> tuple[int | None, tuple[int, int] | None, str | None, int | None]:
    """Resolve P571 statements to (gold_year, window, raw, precision).

    Uses preferred-rank statements if any, ignores deprecated ones. Only year-or-finer
    (precision >= 9) or decade (8) precision is usable; conflicting years -> no gold.
    """
    live = [s for s in statements if not s[2].endswith("DeprecatedRank")]
    pref = [s for s in live if s[2].endswith("PreferredRank")]
    use = pref or live
    if not use:
        return None, None, None, None
    usable = [(t, p) for t, p, _ in use if p >= 8 and _year(t) is not None]
    raw, prec = use[0][0], use[0][1]
    if not usable or len(usable) != len(use):
        return None, None, raw, prec
    years = {(_year(t) // 10 * 10 if p == 8 else _year(t), p) for t, p in usable}
    if len(years) != 1:
        return None, None, raw, prec
    (y, p), = years
    window = (y - 5, y + 9 + 5) if p == 8 else (y - 5, y + 5)
    return y, window, usable[0][0], p


def pull_candidates(work: Path, refresh: bool = False) -> tuple[list[dict], dict]:
    cache = work / "sparql"
    bfs_table = load_bfs_table(work, refresh=refresh)
    roots = " ".join(f"wd:{q}" for q in TYPE_ROOTS)

    base = sparql.run(sparql.load_query("base"), cache, refresh)
    bfs_rows = sparql.run(sparql.load_query("bfs"), cache, refresh)
    type_rows = sparql.run(sparql.load_query("types", ROOTS=roots), cache, refresh)
    inc_rows = sparql.run(sparql.load_query("inception"), cache, refresh)
    extra_rows = sparql.run(sparql.load_query("extras"), cache, refresh)
    label_rows = sparql.run(sparql.load_query("labels"), cache, refresh)

    items: dict[str, dict] = {}
    for r in base:
        q = sparql.val(r, "i")
        it = items.setdefault(q, {"qid": q, "heritage": set(), "imgs": set(), "coords": set(), "sitelinks": 0})
        it["heritage"].add(HERITAGE[sparql.val(r, "h")])
        it["imgs"].add(sparql.val(r, "img"))
        it["coords"].add(sparql.val(r, "coord"))
        it["sitelinks"] = max(it["sitelinks"], int(sparql.val(r, "sl")))
    for r in bfs_rows:
        q = sparql.val(r, "i")
        if q in items and sparql.val(r, "bfs") in bfs_table:
            items[q].setdefault("bfs", set()).add(sparql.val(r, "bfs"))
    for r in type_rows:
        q = sparql.val(r, "i")
        if q not in items:
            continue
        t, root = sparql.val(r, "t"), sparql.val(r, "root")
        items[q].setdefault("p31", set()).add(t)
        for x in (t, root):
            if x in TYPE_ROOTS:
                items[q].setdefault("groups", set()).add(TYPE_ROOTS[x])
    for r in inc_rows:
        q = sparql.val(r, "i")
        if q in items:
            items[q].setdefault("inception", []).append(
                (sparql.val(r, "time"), int(sparql.val(r, "prec")), sparql.val(r, "rank") or ""))
    for r in extra_rows:
        q = sparql.val(r, "i")
        if q in items:
            if sparql.val(r, "kgs"):
                items[q].setdefault("kgs", set()).add(sparql.val(r, "kgs"))
            if sparql.val(r, "cat"):
                items[q].setdefault("cat", set()).add(sparql.val(r, "cat"))
    for r in label_rows:
        q = sparql.val(r, "i")
        if q in items:
            items[q].setdefault("labels", {})[r["text"]["xml:lang"]] = r["text"]["value"]

    funnel = collections.Counter(pulled=len(items))
    eligible = []
    for it in items.values():
        muni = sorted(it.get("bfs", ()))
        if not muni:
            funnel["drop_no_current_municipality"] += 1
            continue
        regions = {bfs_table[b]["region"] for b in muni}
        cantons = {bfs_table[b]["canton_code"] for b in muni}
        if len(regions) != 1 or len(cantons) != 1:
            funnel["drop_multi_region_or_canton"] += 1
            continue
        if it.get("p31", set()) & HARD_EXCLUDE_TYPES:
            funnel["drop_excluded_type"] += 1
            continue
        groups = it.get("groups", set())
        group = next((g for g in GROUP_PRIORITY if g in groups), None)
        if group is None:
            funnel["drop_not_public_landmark_type"] += 1
            continue
        region = regions.pop()
        labels = it.get("labels", {})
        main_label = next((labels[l] for l in LABEL_LANG_BY_REGION[region] if labels.get(l)), None)
        if is_generic(main_label):
            funnel["drop_generic_label"] += 1
            continue
        place_names = [n for b in muni for n in split_bilingual(bfs_table[b]["name"])]
        year, window, raw, prec = year_gold(it.get("inception", []))
        if group == "museum":
            # Wikidata inception of a museum is usually the institution's founding date, not the
            # building's construction: no year question for museums (audit finding, Step 1).
            year, window = None, None
        heritage = "A" if "A" in it["heritage"] else "B" if "B" in it["heritage"] else "local"
        lat_lon = sorted(it["coords"])[0]
        m = re.match(r"point\(([-\d.eE]+) ([-\d.eE]+)\)", lat_lon, re.I)
        eligible.append({
            "qid": it["qid"], "labels": labels, "main_label": main_label, "type_group": group,
            "p31": sorted(it.get("p31", ())), "heritage_class": heritage,
            "kgs_number": sorted(it["kgs"])[0] if it.get("kgs") else None,
            "commons_category": sorted(it["cat"])[0] if it.get("cat") else None,
            "p18_file": sorted(it["imgs"])[0], "n_p18": len(it["imgs"]),
            "coords": (float(m.group(2)), float(m.group(1))) if m else None,
            "municipality_bfs": muni, "municipality_names": place_names,
            "canton_code": cantons.pop(), "language_region": region, "sitelinks": it["sitelinks"],
            "gold_year": year, "year_window": window, "inception_raw": raw, "inception_precision": prec,
            "name_leaks_place": any(_leaks(l, place_names) for l in labels.values() if l),
            "stems": sorted({s for l in labels.values() if l for s in [_stem(l, place_names)] if s}),
        })
        funnel["eligible"] += 1
    return eligible, dict(funnel)


def _leaks(label: str, places: list[str]) -> bool:
    lab = f" {normalize(label)} "
    return any(f" {normalize(p)} " in lab for p in places if normalize(p))


def _stem(label: str, places: list[str]) -> str | None:
    """Label with place names removed, used to find look-alikes across towns."""
    place_toks = {t for p in places for t in normalize(p).split()}
    toks = [t for t in normalize(label).split() if t not in place_toks]
    if not specific_tokens(" ".join(toks)):
        return None
    return " ".join(toks)
