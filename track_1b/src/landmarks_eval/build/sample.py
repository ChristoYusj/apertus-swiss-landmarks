"""Stratified, seeded selection of landmarks and construction of their answer keys.

Strata: language region (BFS SPRGEB2020) x fame tier, where fame = number of
Wikipedia articles about the object in any language edition (Wikidata sitelinks to
*.wikipedia.org; Commons/Wikivoyage pages are NOT counted):
  low  = 0 articles (the object has no Wikipedia article at all)
  mid  = 1-2 articles
  high = 3 or more articles
The same definition is used in every region. TARGET landmarks are drawn at random
(seeded) per cell with a soft cap of 50 % per type group, plus up to R reserves per
cell used to replace photos excluded during the privacy (PII) screening. When a cell
has fewer candidates than TARGET (Romansh / high), the whole cell is taken (census).
"""

from __future__ import annotations

import collections
import json
import math
import random
import re
from pathlib import Path

from ..grading.normalize import distinctive, is_generic, normalize, split_bilingual
from ..schema import Landmark
from . import sparql
from .candidates import pull_candidates
from .regions import load_bfs_table

SEED = 20261013
TARGET = {"DE": 24, "FR": 24, "IT": 24, "RM": 18}
RESERVES = 8
TYPE_CAP = 0.5


def tier_of(wp: int) -> str:
    return "low" if wp == 0 else "mid" if wp <= 2 else "high"


def tier_pools(cands: list[dict], rng: random.Random) -> dict[str, list[dict]]:
    order = list(cands)
    rng.shuffle(order)  # seeded tie-break
    order.sort(key=lambda c: -c["wikipedia_articles"])
    n = len(order)
    for pos, c in enumerate(order):
        c["fame_rank_in_region"] = pos / (n - 1) if n > 1 else 0.0
    pools = {"high": [], "mid": [], "low": []}
    for c in order:
        pools[tier_of(c["wikipedia_articles"])].append(c)
    return pools


def draw(pool: list[dict], n: int, rng: random.Random) -> tuple[list[dict], list[dict]]:
    order = list(pool)
    rng.shuffle(order)
    chosen, counts = [], collections.Counter()
    cap = math.ceil(TYPE_CAP * n)
    if len(order) <= n:  # census: take the whole cell
        return order, []
    for c in order:  # pass 1: respect the soft type cap
        if len(chosen) < n and counts[c["type_group"]] < cap:
            chosen.append(c)
            counts[c["type_group"]] += 1
    for c in order:  # pass 2: fill if the cap made the cell impossible
        if len(chosen) < n and c not in chosen:
            chosen.append(c)
    rest = [c for c in order if c not in chosen]
    return chosen, rest[:RESERVES]


def lookalikes(eligible: list[dict]) -> dict[str, list[dict]]:
    by_stem = collections.defaultdict(list)
    for c in eligible:
        for s in c["stems"]:
            by_stem[(c["type_group"], s)].append(c)
    out = collections.defaultdict(list)
    for (_, stem), members in by_stem.items():
        towns = {tuple(m["municipality_bfs"]) for m in members}
        if 2 <= len(members) <= 15 and len(towns) >= 2:
            for m in members:
                out[m["qid"]].append({"stem": stem, "siblings": [x for x in members if x["municipality_bfs"] != m["municipality_bfs"]]})
    return out


def fetch_details(qids: list[str], work: Path, refresh: bool) -> tuple[dict, dict]:
    from .wikidata_api import details
    return details(qids, work)


def _aliases(pairs) -> list[dict]:
    seen, out = set(), []
    for text, lang, source in pairs:
        key = normalize(text)
        if key and key not in seen:
            seen.add(key)
            out.append({"text": text, "lang": lang, "source": source})
    return out


