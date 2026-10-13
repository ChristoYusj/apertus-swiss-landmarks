"""Hypothesis tests H1b-H4 (docs/analysis_plan.md) and the location analysis: which place does an answer name?

Location extraction is deterministic: the answer is matched against metadata/gazetteer.json (all Swiss cantons
and current/former municipalities in EN/FR/DE/IT/RM, plus foreign countries). The longest name wins at each
position. Municipality names that are also everyday words are never matched (STOP, fixed before looking at
the tables); a saint-named municipality ("St. Martin", "Sent") does not count right after a church word
("baselgia da Sent Martin" is a church, not the town).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .grading.normalize import TYPE_WORDS, normalize
from .grading.normalize import _FUNCTION_WORDS
from .metrics import bootstrap_p, bootstrap_values, holm, mcnemar, percentile_ci, wilson

STOP = ({"alle", "au", "burg", "chapelle", "dorf", "fontaines", "monte", "munster", "mur", "pont", "speicher", "sur",
         "torre", "berg", "buch", "egg", "eich", "horn", "mund", "port", "rain", "root", "rue", "sent", "val", "wald",
         "zell", "thal", "grub", "steg", "mon", "mut", "sour", "gy", "lu", "font", "arch", "riviera", "stein", "pura",
         "loco", "casti", "roten"} | {w for w in TYPE_WORDS if len(w) <= 3})
CHURCH = {"kirche", "chiesa", "eglise", "baselgia", "baselgetta", "chapelle", "kapelle", "cappella", "church", "chapel",
          "oratorio", "oratorium", "pfarrkirche", "parrocchiale", "klosterkirche", "cattedrale", "kathedrale",
          "cathedrale", "collegiata", "basilica", "convento", "kloster", "abbaye", "couvent", "monastero", "caplutta",
          "chaplutta", "temple", "santuario", "sanctuaire", "chiesetta", "clutger", "claustra", "abbazia", "munster",
          "pregia", "collegiale", "abbey", "stift", "dom", "duomo", "pieve", "prepositurale", "kollegiatkirche"}


def _is_church(t: str) -> bool:
    """Church words, including compounds such as Stiftskirche, Wallfahrtskapelle, Benediktinerkloster."""
    return t in CHURCH or t.endswith(("kirche", "kapelle", "kloster", "chille", "chiesa", "chapelle"))
# Place names that are also everyday words ("mit Zug" = by train, "baden" = to bathe) count only right after a
# place cue ("in Zug", "Kanton Zug", "à Baden").
CONTEXT_ONLY = {"zug", "baden"}
PLACE_CUES = {"in", "im", "bei", "nach", "a", "au", "di", "da", "nel", "nella", "en", "kanton", "canton", "cantone",
              "chantun", "gemeinde", "commune", "comune", "vischnanca", "stadt", "ville", "citta", "citad", "de", "von"}
LANG_REGION = {"fr": "FR", "de": "DE", "it": "IT", "rm": "RM"}
SWITZERLAND = {"schweiz", "suisse", "svizzera", "svizra", "switzerland", "svizzer"}


class Gazetteer:
    def __init__(self, gz: dict):
        self.by_first: dict[str, list] = defaultdict(list)
        entries: dict[str, list] = defaultdict(list)
        for code, c in gz["cantons"].items():
            for n in c["names"]:
                entries[n].append(("canton", {"canton": code, "region": c["region"]}))
        for m in gz["municipalities"]:
            for n in m["names"]:
                if n not in STOP and n not in _FUNCTION_WORDS:
                    entries[n].append(("municipality", {"bfs": m["bfs"], "canton": m["canton"], "region": m["region"],
                                                        "current": m["current"]}))
        for code, ns in gz["countries"].items():
            for n in ns:
                entries[n].append(("country", {"country": code}))
        for n, payloads in entries.items():
            toks = n.split()
            if toks:
                self.by_first[toks[0]].append((toks, n, payloads))
        for v in self.by_first.values():
            v.sort(key=lambda e: -len(e[0]))  # longest first
        self.n_municipalities_current = sum(m["current"] for m in gz["municipalities"])
        self.share_de_municipalities = sum(m["region"] == "DE" for m in gz["municipalities"] if m["current"]) / \
            max(1, self.n_municipalities_current)

    @staticmethod
    def _tokens(text: str) -> list[tuple[str, str, int]]:
        """(normalized token, original word, end offset of the original word) for every word of the text."""
        out = []
        for m in re.finditer(r"[^\W_]+", text or ""):
            for piece in normalize(m.group()).split():
                out.append((piece, m.group(), m.end()))
        return out

    def mentions(self, text: str) -> list[dict]:
        """Place names in reading order. A match must be capitalised in the answer (place names are, in all five
        languages: "einem roten Gebäude" is not the village Roten) and must not continue with a hyphen
        ("Saint-Jean-Baptiste" is not Saint-Jean)."""
        text = text or ""
        tt = self._tokens(text)
        toks = [t for t, _, _ in tt]
        out, i = [], 0
        while i < len(toks):
            hit = None
            for cand, name, payloads in self.by_first.get(toks[i], []):
                if toks[i:i + len(cand)] == cand:
                    end = tt[i + len(cand) - 1][2]
                    if not tt[i][1][:1].isupper() or re.match(r"-\w", text[end:end + 2]):
                        continue
                    hit = (cand, name, payloads)
                    break
            if not hit:
                i += 1
                continue
            cand, name, payloads = hit
            if name.startswith("st ") and any(_is_church(t) for t in toks[max(0, i - 3):i]):
                payloads = [p for p in payloads if p[0] != "municipality"]
            if name in CONTEXT_ONLY and not any(t in PLACE_CUES for t in toks[max(0, i - 2):i]):
                payloads = []
            if payloads:
                out.append({"pos": i, "name": name, "payloads": payloads})
            i += len(cand)
        return out

    def locate(self, text: str) -> dict:
        """First specific Swiss place named (municipality or canton); else a foreign country; else none.
        A town name shared by several cantons ("Buchs") takes the canton named later in the answer, if any."""
        ms = self.mentions(text)
        named_cantons = [p["canton"] for m in ms for k, p in m["payloads"] if k == "canton"]
        for m in ms:
            munis = [p for k, p in m["payloads"] if k == "municipality"]
            cantons = [p for k, p in m["payloads"] if k == "canton"]
            if not munis and not cantons:
                continue
            cur = [p for p in munis if p["current"]]
            pool = cur or cantons or munis
            if len({p["canton"] for p in pool}) > 1:
                narrowed = [p for p in pool if p["canton"] in named_cantons]
                pool = narrowed or pool
            cset = {p["canton"] for p in pool if p["canton"]}
            rset = {p["region"] for p in pool if p["region"]}
            bfs = {p["bfs"] for p in pool if p.get("bfs")}
            return {"kind": "swiss", "name": m["name"], "level": "municipality" if munis else "canton",
                    "canton": next(iter(cset)) if len(cset) == 1 else None,
                    "region": next(iter(rset)) if len(rset) == 1 else None,
                    "bfs": next(iter(bfs)) if len(bfs) == 1 else None}
        for m in ms:
            for k, p in m["payloads"]:
                if k == "country":
                    return {"kind": "abroad", "name": m["name"], "country": p["country"]}
        t = f" {normalize(text or '')} "
        if any(f" {w} " in t for w in SWITZERLAND):
            return {"kind": "switzerland_only"}
        return {"kind": "none"}


def _pct(k, n):
    return k / n if n else None


def location_analysis(rows: list[dict], gz: Gazetteer, lms: dict) -> dict:
    """rows: photo_main place answers with keys landmark_qid, lang, label, text."""
    out = {}
    gold_regions = Counter(l["language_region"] for l in lms.values())
    for lang in ("fr", "de", "it", "rm"):
        rs = [r for r in rows if r["lang"] == lang]
        locs = [(r, gz.locate(r["text"])) for r in rs]
        kinds = Counter(l["kind"] for _, l in locs)
        swiss = [(r, l) for r, l in locs if l["kind"] == "swiss"]
        resolved = [(r, l) for r, l in swiss if l["region"]]
        non_gr = [(r, l) for r, l in locs if lms[r["landmark_qid"]]["canton_code"] != "GR"]
        wrong = [(r, l) for r, l in resolved if r["label"] == "incorrect"]
        out[lang] = {
            "n": len(rs), "kinds": dict(sorted(kinds.items())),
            "pct_naming_a_swiss_place": _pct(len(swiss), len(rs)),
            "pct_abroad": _pct(kinds["abroad"], len(rs)),
            "pct_placed_in_GR": _pct(sum(l.get("canton") == "GR" for _, l in locs), len(rs)),
            "pct_nonGR_landmarks_placed_in_GR": _pct(sum(l.get("canton") == "GR" for _, l in non_gr), len(non_gr)),
            "predicted_region_dist": dict(sorted(Counter(l["region"] for _, l in resolved).items())),
            "pct_home_region_among_resolved": _pct(sum(l["region"] == LANG_REGION[lang] for _, l in resolved), len(resolved)),
            "pct_home_region_among_wrong_resolved": _pct(sum(l["region"] == LANG_REGION[lang] for _, l in wrong), len(wrong)),
            "abroad_countries": dict(sorted(Counter(l["country"] for _, l in locs if l["kind"] == "abroad").items())),
        }
    out["gold_region_dist"] = dict(sorted(gold_regions.items()))
    out["gold_pct_GR"] = _pct(sum(l["canton_code"] == "GR" for l in lms.values()), len(lms))
    # exploratory paired comparison (same photo, only the question language differs): non-GR landmarks put in GR
    by = defaultdict(dict)
    for r in rows:
        if lms[r["landmark_qid"]]["canton_code"] != "GR":
            by[r["landmark_qid"]][r["lang"]] = gz.locate(r["text"]).get("canton") == "GR"
    pairs = {}
    for other in ("fr", "de", "it"):
        both = [v for v in by.values() if "rm" in v and other in v]
        b = sum(v["rm"] and not v[other] for v in both)
        c = sum(v[other] and not v["rm"] for v in both)
        pairs[f"rm_vs_{other}"] = {"landmarks": len(both), "only_rm_says_GR": b, f"only_{other}_says_GR": c,
                                   "mcnemar_p": mcnemar(b, c)}
    out["exploratory_paired_GR_pull"] = pairs
    return out


def hypotheses(rows: list[dict], gz: Gazetteer, lms: dict, cases: dict, bootstrap: int = 2000) -> dict:
    """rows: every graded answer with keys item_id, landmark_qid, arm, qtype, lang, tier, region, label, text."""
    main = [r for r in rows if r["arm"] == "photo_main"]
    res, pvals = {}, {}

    def hall(rs):
        att = [r for r in rs if r["label"] in ("correct", "incorrect")]
        return sum(r["label"] == "incorrect" for r in att) / len(att) if att else None

    def tier_diff(rs):
        a, b = hall([r for r in rs if r["tier"] == "low"]), hall([r for r in rs if r["tier"] == "high"])
        return None if a is None or b is None else a - b

    for key, qtype in (("H1", "name"), ("H1b", "place")):
        rs = [r for r in main if r["qtype"] == qtype]
        vals = bootstrap_values(rs, tier_diff, b=bootstrap) if bootstrap else None
        res[key] = {"estimate": tier_diff(rs), "ci95_cluster_bootstrap": percentile_ci(vals), "p_two_sided": bootstrap_p(vals),
                    "hallucination_low": hall([r for r in rs if r["tier"] == "low"]),
                    "hallucination_high": hall([r for r in rs if r["tier"] == "high"]),
                    "attempted_low": sum(r["tier"] == "low" and r["label"] != "not_attempted" for r in rs),
                    "attempted_high": sum(r["tier"] == "high" and r["label"] != "not_attempted" for r in rs)}
        pvals[key] = res[key]["p_two_sided"]

    # H2: wrong place answers that name a (current) Swiss municipality
    wrong = []
    for r in main:
        if r["qtype"] == "place" and r["label"] == "incorrect":
            loc = gz.locate(r["text"])
            if loc["kind"] == "swiss" and loc["level"] == "municipality" and loc["region"]:
                wrong.append({**r, "pred_de": loc["region"] == "DE"})

    def share_de(rs):
        return sum(r["pred_de"] for r in rs) / len(rs) if rs else None

    def h2(rs):
        a = share_de([r for r in rs if r["region"] != "DE"])
        b = share_de([r for r in rs if r["region"] == "DE"])
        return None if a is None or b is None else a - b

    def h2c(rs):
        a = share_de([r for r in rs if r["region"] != "DE"])
        return None if a is None else a - gz.share_de_municipalities

    v2 = bootstrap_values(wrong, h2, b=bootstrap) if bootstrap else None
    v2c = bootstrap_values([r for r in wrong if r["region"] != "DE"], h2c, b=bootstrap) if bootstrap else None
    non_de = [r for r in wrong if r["region"] != "DE"]
    res["H2"] = {
        "n_wrong_naming_a_municipality": len(wrong), "n_non_DE_landmarks": len(non_de),
        "share_DE_named_for_non_DE_landmarks": share_de(non_de),
        "as_registered": {"base": "share of DE municipalities named in wrong answers for DE landmarks",
                          "base_value": share_de([r for r in wrong if r["region"] == "DE"]), "estimate": h2(wrong),
                          "ci95_cluster_bootstrap": percentile_ci(v2), "p_two_sided": bootstrap_p(v2)},
        "clarified": {"base": "share of German-speaking municipalities among all current Swiss municipalities (BFS)",
                      "base_value": gz.share_de_municipalities, "estimate": h2c(non_de),
                      "ci95_cluster_bootstrap": percentile_ci(v2c), "p_two_sided": bootstrap_p(v2c)},
        "note": "the registered base rate is not informative (wrong answers for DE landmarks stay mostly in DE); "
                "the clarified comparison is reported next to it; the registered test enters the Holm family",
    }
    pvals["H2"] = res["H2"]["as_registered"]["p_two_sided"]

    # H2b: wrong answers naming a look-alike sibling's town
    sib_hits = []
    for r in main:
        sibs = lms[r["landmark_qid"]].get("lookalike_siblings") or []
        if r["label"] != "incorrect" or not sibs:
            continue
        t = f" {normalize(r['text'])} "
        named = [s for s in sibs if any(f" {normalize(x)} " in t for x in _town_forms(s["municipality"]))]
        if named:
            sib_hits.append({"item_id": r["item_id"], "landmark_qid": r["landmark_qid"], "named": [s["qid"] for s in named]})
    res["H2b"] = {"wrong_answers_on_landmarks_with_lookalikes": sum(r["label"] == "incorrect" and bool(lms[r["landmark_qid"]].get("lookalike_siblings"))
                                                                    for r in main),
                  "naming_a_lookalike_town": len(sib_hits), "landmarks": len({h["landmark_qid"] for h in sib_hits}),
                  "examples": sib_hits[:5],
                  "testable": len({h["landmark_qid"] for h in sib_hits}) >= 10,
                  "note": "not testable when fewer than 10 landmarks contribute (floor effect); reported descriptively"}
    if res["H2b"]["testable"]:
        pvals["H2b"] = None  # sibling fame is not in the shipped data; would need it to run the binomial test

    # H3: text_only vs photo_main place accuracy, paired by landmark, per language
    for lang in ("fr", "de"):
        t = {r["landmark_qid"]: r["label"] == "correct" for r in rows
             if r["arm"] == "text_only" and r["qtype"] == "place" and r["lang"] == lang}
        p = {r["landmark_qid"]: r["label"] == "correct" for r in main if r["qtype"] == "place" and r["lang"] == lang}
        both = sorted(set(t) & set(p))
        b = sum(t[q] and not p[q] for q in both)
        c = sum(p[q] and not t[q] for q in both)
        key = f"H3_{lang}"
        res[key] = {"landmarks": len(both), "text_correct": sum(t[q] for q in both), "photo_correct": sum(p[q] for q in both),
                    "only_text_correct": b, "only_photo_correct": c, "mcnemar_p": mcnemar(b, c)}
        pvals[key] = res[key]["mcnemar_p"]

    # H4: premise adopted (incorrect) vs paired control (same photo, plain name question) incorrect
    lab = {r["item_id"]: r["label"] for r in rows}
    pairs = [(r["label"] == "incorrect", lab.get(cases[r["item_id"]].get("paired_control_item_id")) == "incorrect")
             for r in rows if r["arm"] == "trap_premise" and cases[r["item_id"]].get("paired_control_item_id") in lab]
    b = sum(x and not y for x, y in pairs)
    c = sum(y and not x for x, y in pairs)
    res["H4"] = {"pairs": len(pairs), "premise_incorrect": sum(x for x, _ in pairs), "control_incorrect": sum(y for _, y in pairs),
                 "premise_incorrect_rate": _pct(sum(x for x, _ in pairs), len(pairs)),
                 "premise_incorrect_ci95_wilson": wilson(sum(x for x, _ in pairs), len(pairs)),
                 "control_incorrect_rate": _pct(sum(y for _, y in pairs), len(pairs)),
                 "only_premise_incorrect": b, "only_control_incorrect": c, "mcnemar_p": mcnemar(b, c)}
    pvals["H4"] = res["H4"]["mcnemar_p"]
    res["holm"] = holm(pvals)

    # descriptive: wrong NAME answers that name ANOTHER landmark of this dataset (pull toward the famous?)
    strong = {q: [a["text"] for a in l["name_aliases"] if a.get("distinctive", True)] for q, l in lms.items()}
    named = Counter()
    n_wrong = 0
    for r in main:
        if r["qtype"] != "name" or r["label"] != "incorrect":
            continue
        n_wrong += 1
        t = f" {normalize(r['text'])} "
        others = [q for q, al in strong.items() if q != r["landmark_qid"] and any(f" {normalize(a)} " in t for a in al if normalize(a))]
        for q in others[:1]:
            named[q] += 1
    tiers = Counter(lms[q]["fame_tier"] for q in named.elements())
    res["named_other_landmark"] = {
        "wrong_name_answers": n_wrong, "naming_another_dataset_landmark": sum(named.values()),
        "tier_of_named": dict(sorted(tiers.items())),
        "dataset_tier_share": dict(sorted(Counter(l["fame_tier"] for l in lms.values()).items())),
        "top": [{"qid": q, "name": lms[q]["labels"].get("en") or lms[q]["labels"].get("de") or q, "times": k}
                for q, k in named.most_common(10)],
    }
    return res


def _town_forms(name: str) -> list[str]:
    from .grading.normalize import split_bilingual
    return split_bilingual(name)


def load_gazetteer(dataset: Path) -> Gazetteer | None:
    p = dataset / "metadata" / "gazetteer.json"
    return Gazetteer(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else None
