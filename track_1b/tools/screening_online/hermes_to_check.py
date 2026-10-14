"""Convert the second AI reviewer's resolution (Hermes, format apertus-conservative-resolution-v1) into a
screening-check file for `landmarks-eval combine-screening` (protocol v3b-ai-review).

  python hermes_to_check.py <CLAUDE_FINAL_AI_HANDOFF.json> <a1_decisions.json> <out screening_check.json>

Per photo the reviewer's `effective_disposition` is used (retain_candidate -> ok, exclude -> reject / drop).
A dropped main photo is classed from the reviewer's own record: excluded under the lead's "if unsure, exclude"
policy -> "may not show the landmark"; a privacy reason (faces, people) -> privacy; otherwise wrong object.
Landmarks with an explicit human edge decision are marked human; a1_decisions.json holds later decisions the lead
(A1) made directly (e.g. in chat) and overrides the reviewer for that landmark.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

src, a1_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
h = json.loads(src.read_text(encoding="utf-8"))
assert h.get("format") == "apertus-conservative-resolution-v1", src
a1 = json.loads(a1_path.read_text(encoding="utf-8"))
PRIVACY = re.compile(r"\b(faces?|pedestrians?|patrons|person|people|man)\b", re.I)

checks: dict[str, dict] = {}
stats = Counter()
for s in h["resolved_screening"]:
    c = checks.setdefault(s["qid"], {})
    if s["resolution_source"] == "explicit_human_edge_decision":
        c["human"] = True
    keep = s["effective_disposition"] == "retain_candidate"
    if s["role"] == "main":
        if keep:
            c["main"] = "ok"
        elif s["resolution_source"] == "user_authorized_conservative_ai_exclusion":
            c["main"], c["reason"] = "wrong", "main photo may not show the landmark (excluded when unsure)"
        elif PRIVACY.search(" ".join(s["reasons"] or [])):
            c["main"] = "exclude"
        else:
            c["main"] = "wrong"
        stats[f"main_{c['main']}"] += 1
    else:
        c[s["role"]] = "ok" if keep else "reject"
        stats[f"{s['role']}_{c[s['role']]}"] += 1
for qid, d in a1["decisions"].items():
    assert qid in checks, qid
    checks[qid] = {**{k: v for k, v in d.items() if k in ("main", "alt", "low", "reason")}, "human": True}
    stats["a1_override"] += 1
res = {"format": "screening-check", "annotator": "ai:hermes", "source": src.name, "source_created_at": h.get("created_at"),
       "a1_decisions": a1_path.name, "exported_at": h.get("created_at"), "checks": dict(sorted(checks.items()))}
out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(dict(sorted(stats.items())), "human-marked landmarks:", sum(1 for c in checks.values() if c.get("human")))