def build_landmarks(work: Path, refresh: bool = False) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    eligible, funnel = pull_candidates(work, refresh)
    bfs_table = load_bfs_table(work)
    cantons = collections.defaultdict(list)
    canton_qid = {}
    for r in sparql.run(sparql.load_query("cantons"), work / "sparql", refresh):
        code = sparql.val(r, "code").replace("CH-", "")
        canton_qid[code] = sparql.val(r, "c")
        cantons[code].append((r["text"]["value"], r["text"]["xml:lang"], "wikidata:label"))
    wp = {sparql.val(r, "i"): int(sparql.val(r, "wp"))
          for r in sparql.run(sparql.load_query("wikipedia_counts"), work / "sparql", refresh)}
    for c in eligible:
        c["wikipedia_articles"] = wp.get(c["qid"], 0)
    looks = lookalikes(eligible)
    # Every official municipality name (incl. bilingual parts and suffix-free forms such as
    # "Schmitten" for "Schmitten (GR)") -> the BFS numbers that carry it.
    name_munis: dict[str, set] = collections.defaultdict(set)
    for bfs_no, b in bfs_table.items():
        for n in split_bilingual(b["name"]):
            name_munis[normalize(n)].add(bfs_no)
    canton_cores = set()
    for code, labs in cantons.items():
        for t, _, _ in labs:
            core = re.sub(r"^(canton (of|de|du)|kanton|cantone( (di|del|dei))?|chantun)\s+", "", normalize(t))
            canton_cores.add(core)
    dropped = collections.Counter()

    selected, reserves, cells = [], [], {}
    for region in ["DE", "FR", "IT", "RM"]:
        cands = [c for c in eligible if c["language_region"] == region]
        pools = tier_pools(cands, rng)
        for tier in ["high", "mid", "low"]:
            chosen, extra = draw(pools[tier], TARGET[region], rng)
            for c in chosen + extra:
                c["fame_tier"], c["stratum"] = tier, f"{region}|{tier}"
            selected += chosen
            reserves += extra
            cells[f"{region}|{tier}"] = {"pool": len(pools[tier]), "selected": len(chosen), "reserves": len(extra),
                                         "wikipedia_articles_range": [min(c["wikipedia_articles"] for c in pools[tier]),
                                                                      max(c["wikipedia_articles"] for c in pools[tier])]}

    names, places = fetch_details([c["qid"] for c in selected + reserves], work, refresh)

    def to_landmark(c: dict) -> dict | None:
        own_ids = set(c["municipality_bfs"])
        own_names = {normalize(n) for n in c["municipality_names"]}
        other_names = {n for n, ids in name_munis.items() if ids - own_ids}
        # ---- accepted answers for "where": official BFS names + Wikidata labels of the chain
        place_pairs = [(n, "", "bfs:name") for n in c["municipality_names"]]
        for t, l, _pq, bfs_nums in places.get(c["qid"], []):
            if l not in ("en", "fr", "de", "it", "rm"):
                continue
            own_entity = bool(set(bfs_nums) & own_ids)
            for x in split_bilingual(t):
                nx = normalize(x)
                bad = (nx in other_names or (not own_entity and nx in canton_cores)) and nx not in own_names
                if bad:
                    dropped[f"place|{c['qid']}|{x}"] += 1
                else:
                    place_pairs.append((x, l, "wikidata:place_label"))
        place_aliases = _aliases(place_pairs)
        town_norms = {normalize(a["text"]) for a in place_aliases}
        town_tokens = {t for n in town_norms for t in n.split()}
        ambiguous = sorted(a["text"] for a in place_aliases if normalize(a["text"]) in other_names)
        # ---- accepted answers for "what": drop aliases that are only a town or only type words
        name_pairs = []
        for t, l, k in names.get(c["qid"], []):
            nt = normalize(t)
            if nt in town_norms or nt in name_munis:
                dropped[f"name_is_town|{c['qid']}|{t}"] += 1
            elif is_generic(t):
                dropped[f"name_generic|{c['qid']}|{t}"] += 1
            else:
                name_pairs.append((t, l, f"wikidata:{k}"))
        name_aliases = _aliases(name_pairs)
        if not name_aliases:
            return None  # no usable name: replaced by a reserve
        for a in name_aliases:
            a["distinctive"] = distinctive(a["text"], town_tokens)
        needs_place = not any(a["distinctive"] for a in name_aliases)
        labels = [v for v in c["labels"].values() if v]
        leaks = any(f" {n} " in f" {normalize(lab)} " for lab in labels for n in town_norms if n)
        look = looks.get(c["qid"], [])
        lm = {
            "qid": c["qid"],
            "labels": {l: c["labels"].get(l) for l in ("en", "fr", "de", "it", "rm")},
            "name_aliases": name_aliases,
            "p31": c["p31"], "type_group": c["type_group"], "heritage_class": c["heritage_class"],
            "kgs_number": c["kgs_number"], "canton_qid": canton_qid[c["canton_code"]],
            "canton_code": c["canton_code"],
            "canton_aliases": _aliases(cantons[c["canton_code"]] + [(c["canton_code"], "", "iso3166-2")]),
            "municipality_bfs": c["municipality_bfs"][0],
            "municipality_name": bfs_table[c["municipality_bfs"][0]]["name"],
            "place_aliases": place_aliases,
            "language_region": c["language_region"], "sitelinks": c["sitelinks"],
            "wikipedia_articles": c["wikipedia_articles"],
            "fame_tier": c["fame_tier"], "fame_rank_in_region": round(c["fame_rank_in_region"], 4),
            "coords": c["coords"], "commons_category": c["commons_category"], "p18_file": c["p18_file"],
            "inception_raw": c["inception_raw"], "inception_precision": c["inception_precision"],
            "gold_year": c["gold_year"], "year_window": c["year_window"],
            "name_leaks_place": leaks, "name_needs_place": needs_place,
            "ambiguous_place_aliases": ambiguous,
            "lookalike_set_id": look[0]["stem"] if look else None,
            "stratum": c["stratum"], "selection_seed": SEED,
        }
        Landmark.model_validate(lm)
        lm["_siblings"] = sorted({(sb["qid"], sb["municipality_names"][0]) for x in look for sb in x["siblings"]})
        return lm

    # invalid selections (no usable name) are replaced by the next reserve of the same cell
    res_by_cell = collections.defaultdict(list)
    for c in reserves:
        res_by_cell[c["stratum"]].append(c)
    out_sel, replaced = [], []
    for c in selected:
        lm = to_landmark(c)
        while lm is None and res_by_cell[c["stratum"]]:
            r = res_by_cell[c["stratum"]].pop(0)
            replaced.append({"out": c["qid"], "in": r["qid"], "reason": "no usable name alias"})
            c, lm = r, to_landmark(r)
        if lm is None:
            replaced.append({"out": c["qid"], "in": None, "reason": "no usable name alias, no reserve left"})
            continue
        out_sel.append(lm)
    out_res = [x for cell in res_by_cell.values() for c in cell if (x := to_landmark(c)) is not None]
    for name, rows in (("landmarks.jsonl", out_sel), ("reserves.jsonl", out_res)):
        with open(work / name, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    funnel.update({"selected": len(out_sel), "reserves": len(out_res)})
    report = {"seed": SEED, "funnel": funnel, "cells": cells,
              "replaced": replaced,
              "dropped_aliases": collections.Counter(k.split("|")[0] for k in dropped),
              "dropped_alias_examples": sorted(dropped)[:400],
              "name_needs_place": sum(x["name_needs_place"] for x in out_sel),
              "with_ambiguous_place": sum(bool(x["ambiguous_place_aliases"]) for x in out_sel),
              "type_groups": collections.Counter(x["type_group"] for x in out_sel),
              "with_year": sum(x["gold_year"] is not None for x in out_sel),
              "name_leaks_place": sum(x["name_leaks_place"] for x in out_sel),
              "with_lookalikes": sum(x["lookalike_set_id"] is not None for x in out_sel)}
    (work / "selection_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report
