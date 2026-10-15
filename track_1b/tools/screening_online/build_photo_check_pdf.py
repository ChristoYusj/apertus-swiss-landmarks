"""Human look at every published photo: a fillable PDF grid (6 photos per page), one "problem" tick box per photo.

  python build_photo_check_pdf.py <dataset dir> <out.pdf>        (needs reportlab; team-only tool)

A person ticks a photo that shows a recognisable face, a readable licence plate, a private interior or personal
text (rule 1 of the photo screening). Field names: prob_<image_id>. `read_photo_check_pdf.py` lists the ticked ones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

W, H, M = 768, 1152, 36
COLS, ROWS = 2, 3
ROLE = {"main_p18": "main photo", "alt": "photo"}


def main(ds: Path, out: Path) -> None:
    imgs = [json.loads(l) for l in open(ds / "metadata" / "images.jsonl", encoding="utf-8")]
    lms = {json.loads(l)["qid"]: json.loads(l) for l in open(ds / "data" / "landmarks.jsonl", encoding="utf-8")}
    cases = [json.loads(l) for l in open(ds / "data" / "test_cases.jsonl", encoding="utf-8")]
    arm_of = {c["image_id"]: c["arm"] for c in cases if c.get("image_id")}
    role = {i["image_id"]: {"photo_main": "main photo", "photo_alt": "2nd view", "trap_lowinfo": "too generic"}.get(
        arm_of.get(i["image_id"]), "photo") for i in imgs}
    imgs.sort(key=lambda i: (i["landmark_qid"], i["role"] != "main_p18", i["image_id"]))
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Body", str(fonts / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Bold", str(fonts / "arialbd.ttf")))
    ink, mute, blue = colors.HexColor("#18212b"), colors.HexColor("#5d6a72"), colors.HexColor("#c8261b")
    c = canvas.Canvas(str(out), pagesize=(W, H), pageCompression=1)
    c.setTitle("Photo Check (A1)")
    c.setAuthor("Red Pandas - Hack Apertus 2026")
    c.setFont("Bold", 24)
    c.setFillColor(ink)
    c.drawString(M, H - 70, f"Photo check: all {len(imgs)} published photos")
    c.setFont("Body", 15)
    for k, line in enumerate((
            "Look at every photo. Tick \"problem\" under a photo only if it shows:",
            "  - a recognisable person (a face, or someone close enough to identify),",
            "  - a readable car licence plate,",
            "  - the inside of a private home, or",
            "  - personal text (name plates, letters).",
            "Tiny, distant people are fine. Statues and paintings are not people.",
            "Leave everything else unticked. Zoom in when unsure.",
            "When finished: save the PDF and send it back.")):
        c.drawString(M, H - 120 - 26 * k, line)
    c.showPage()
    cw, ch = (W - 2 * M) / COLS, (H - 2 * M) / ROWS
    for n, im in enumerate(imgs):
        slot = n % (COLS * ROWS)
        if n and slot == 0:
            c.showPage()
        col, row = slot % COLS, slot // COLS
        x0, y0 = M + col * cw, H - M - (row + 1) * ch
        path = str(ds / "images" / f"{im['image_id']}.jpg")
        iw, ih = ImageReader(path).getSize()
        box_w, box_h = cw - 16, ch - 92
        s = min(box_w / iw, box_h / ih)
        c.drawImage(path, x0 + 8 + (box_w - iw * s) / 2, y0 + 84 + (box_h - ih * s) / 2, iw * s, ih * s)
        lm = lms[im["landmark_qid"]]
        name = next((v for v in (lm["labels"].get(l) for l in ("fr", "de", "en", "it", "rm")) if v), lm["qid"])
        c.setFont("Bold", 11)
        c.setFillColor(ink)
        c.drawString(x0 + 8, y0 + 66, f"#{n + 1}  {name}"[:58])
        c.setFont("Body", 10)
        c.setFillColor(mute)
        c.drawString(x0 + 8, y0 + 52, f"{role[im['image_id']]} · {im['image_id']}")
        c.acroForm.checkbox(name=f"prob_{im['image_id']}", x=x0 + 8, y=y0 + 14, size=26, buttonStyle="cross",
                            borderColor=blue, fillColor=colors.white, textColor=blue, forceBorder=True)
        c.setFont("Body", 14)
        c.setFillColor(ink)
        c.drawString(x0 + 42, y0 + 21, "problem")
    c.showPage()
    c.save()
    print(f"{len(imgs)} photos, {1 + -(-len(imgs) // (COLS * ROWS))} pages")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
