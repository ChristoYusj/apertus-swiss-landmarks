"""Generate the offline photo-screening page (Task P of docs/annotation_guidelines.md).

One self-contained HTML file: the annotator picks A1/A2/A3, reviews their assigned photos
(main photos: privacy only; alternative views: privacy + "good 2nd view" + "too generic"),
decisions persist in the browser, and "Download my decisions" saves a JSON file that is
merged with `landmarks-eval merge-review`. Photos are loaded from Wikimedia Commons.
"""

from __future__ import annotations

import html
import json
import random
from pathlib import Path
from urllib.parse import quote, unquote

OVERLAP_RANDOM = 60
OVERLAP_LOWINFO = 40
SEED = 20261013


def assign(images: list[dict], lms: dict) -> list[dict]:
    rng = random.Random(SEED)
    ids = sorted(i["image_id"] for i in images)
    low_alts = sorted(i["image_id"] for i in images
                      if i["role"] == "alt" and lms[i["landmark_qid"]]["fame_tier"] == "low")
    overlap = set(rng.sample(low_alts, min(OVERLAP_LOWINFO, len(low_alts))))
    rest = [i for i in ids if i not in overlap]
    overlap |= set(rng.sample(rest, min(OVERLAP_RANDOM, len(rest))))
    others = [i for i in ids if i not in overlap]
    rng.shuffle(others)
    who = {i: ["A1", "A2", "A3"] for i in overlap}
    for k, i in enumerate(others):
        who[i] = [["A1", "A2", "A3"][k % 3]]
    out = []
    for im in images:
        lm = lms[im["landmark_qid"]]
        name = next((v for v in (lm["labels"].get(l) for l in ("fr", "de", "en", "it", "rm")) if v), lm["qid"])
        title = im["commons_title"].removeprefix("File:")
        out.append({"id": im["image_id"], "qid": im["landmark_qid"], "role": im["role"], "name": name,
                    "town": lm["municipality_name"], "faces": im["faces_detected"],
                    "src": f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(title)}?width=500",
                    "main": f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(unquote(lm['p18_file'].rsplit('/', 1)[-1]))}?width=240",
                    "page": im["commons_page_url"], "who": who[im["image_id"]], "overlap": len(who[im["image_id"]]) == 3})
    out.sort(key=lambda x: (x["qid"], x["role"] != "main_p18", x["id"]))
    return out


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo screening</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--accent:#c8102e;--ok:#1f7a4d;--warn:#b54708}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#a3a29b;--line:#34332f;--accent:#ff5a6e;--ok:#4cc38a;--warn:#f0a35e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 8px 0 0}select,button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 10px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}.bar{flex:1;min-width:160px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--ok);width:0}main{padding:16px;max-width:1100px;margin:auto}
.help{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:14px;display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:14px}
.card.done{opacity:.6}.card img.big{width:100%;border-radius:8px;background:var(--line);min-height:120px}
.meta{font-size:13px;color:var(--mute)}.meta b{color:var(--ink)}.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;border:1px solid var(--line);margin-right:4px}
.tag.alt{border-color:var(--accent);color:var(--accent)}.tag.face{border-color:var(--warn);color:var(--warn)}
.q{margin:10px 0 4px;font-weight:600;font-size:14px}.opts button{margin:0 6px 6px 0}.opts button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.side img{width:100%;border-radius:8px}label{font-size:14px}
@media (max-width:720px){.card{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Photo screening</h1>
<label>I am <select id="who"><option value="">choose…</option><option>A1</option><option>A2</option><option>A3</option></select></label>
<div class="bar"><i id="prog"></i></div><span id="count" class="meta"></span>
<button id="dl" class="primary">Download my decisions</button></header>
<main>
<div class="help"><b>Read once.</b> For every photo answer <b>Privacy</b>: <i>Exclude</i> if a recognisable person, a readable licence plate, a private interior or personal text is visible (tiny distant people are fine).
For photos tagged <span class="tag alt">2nd view</span> also answer: is it <i>the same object</i> as the small main photo, seen clearly from outside? And tick <i>Too generic</i> if this photo alone could not tell even an expert <i>which</i> object it is.
When unsure: Exclude / Not usable. Your choices are saved in this browser; press <b>Download my decisions</b> at the end and send the file to the team lead.</div>
<div id="list"></div></main>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
let who = "", st = {};
function key(){return "screening-"+who}
function load(){try{st=JSON.parse(localStorage.getItem(key())||"{}")}catch(e){st={}}}
function save(){try{localStorage.setItem(key(),JSON.stringify(st))}catch(e){}}
function mine(){return DATA.filter(d=>d.who.includes(who))}
function complete(d){const s=st[d.id]||{};return s.privacy&&(d.role!=="alt"||s.privacy==="exclude"||s.view)}
function progress(){const m=mine();const n=m.filter(complete).length;$("#prog").style.width=(m.length?100*n/m.length:0)+"%";$("#count").textContent=n+" / "+m.length}
function btn(d,field,val,label){const b=document.createElement("button");b.textContent=label;if((st[d.id]||{})[field]===val)b.classList.add("on");
 b.onclick=()=>{st[d.id]=Object.assign({},st[d.id],{[field]:val});save();render(d.id)};return b}
function card(d){const el=document.createElement("div");el.className="card"+(complete(d)?" done":"");el.id="c-"+d.id;
 const left=document.createElement("div");const img=document.createElement("img");img.className="big";img.loading="lazy";img.src=d.src;img.alt=d.name;left.appendChild(img);
 const meta=document.createElement("div");meta.className="meta";meta.innerHTML="";const t=document.createElement("b");t.textContent=d.name;meta.appendChild(t);
 meta.appendChild(document.createTextNode(" — "+d.town+" · "+d.id+" "));const a=document.createElement("a");a.href=d.page;a.target="_blank";a.rel="noopener";a.textContent="source";meta.appendChild(a);left.appendChild(meta);
 const side=document.createElement("div");side.className="side";
 const tags=document.createElement("div");if(d.role==="alt"){const s=document.createElement("span");s.className="tag alt";s.textContent="2nd view";tags.appendChild(s)}
 if(d.faces>0){const s=document.createElement("span");s.className="tag face";s.textContent="check: "+d.faces+" face(s)?";tags.appendChild(s)}side.appendChild(tags);
 let q=document.createElement("div");q.className="q";q.textContent="Privacy";side.appendChild(q);let o=document.createElement("div");o.className="opts";
 o.append(btn(d,"privacy","keep","OK"),btn(d,"privacy","exclude","Exclude"));side.appendChild(o);
 if(d.role==="alt"){q=document.createElement("div");q.className="q";q.textContent="Same object, clear 2nd view?";side.appendChild(q);
  o=document.createElement("div");o.className="opts";o.append(btn(d,"view","good","Good 2nd view"),btn(d,"view","bad","Not usable"));side.appendChild(o);
  const lab=document.createElement("label");const cb=document.createElement("input");cb.type="checkbox";cb.checked=!!(st[d.id]||{}).lowinfo;
  cb.onchange=()=>{st[d.id]=Object.assign({},st[d.id],{lowinfo:cb.checked});save()};lab.append(cb,document.createTextNode(" Too generic to identify"));side.appendChild(lab);
  q=document.createElement("div");q.className="q";q.textContent="Main photo";side.appendChild(q);const m=document.createElement("img");m.loading="lazy";m.src=d.main;m.alt="main photo";side.appendChild(m)}
 el.append(left,side);return el}
function render(id){if(id){const old=document.getElementById("c-"+id);const d=DATA.find(x=>x.id===id);old.replaceWith(card(d));progress();return}
 const L=$("#list");L.textContent="";if(!who){L.textContent="Choose your ID (A1, A2 or A3) at the top.";return}
 mine().forEach(d=>L.appendChild(card(d)));progress()}
$("#who").onchange=e=>{who=e.target.value;load();render()};
$("#dl").onclick=()=>{if(!who)return alert("Choose your ID first");const out={annotator:who,guideline_version:"v1",exported_at:new Date().toISOString(),decisions:st};
 const b=new Blob([JSON.stringify(out,null,1)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="screening_"+who+".json";a.click()};
render();
</script></body></html>"""


def build_review_page(work: Path) -> Path:
    images = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    lms = {json.loads(l)["qid"]: json.loads(l) for l in open(work / "landmarks_final.jsonl", encoding="utf-8")}
    data = assign(images, lms)
    out = work / "review" / "photo_screening.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    counts = {a: sum(a in d["who"] for d in data) for a in ("A1", "A2", "A3")}
    (work / "review" / "assignment.json").write_text(json.dumps({"counts": counts, "overlap": sum(d["overlap"] for d in data),
                                                                "items": [{k: d[k] for k in ("id", "who")} for d in data]},
                                                               indent=1), encoding="utf-8")
    return out
