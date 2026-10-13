"""Generate the offline photo-screening page (Task P of docs/annotation_guidelines.md, guideline v2).

The team screens together on one computer (joint consensus decisions, no split). One card per landmark:
  main photo       OK / Exclude (person or private detail) / Wrong object
  other photos     pick at most one "2nd view" and at most one "Too generic"; "None usable" if no good view
Decisions autosave in the browser after every click; "Save progress" downloads the decisions file at any
time (also mid-way) and "Load saved file" resumes from it, e.g. on another browser. The file is merged
with `landmarks-eval merge-review`. Photos are the shipped 500 px files (images/ next to the page), with
Wikimedia Commons as a fallback when the folder is missing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import quote, unquote

GUIDELINE_VERSION = "v2-team"


def _commons(title: str, width: int) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(unquote(title))}?width={width}"


def cards(images: list[dict], lms: list[dict]) -> list[dict]:
    by_lm: dict[str, list[dict]] = {}
    for im in images:
        by_lm.setdefault(im["landmark_qid"], []).append(im)
    out = []
    for lm in lms:
        ims = by_lm.get(lm["qid"], [])
        main = [i for i in ims if i["role"] == "main_p18"]
        assert len(main) == 1, f"{lm['qid']}: expected one main photo, found {len(main)}"
        alts = sorted((i for i in ims if i["role"] == "alt"), key=lambda i: i["image_id"])
        name = next((v for v in (lm["labels"].get(l) for l in ("fr", "de", "en", "it", "rm")) if v), lm["qid"])

        def photo(im):
            return {"id": im["image_id"], "page": im["commons_page_url"], "faces": im["faces_detected"],
                    "fallback": _commons(im["commons_title"].removeprefix("File:"), 500)}

        out.append({"qid": lm["qid"], "name": name, "town": lm["municipality_name"], "canton": lm["canton_code"],
                    "main": photo(main[0]), "alts": [photo(a) for a in alts]})
    return out


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo screening</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--accent:#c8102e;--ok:#1f7a4d;--warn:#b54708;--sel:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#a3a29b;--line:#34332f;--accent:#ff5a6e;--ok:#4cc38a;--warn:#f0a35e;--sel:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 6px 0 0}button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 10px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}.bar{flex:1;min-width:120px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--ok);width:0}main{padding:16px;max-width:1150px;margin:auto}
.help{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:16px}.help li{margin:3px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:16px}
.card.done{border-color:var(--ok)}.card.done .title::after{content:"  ✓ done";color:var(--ok);font-weight:600}
.title{font-weight:600;font-size:16px}.meta{font-size:13px;color:var(--mute)}
.mainrow{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px;margin-top:8px}
img{width:100%;border-radius:8px;background:var(--line);min-height:90px;display:block;object-fit:contain;cursor:zoom-in}
.mainrow img{height:330px}.alt img{height:210px}
.alts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:12px}
.alt{border:2px solid transparent;border-radius:10px;padding:6px}.alt.view{border-color:var(--sel)}.alt.low{border-color:var(--warn)}
.q{margin:8px 0 4px;font-weight:600;font-size:14px}.opts{display:flex;flex-wrap:wrap;gap:6px}
.opts button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;border:1px solid var(--warn);color:var(--warn);margin:4px 0}
.saved{font-size:12px;color:var(--mute)}label{font-size:14px;cursor:pointer}input[type=file]{display:none}
@media (max-width:760px){.mainrow{grid-template-columns:1fr}.alts{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>Photo screening</h1>
<div class="bar"><i id="prog"></i></div><span id="count" class="meta"></span>
<label><input type="checkbox" id="hide"> Hide finished</label>
<button id="next">Next unfinished ↓</button>
<button id="save" class="primary">Save progress</button>
<button id="loadbtn" type="button">Load saved file</button><input type="file" id="load" accept=".json,application/json">
<span id="saved" class="saved"></span></header>
<main>
<div class="help"><b>Read once. You decide together, one card per landmark.</b><ol>
<li><b>Main photo:</b> <i>OK</i>, or <i>Exclude</i> if a recognisable person, a readable licence plate, a private interior or personal text is visible (tiny, distant people are fine), or <i>Wrong object</i> if it does not show this landmark (another building, a map, a painting).</li>
<li><b>Other photos:</b> click <i>Use as 2nd view</i> on the best one: the <i>same object</i>, seen clearly, with no recognisable people. If none qualifies, click <i>None usable</i>.</li>
<li><b>Optional:</b> click <i>Too generic</i> on a photo (no people) that alone could not tell even an expert <i>which</i> object it is: a plain wall, a generic door, a typical interior.</li></ol>
Click a photo to see it larger. When unsure: Exclude / don't pick. Every click is saved in this browser automatically. Press <b>Save progress</b> whenever you stop (it downloads <code>screening_team.json</code>); <b>Load saved file</b> continues from such a file. Send the last file to the team lead.</div>
<div id="list"></div></main>
<script>
const DATA = __DATA__, VERSION = "__VERSION__", KEY = "screening-team-v2";
const $ = s => document.querySelector(s);
let st = {}, lastSave = null;
try { st = JSON.parse(localStorage.getItem(KEY) || "{}") || {} } catch (e) { st = {} }
function persist(){ try { localStorage.setItem(KEY, JSON.stringify(st)); $("#saved").textContent = "autosaved " + new Date().toLocaleTimeString() } catch (e) { $("#saved").textContent = "⚠ browser storage off: use Save progress" } }
function dec(d){ return st[d.qid] || {} }
function complete(d){ const s = dec(d); if (!s.main) return false; if (s.main !== "ok" || !d.alts.length) return true; return !!s.alt }
function progress(){ const n = DATA.filter(complete).length; $("#prog").style.width = (100 * n / DATA.length) + "%"; $("#count").textContent = n + " / " + DATA.length + " landmarks" }
function set(d, patch){ const s = Object.assign({}, dec(d), patch);
  if (patch.alt && patch.alt !== "none" && s.low === patch.alt) delete s.low;       // a photo is a 2nd view OR too generic, not both
  if (patch.low && s.alt === patch.low) delete s.alt;
  st[d.qid] = s; persist(); redraw(d) }
function button(label, on, fn){ const b = document.createElement("button"); b.type = "button"; b.textContent = label; if (on) b.classList.add("on"); b.onclick = fn; return b }
function pic(p){ const i = document.createElement("img"); i.loading = "lazy"; i.alt = p.id; i.src = "images/" + p.id + ".jpg";
  i.onerror = () => { if (i.src !== p.fallback) i.src = p.fallback }; i.title = "click to enlarge"; i.onclick = () => window.open(i.src, "_blank"); return i }
function src(p){ const a = document.createElement("a"); a.href = p.page; a.target = "_blank"; a.rel = "noopener"; a.textContent = "source"; return a }
function faces(p, box){ if (p.faces > 0){ const t = document.createElement("div"); t.className = "tag"; t.textContent = "face detector: " + p.faces + " — check for people"; box.appendChild(t) } }
function card(d, k){ const s = dec(d), el = document.createElement("div"); el.className = "card" + (complete(d) ? " done" : ""); el.id = "c-" + d.qid;
  const t = document.createElement("div"); t.className = "title"; t.textContent = (k + 1) + ". " + d.name; el.appendChild(t);
  const m = document.createElement("div"); m.className = "meta"; m.append(d.town + " (" + d.canton + ") · " + d.qid + " · main photo ", src(d.main)); el.appendChild(m);
  const row = document.createElement("div"); row.className = "mainrow"; row.appendChild(pic(d.main));
  const side = document.createElement("div"); faces(d.main, side);
  let q = document.createElement("div"); q.className = "q"; q.textContent = "1. Main photo"; side.appendChild(q);
  let o = document.createElement("div"); o.className = "opts";
  o.append(button("OK", s.main === "ok", () => set(d, {main: "ok"})), button("Exclude: person / private", s.main === "exclude", () => set(d, {main: "exclude"})),
           button("Wrong object", s.main === "wrong", () => set(d, {main: "wrong"}))); side.appendChild(o);
  if (d.alts.length){ q = document.createElement("div"); q.className = "q"; q.textContent = "2. Other photos (" + d.alts.length + ")"; side.appendChild(q);
    o = document.createElement("div"); o.className = "opts"; o.append(button("None usable", s.alt === "none", () => set(d, {alt: "none"}))); side.appendChild(o) }
  else { const n = document.createElement("p"); n.className = "meta"; n.textContent = "No other photos for this landmark."; side.appendChild(n) }
  row.appendChild(side); el.appendChild(row);
  if (d.alts.length){ const g = document.createElement("div"); g.className = "alts";
    d.alts.forEach(p => { const b = document.createElement("div"); b.className = "alt" + (s.alt === p.id ? " view" : "") + (s.low === p.id ? " low" : "");
      b.appendChild(pic(p)); faces(p, b); const oo = document.createElement("div"); oo.className = "opts";
      oo.append(button("Use as 2nd view", s.alt === p.id, () => set(d, {alt: s.alt === p.id ? undefined : p.id})),
                button("Too generic", s.low === p.id, () => set(d, {low: s.low === p.id ? undefined : p.id})));
      b.appendChild(oo); const mm = document.createElement("div"); mm.className = "meta"; mm.append(src(p)); b.appendChild(mm); g.appendChild(b) });
    el.appendChild(g) }
  if ($("#hide").checked && complete(d)) el.style.display = "none";
  return el }
function redraw(d){ const k = DATA.indexOf(d); document.getElementById("c-" + d.qid).replaceWith(card(d, k)); progress() }
function render(){ const L = $("#list"); L.textContent = ""; DATA.forEach((d, k) => L.appendChild(card(d, k))); progress() }
function payload(){ const done = DATA.filter(complete).length;
  return {format: "team-consensus", annotator: "team", guideline_version: VERSION, exported_at: new Date().toISOString(), complete: done, total: DATA.length, decisions: st} }
$("#save").onclick = () => { const b = new Blob([JSON.stringify(payload(), null, 1)], {type: "application/json"}); const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "screening_team.json"; document.body.appendChild(a); a.click(); a.remove();
  $("#saved").textContent = "file saved " + new Date().toLocaleTimeString() };
$("#loadbtn").onclick = () => $("#load").click();
$("#load").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { const j = JSON.parse(t);
  if (j.format !== "team-consensus" || typeof j.decisions !== "object") throw new Error("not a screening_team.json file");
  const known = new Set(DATA.map(d => d.qid)), n = Object.keys(j.decisions).filter(q => known.has(q)).length;
  if (!confirm("Load " + n + " landmark decisions from " + f.name + "? This replaces what is shown now.")) return;
  st = {}; for (const q of Object.keys(j.decisions)) if (known.has(q)) st[q] = j.decisions[q]; persist(); render() })
  .catch(err => alert("Could not load: " + err.message)); e.target.value = "" };
$("#hide").onchange = render;
$("#next").onclick = () => { const d = DATA.find(x => !complete(x)); if (!d) return alert("All done — press Save progress and send the file.");
  if ($("#hide").checked) render(); document.getElementById("c-" + d.qid).scrollIntoView({behavior: "smooth", block: "start"}) };
render();
</script></body></html>"""


def build_review_page(work: Path, out_dir: Path | None = None) -> Path:
    """Write <out_dir>/photo_screening.html plus a copy of the photos in <out_dir>/images/."""
    images = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    lms = [json.loads(l) for l in open(work / "landmarks_final.jsonl", encoding="utf-8")]
    data = cards(images, lms)
    out_dir = out_dir or work / "review" / "photo_screening"
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    for im in images:
        src = work / "images" / f"{im['image_id']}.jpg"
        dst = out_dir / "images" / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = out_dir / "photo_screening.html"
    page.write_text(PAGE.replace("__DATA__", payload).replace("__VERSION__", GUIDELINE_VERSION), encoding="utf-8")
    return page
