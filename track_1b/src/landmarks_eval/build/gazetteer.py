"""Build metadata/gazetteer.json: every Swiss canton and municipality (current and former) with its names in
EN/FR/DE/IT/RM, plus neighbouring and other countries. Used by the location analysis (which place does a
wrong answer name?). Sources: Wikidata labels (CC0, via the cached QLever queries) and the BFS municipality
register 01-10-2026 (canton, language region SPRGEB2020; FSO open government data, attribution required).
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from ..grading.normalize import TYPE_WORDS, normalize, split_bilingual
from . import sparql
from .regions import CANTON_BY_BFS_ID

REGION_CODE = {"1": "DE", "2": "FR", "3": "IT", "4": "RM"}
_PREFIX = re.compile(r"^(kanton|canton|chantun|cantone)\s+(of\s+|de\s+(la\s+|l')?|d'|du\s+|des\s+|dei\s+|del\s+|di\s+|da\s+)?",
                     re.I)
# Everyday names of cantons that are not their Wikidata label ("Grigioni" next to "canton dei Grigioni").
CANTON_EXTRA = {"GR": ["Grigioni", "Grisons", "Graubünden", "Grischun"], "TI": ["Ticino", "Tessin"],
                "VS": ["Vallese", "Wallis", "Valais", "Vallais"], "BS": ["Basilea", "Basel", "Bâle"],
                "AI": ["Appenzell"], "SG": ["San Gallo", "Son Gagl", "Sankt Gallen"]}
COUNTRIES = {
    "IT": ["Italia", "Italie", "Italien", "Italy"], "FR": ["France", "Frankreich", "Francia", "Frantscha"],
    "DE": ["Deutschland", "Germany", "Allemagne", "Germania"], "AT": ["Österreich", "Austria", "Autriche"],
    "LI": ["Liechtenstein"], "SI": ["Slovenia", "Slowenien", "Slovénie", "Slovenija"],
    "ES": ["Spain", "Spanien", "Espagne", "Spagna", "España"], "GB": ["England", "Angleterre", "Inghilterra"],
    "CZ": ["Tschechien", "Czech Republic", "République tchèque", "Repubblica Ceca"],
    "BE": ["Belgium", "Belgien", "Belgique", "Belgio"], "NL": ["Niederlande", "Netherlands", "Pays-Bas", "Paesi Bassi"],
    "HR": ["Croatia", "Kroatien", "Croatie", "Croazia"], "PL": ["Poland", "Polen", "Pologne", "Polonia"],
    "HU": ["Hungary", "Ungarn", "Hongrie", "Ungheria"], "PT": ["Portugal", "Portogallo"],
}


# BFS municipality numbers are allocated in one block per canton; a former municipality's canton follows
# from its number (verified below against every current municipality). Numbers >= 7000 (lakes) have none.
BFS_BLOCKS = [(1, "ZH"), (301, "BE"), (1001, "LU"), (1201, "UR"), (1301, "SZ"), (1401, "OW"), (1501, "NW"),
              (1601, "GL"), (1701, "ZG"), (2001, "FR"), (2401, "SO"), (2701, "BS"), (2761, "BL"), (2901, "SH"),
              (3001, "AR"), (3101, "AI"), (3201, "SG"), (3501, "GR"), (4001, "AG"), (4401, "TG"), (5001, "TI"),
              (5401, "VD"), (6001, "VS"), (6401, "NE"), (6601, "GE"), (6701, "JU"), (7000, None)]


def canton_of_bfs(code: int) -> str | None:
    canton = None
    for start, c in BFS_BLOCKS:
        if code >= start:
            canton = c
    return canton


def build_gazetteer(work: Path, ds: Path) -> dict:
    cantons: dict[str, set] = defaultdict(set)
    for r in sparql.run(sparql.load_query("cantons"), work / "sparql", False):
        code = r["code"]["value"].split("-")[-1]
        cantons[code].add(normalize(_PREFIX.sub("", r["text"]["value"])))
    for code, extra in CANTON_EXTRA.items():
        cantons[code] |= {normalize(x) for x in extra}
    bfs_rows = list(csv.DictReader(open(work / "bfs_levels_01-10-2026.csv", encoding="utf-8")))
    current = {int(r["BfsCode"]): {"canton": CANTON_BY_BFS_ID[r["CantonId"].strip()],
                                   "region": REGION_CODE[r["SPRGEB2020"].strip()], "names": {r["Name"]}}
               for r in bfs_rows}
    canton_regions: dict[str, set] = defaultdict(set)
    for b, m in current.items():
        canton_regions[m["canton"]].add(m["region"])
        assert canton_of_bfs(b) == m["canton"], f"BFS block table wrong for {b} ({m['canton']})"

    def mono(c):
        return next(iter(canton_regions[c])) if c and len(canton_regions[c]) == 1 else None
    former: dict[int, set] = defaultdict(set)
    liechtenstein: set = set()
    for r in sparql.run(sparql.load_query("municipality_names"), work / "sparql", False):
        b = int(r["bfs"]["value"])
        if b in current:
            current[b]["names"].add(r["text"]["value"])
        elif 7001 <= b <= 7099:      # the BFS also numbers Liechtenstein's municipalities (Vaduz = 7001)
            liechtenstein.add(r["text"]["value"])
        elif b < 7000:               # >= 9000: lakes and other areas without a municipality
            former[b].add(r["text"]["value"])

    # a former municipality takes the canton and language region of the current municipality it became
    successors: dict[int, set] = defaultdict(set)
    for r in sparql.run(sparql.load_query("municipality_successors"), work / "sparql", False):
        b, s = int(r["bfs"]["value"]), int(r["succ"]["value"])
        if b in former and s in current:
            successors[b].add(s)

    def former_info(b: int) -> tuple[str | None, str | None]:
        cs = {current[s]["canton"] for s in successors.get(b, ())}
        rs = {current[s]["region"] for s in successors.get(b, ())}
        canton = next(iter(cs)) if len(cs) == 1 else canton_of_bfs(b)
        region = next(iter(rs)) if len(rs) == 1 else mono(canton)
        return canton, region

    def names(raw: set, short_forms: bool = False) -> list[str]:
        out = {normalize(x) for n in raw for x in split_bilingual(n)} - {""}
        if short_forms:  # "Oberhofen am Thunersee" is usually just "Oberhofen" (ties are settled by the canton)
            out |= {m.group(1) for n in list(out)
                    if (m := re.match(r"^(.+?) (am|an der|im|bei|ob|unter|sur|pres|presso|in|near) .+$", n))
                    and not m.group(1).startswith("st ") and m.group(1) not in TYPE_WORDS}  # not "st maria"
        return sorted(out)

    gz = {
        "source": ("Wikidata labels (CC0) via QLever; BFS/FSO municipality register 01-10-2026 "
                   "(canton, language region SPRGEB2020), open government data, source: Federal Statistical Office"),
        "cantons": {c: {"names": sorted(v), "region": mono(c)} for c, v in sorted(cantons.items())},
        "municipalities": [{"bfs": b, "names": names(m["names"], short_forms=True), "canton": m["canton"], "region": m["region"],
                            "current": True} for b, m in sorted(current.items())]
                          + [{"bfs": b, "names": names(v), "canton": former_info(b)[0], "region": former_info(b)[1],
                              "current": False, "successors": sorted(successors.get(b, ()))}
                             for b, v in sorted(former.items())],
        "countries": {k: sorted({normalize(x) for x in v} | ({normalize(x) for n in liechtenstein for x in split_bilingual(n)}
                                                              if k == "LI" else set()))
                      for k, v in COUNTRIES.items()},
    }
    (ds / "metadata" / "gazetteer.json").write_text(json.dumps(gz, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    return {"cantons": len(gz["cantons"]), "municipalities_current": len(current), "municipalities_former": len(former),
            "former_with_successor": len(successors),
            "former_without_region": sum(m["region"] is None for m in gz["municipalities"] if not m["current"])}
