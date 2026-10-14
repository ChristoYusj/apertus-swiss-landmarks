"""Convert the second AI reviewer's resolution (Hermes, format apertus-conservative-resolution-v1) into a
screening-check file for `landmarks-eval combine-screening` (protocol v3b-ai-review).

  python hermes_to_check.py <CLAUDE_FINAL_AI_HANDOFF.json> <a1_decisions.json> <out screening_check.json>

Per photo the reviewer's `effective_disposition` is used (retain_candidate -> ok, exclude -> reject / drop).
Why a main photo was dropped is not a structured field in the handoff, so the class of every dropped main photo is
listed in MAIN_DROP_CLASS below, read from the reviewer's reasons one by one (Claude, 15 Oct); the script stops if a
drop is missing from the table. The photos a person decided (`explicit_human_edge_decision`) are recorded per role
(`human_roles`), so A1 is credited only on those photos; a1_decisions.json holds later decisions the lead made
directly (e.g. in chat) and overrides the reviewer for that landmark.
"""
import json
import sys
from collections import Counter
from pathlib import Path

UNSURE = "main photo may not show the landmark (excluded when unsure)"
MAIN_DROP_CLASS = {   # qid -> merge class (exclude = privacy; wrong = not the landmark), with the reviewer's reason
    "Q18392442": ("exclude", None),    # foreground faces (Grimmenturm, Zurich)
    "Q1465655": ("exclude", None),     # approaching walker, face visible (Chasseral transmitter)
    "Q29884005": ("exclude", None),    # close foreground faces in a market crowd (Bellinzona)
    "Q29522262": ("exclude", None),    # café patrons, faces partly visible
    "Q27479764": ("wrong", None),      # a painting, not the museum
    "Q27484731": ("wrong", None),      # pottery display case, not the museum
    "Q27489653": ("wrong", None),      # vessels in a display case, not the museum
    "Q4883806": ("wrong", UNSURE),     # building hidden by foliage
    "Q27485116": ("wrong", UNSURE),    # gallery of vestments, museum not identifiable
    "Q27480023": ("wrong", UNSURE),    # mineral display case
    "Q29884166": ("wrong", UNSURE),    # chapel very small and obscured
    "Q29527052": ("wrong", UNSURE),    # walls may be a different fortification
}

src, a1_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
h = json.loads(src.read_text(encoding="utf-8"))
assert h.get("format") == "apertus-conservative-resolution-v1", src
a1 = json.loads(a1_path.read_text(encoding="utf-8"))

checks: dict[str, dict] = {}
stats = Counter()
for s in h["resolved_screening"]:
    c = checks.setdefault(s["qid"], {})
    if s["resolution_source"] == "explicit_human_edge_decision":
        c.setdefault("human_roles", []).append(s["role"])
    keep = s["effective_disposition"] == "retain_candidate"
    if s["role"] == "main":
        if keep:
            c["main"] = "ok"
        else:
            if s["qid"] not in MAIN_DROP_CLASS:
                raise SystemExit(f"{s['qid']}: dropped main photo without a reviewed class; add it to MAIN_DROP_CLASS")
            c["main"], reason = MAIN_DROP_CLASS[s["qid"]]
            if reason:
                c["reason"] = reason
        stats[f"main_{c['main']}"] += 1
    else:
        c[s["role"]] = "ok" if keep else "reject"
        stats[f"{s['role']}_{c[s['role']]}"] += 1
dropped = {q for q, c in checks.items() if c.get("main") != "ok"}
assert dropped == set(MAIN_DROP_CLASS), f"table and handoff disagree: {sorted(dropped ^ set(MAIN_DROP_CLASS))}"
for qid, d in a1["decisions"].items():
    assert qid in checks, qid
    roles = [k for k in ("main", "alt", "low") if k in d]
    prev = checks[qid]
    checks[qid] = {**{k: v for k, v in d.items() if k in ("main", "alt", "low", "reason")},
                   "human_roles": sorted(set(prev.get("human_roles", [])) | set(roles))}
    stats["a1_override"] += 1
for c in checks.values():
    if "human_roles" in c:
        c["human_roles"] = sorted(set(c["human_roles"]))
res = {"format": "screening-check", "annotator": "ai:hermes", "source": src.name, "source_created_at": h.get("created_at"),
       "a1_decisions": a1_path.name, "exported_at": h.get("created_at"), "checks": dict(sorted(checks.items()))}
out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
print(dict(sorted(stats.items())), "human-decided photos:",
      {q: c["human_roles"] for q, c in checks.items() if c.get("human_roles")})
