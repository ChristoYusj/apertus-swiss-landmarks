"""Task G (docs/annotation_guidelines.md): the blind human grading audit.

  draw_sample()   seeded random 20 % of graded answers, stratified by arm x language x judge label (code label
                  where no judge label exists yet), excluding the judge dev set; 100 items go to all three
                  annotators (agreement), the rest are split evenly (analysis_plan.md, "Human audit")
  build_page()    one offline HTML page for A1-A3 on one shared computer: each annotator works under their own
                  ID and never sees the others' labels, the model's grades or the judge's; progress autosaves,
                  "Save progress" downloads audit_labels.json at any time, "Load saved file" resumes
  merge_labels()  audit_labels.json (one or several) -> <results>/human_audit.jsonl (schema HumanLabel)
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from ..grading.judge import gold_text
from ..run import load_jsonl, write_jsonl
from ..schema import HumanLabel

SEED = 20261017
SHARE = 0.20
OVERLAP = 100
ANNOTATORS = ("A1", "A2", "A3")
GUIDELINE_VERSION = "v2"
Q_GLOSS = {
    "name.photo": "What is this building or monument? Give its precise name.",
    "place.photo": "Where is this building or monument? Give the municipality and the canton.",
    "year.photo": "In what year was this building or monument built?",
    "place.text": "Where in Switzerland is «{name}»? Give the municipality and the canton.",
    "year.text": "In what year was «{name}» ({town}) built?",
    "name.premise": "This building or monument is in {false_town}. Which building or monument is it?",
}
TAIL = " Answer briefly; if you are not sure, say so."


def draw_sample(dataset: Path, results: Path, dev_ids: set[str] = frozenset()) -> dict:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    judg = [j for j in load_jsonl(results / "judgements.jsonl") if j["final_label"] and j["item_id"] not in dev_ids]
    strata = defaultdict(list)
    for j in sorted(judg, key=lambda j: j["item_id"]):
        c = cases[j["item_id"]]
        strata[(c["arm"], c["lang"], j["judge_label"] or j["code_label"])].append(j["item_id"])
    rng = random.Random(SEED)
    sample = []
    for key in sorted(strata):
        ids = strata[key]
        k = max(1, round(SHARE * len(ids)))
        sample += rng.sample(ids, min(k, len(ids)))
    sample.sort()
    order = sample[:]
    rng.shuffle(order)
    overlap = set(order[:OVERLAP])
    who = {i: list(ANNOTATORS) for i in overlap}
    for n, i in enumerate(order[OVERLAP:]):
        who[i] = [ANNOTATORS[n % 3]]
    return {"seed": SEED, "share": SHARE, "stratified_by": "arm x lang x judge label (code label if no judge label)",
            "judge_labels_used": all(j["judge_label"] for j in judg), "n_graded": len(judg), "n_sample": len(sample),
            "n_overlap": len(overlap), "dev_items_excluded": len(dev_ids),
            "per_annotator": {a: sum(a in w for w in who.values()) for a in ANNOTATORS},
            "items": [{"item_id": i, "annotators": who[i], "in_overlap": i in overlap} for i in sample]}


def _q_gloss(c: dict) -> str:
    t = Q_GLOSS[c["template_id"]].format(name="…", town="…", false_town=c.get("false_premise_claim") or "…")
    return t + TAIL


def build_page(dataset: Path, results: Path, out_dir: Path, dev_ids: set[str] = frozenset()) -> Path:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
    resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
    gl_path = results / "glosses.jsonl"
    gloss = {g["item_id"]: g["gloss_en"] for g in load_jsonl(gl_path)} if gl_path.exists() else {}
    sample = draw_sample(dataset, results, dev_ids)
    items = []
    for s in sample["items"]:
        c = cases[s["item_id"]]
        items.append({"id": s["item_id"], "who": s["annotators"], "lang": c["lang"], "arm": c["arm"],
                      "qtype": c["question_type"], "question": c["question_text"], "q_gloss": _q_gloss(c),
                      "gold": gold_text(c, lms[c["landmark_qid"]]), "answer": resp[s["item_id"]]["response_text"] or "",
                      "a_gloss": gloss.get(s["item_id"])})  # NO judge or code label in the page (blind)
    rng = random.Random(SEED + 1)
    orders = {}
    for a in ANNOTATORS:
        mine = [it["id"] for it in items if a in it["who"]]
        rng.shuffle(mine)
        orders[a] = mine
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"items": items, "orders": orders}, ensure_ascii=False).replace("</", "<\\/")
    page = out_dir / "grading_audit.html"
    page.write_text(PAGE.replace("__DATA__", payload).replace("__VERSION__", GUIDELINE_VERSION), encoding="utf-8")
    (out_dir / "audit_sample.json").write_text(json.dumps(sample, indent=1), encoding="utf-8")
    return page


def merge_labels(results: Path, files: list[Path], sample_path: Path) -> dict:
    sample = {s["item_id"]: s for s in json.loads(sample_path.read_text(encoding="utf-8"))["items"]}
    best: dict[tuple, dict] = {}
    for f in files:
        sub = json.loads(Path(f).read_text(encoding="utf-8"))
        if sub.get("format") != "audit-v1":
            raise SystemExit(f"{f}: not an audit_labels.json file")
        for a, labs in sub["labels"].items():
            for iid, v in labs.items():
                if iid not in sample or a not in sample[iid]["annotators"] or not v.get("label"):
                    continue
                key = (iid, a)
                if key not in best or v.get("t", "") > best[key].get("t", ""):  # latest decision wins
                    best[key] = {**v, "guideline_version": sub.get("guideline_version", GUIDELINE_VERSION)}
    rows = []
    for (iid, a), v in sorted(best.items()):
        row = {"item_id": iid, "annotator_id": a, "label": v["label"], "in_overlap": sample[iid]["in_overlap"],
               "guideline_version": v["guideline_version"], "timestamp": v.get("t") or dt.datetime.now(dt.timezone.utc).isoformat(),
               "used_translation": bool(v.get("used_translation")), "unsure": bool(v.get("unsure"))}
        HumanLabel.model_validate(row)
        rows.append(row)
    write_jsonl(results / "human_audit.jsonl", rows)
    expected = {a: sum(a in s["annotators"] for s in sample.values()) for a in ANNOTATORS}
    done = {a: sum(r["annotator_id"] == a for r in rows) for a in ANNOTATORS}
    return {"labels": len(rows), "done_per_annotator": done, "expected_per_annotator": expected,
            "complete": done == expected}


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grading audit</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--accent:#c8102e;--ok:#1f7a4d;--sel:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#a3a29b;--line:#34332f;--accent:#ff5a6e;--ok:#4cc38a;--sel:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 6px 0 0}select,button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 10px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}.bar{flex:1;min-width:120px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--ok);width:0}main{padding:16px;max-width:900px;margin:auto}
.help{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}.card.done{border-color:var(--ok)}
.k{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);margin-top:10px}.q{font-weight:600}
.gloss{color:var(--mute);font-size:14px}.gold{white-space:pre-wrap;font-size:14px;background:var(--bg);border-radius:8px;padding:8px 10px}
.ans{white-space:pre-wrap;border-left:3px solid var(--sel);padding:4px 10px}.opts{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.opts button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}.row{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:14px}
.meta{font-size:12px;color:var(--mute)}.saved{font-size:12px;color:var(--mute)}input[type=file]{display:none}
</style></head><body>
<header><h1>Grading audit</h1>
<label>I am <select id="who"><option value="">choose…</option><option>A1</option><option>A2</option><option>A3</option></select></label>
<div class="bar"><i id="prog"></i></div><span id="count" class="meta"></span>
<button id="next">Next unlabelled ↓</button><button id="save" class="primary">Save progress</button>
<button id="loadbtn" type="button">Load saved file</button><input type="file" id="load" accept=".json,application/json">
<span id="saved" class="saved"></span></header>
<main>
<div class="help"><b>Read the guidelines (Task G) first.</b> Work <b>alone</b>: choose your ID, label your items, and do not discuss items until all three have finished. You only ever see your own labels.
For each item choose <b>Correct</b>, <b>Incorrect</b> or <b>Not attempted</b> by comparing the model's answer with the gold answer. Tick <i>used translation</i> if you relied on the English gloss, and <i>unsure</i> if it was a hard call.
Every click is saved in this browser. Press <b>Save progress</b> whenever you stop (downloads <code>audit_labels.json</code> with everyone's progress on this computer); <b>Load saved file</b> continues from such a file.</div>
<div id="list"></div></main>
<script>
const D = __DATA__, VERSION = "__VERSION__", KEY = "audit-v1";
const ITEMS = Object.fromEntries(D.items.map(x => [x.id, x]));
const $ = s => document.querySelector(s);
let who = "", all = {};
try { all = JSON.parse(localStorage.getItem(KEY) || "{}") || {} } catch (e) { all = {} }
function mine(){ return all[who] = all[who] || {} }
function persist(){ try { localStorage.setItem(KEY, JSON.stringify(all)); $("#saved").textContent = "autosaved " + new Date().toLocaleTimeString() } catch (e) { $("#saved").textContent = "⚠ browser storage off: use Save progress" } }
function set(id, patch){ mine()[id] = Object.assign({}, mine()[id], patch, {t: new Date().toISOString()}); persist(); redraw(id) }
function progress(){ const o = D.orders[who] || []; const n = o.filter(id => (mine()[id] || {}).label).length;
  $("#prog").style.width = (o.length ? 100 * n / o.length : 0) + "%"; $("#count").textContent = who ? n + " / " + o.length : "" }
function el(tag, cls, text){ const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e }
function card(id, k){ const it = ITEMS[id], s = mine()[id] || {}, c = el("div", "card" + (s.label ? " done" : "")); c.id = "c-" + id;
  c.append(el("div", "meta", (k + 1) + " · " + it.lang.toUpperCase() + " · " + it.arm + " · " + it.qtype));
  c.append(el("div", "k", "Question"), el("div", "q", it.question), el("div", "gloss", "EN: " + it.q_gloss));
  c.append(el("div", "k", "Gold answer"), el("div", "gold", it.gold));
  c.append(el("div", "k", "Model answer"), el("div", "ans", it.answer || "(empty)"));
  if (it.a_gloss) c.append(el("div", "gloss", "EN machine gloss (aid only, the original is authoritative): " + it.a_gloss));
  const o = el("div", "opts");
  [["correct", "Correct"], ["incorrect", "Incorrect"], ["not_attempted", "Not attempted"]].forEach(([v, l]) => {
    const b = el("button", s.label === v ? "on" : "", l); b.type = "button"; b.onclick = () => set(id, {label: v}); o.append(b) });
  c.append(o);
  const r = el("div", "row");
  [["used_translation", "used translation"], ["unsure", "unsure"]].forEach(([f, l]) => {
    const lab = el("label"), cb = el("input"); cb.type = "checkbox"; cb.checked = !!s[f]; cb.onchange = () => set(id, {[f]: cb.checked});
    lab.append(cb, document.createTextNode(" " + l)); r.append(lab) });
  c.append(r); return c }
function redraw(id){ const o = D.orders[who]; document.getElementById("c-" + id).replaceWith(card(id, o.indexOf(id))); progress() }
function render(){ const L = $("#list"); L.textContent = ""; if (!who){ L.textContent = "Choose your ID (A1, A2 or A3) at the top."; progress(); return }
  D.orders[who].forEach((id, k) => L.appendChild(card(id, k))); progress() }
$("#who").onchange = e => { who = e.target.value; render(); window.scrollTo(0, 0) };
$("#next").onclick = () => { if (!who) return; const id = D.orders[who].find(i => !(mine()[i] || {}).label);
  if (!id) return alert("All your items are labelled. Press Save progress."); document.getElementById("c-" + id).scrollIntoView({behavior: "smooth"}) };
$("#save").onclick = () => { const b = new Blob([JSON.stringify({format: "audit-v1", guideline_version: VERSION, exported_at: new Date().toISOString(), labels: all}, null, 1)], {type: "application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "audit_labels.json"; document.body.appendChild(a); a.click(); a.remove();
  $("#saved").textContent = "file saved " + new Date().toLocaleTimeString() };
$("#loadbtn").onclick = () => $("#load").click();
$("#load").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { const j = JSON.parse(t);
  if (j.format !== "audit-v1" || typeof j.labels !== "object") throw new Error("not an audit_labels.json file");
  const n = Object.values(j.labels).reduce((s, v) => s + Object.keys(v).length, 0);
  if (!confirm("Load " + n + " labels from " + f.name + "? Labels with the same ID and item are replaced by the newer one.")) return;
  for (const [a, labs] of Object.entries(j.labels)) { all[a] = all[a] || {};
    for (const [id, v] of Object.entries(labs)) if (!all[a][id] || (v.t || "") > (all[a][id].t || "")) all[a][id] = v }
  persist(); render() }).catch(err => alert("Could not load: " + err.message)); e.target.value = "" };
render();
</script></body></html>"""
