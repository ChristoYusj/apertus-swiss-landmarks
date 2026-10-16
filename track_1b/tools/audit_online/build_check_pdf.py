"""Fillable PDF version of the human grading check (same items as human_check.html), one answer per iPad-size page.

  python build_check_pdf.py <human_check_items.json> <out.pdf>        (needs reportlab; team-only tool)

Per page: the question (+ English), the gold answer, the model answer (+ English machine translation), the second
AI's proposed grade and reason, then a "Your grade" drop-down (grade_NNN) and two tick boxes (trans_NNN = used the
translation, unsure_NNN). `read_check_pdf.py` turns a filled copy into human_check_A1.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

W, H, M = 768, 1152, 44
FORM_TOP = 230                     # the text must stay above this line (the form fields are below it)
NAME = {"correct": "Correct", "incorrect": "Incorrect", "not_attempted": "Not attempted"}
CHOOSE = "Choose..."


def options(it: dict) -> list[str]:
    ai = [f"Agree with AI ({NAME[it['ai_label']]})"] if it.get("ai_label") else []
    return [CHOOSE, *ai, "Correct", "Incorrect", "Not attempted"]


def main(items_path: Path, out: Path, blind: bool = False) -> None:
    data = json.loads(items_path.read_text(encoding="utf-8"))
    items, who = data["items"], data.get("annotator", "A1")
    if blind:   # protocol audit-v4: no grade of any kind may reach a blind page
        assert not any(k in it for it in items for k in ("ai_label", "ai_reason", "judge_label", "code_label")), items_path
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Body", str(fonts / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Bold", str(fonts / "arialbd.ttf")))
    ink, mute, blue = colors.HexColor("#18212b"), colors.HexColor("#5d6a72"), colors.HexColor("#2453b8")
    c = canvas.Canvas(str(out), pagesize=(W, H), pageCompression=1)
    c.setTitle(f"Grading {'Audit' if blind else 'Check'} ({who})")
    c.setAuthor("Red Pandas - Hack Apertus 2026")

    def para(text, y, size=13.0, bold=False, color=ink, bg=None, draw=True):
        st = ParagraphStyle("p", fontName="Bold" if bold else "Body", fontSize=size, leading=size * 1.35, textColor=color)
        lines = escape(text).split("\n")
        p = Paragraph("<br/>".join(lines), st)
        _, h = p.wrap(W - 2 * M - (16 if bg else 0), H)
        if bg:
            if draw:
                c.setFillColor(bg)
                c.roundRect(M - 2, y - h - 10, W - 2 * M + 4, h + 14, 6, stroke=0, fill=1)
                p.drawOn(c, M + 8, y - h - 4)
            return y - h - 24
        if draw:
            p.drawOn(c, M, y - h)
        return y - h - 10

    # page 1: instructions
    y = H - M
    y = para(f"Grading {'Audit' if blind else 'Check'} ({who}): {len(items)} answers of Apertus 1.5 70B", y, 24, True)
    y = para(f"Annotator {who}. One answer per page. " + (
        "No grade is shown: read the model answer against the gold answer and pick a value in the \"Your grade\" box "
        "at the bottom of the page. Work alone, without looking anything up" + (
            "." if data.get("single") else " and without discussing items with the others until all three have "
            "finished.") if blind else
        "A second AI already proposed a grade: judge each answer yourself, then pick a value in the \"Your grade\" "
        "box at the bottom of the page."), y - 6, 15)
    for line in (
        "Correct: it names the gold landmark / the right municipality / a year in the window, and nothing contradicts "
        "the gold.",
        "Incorrect: it commits to something wrong: another landmark, another municipality, a village instead of the "
        "municipality, a wrong canton or country, several competing candidates, or (trick question) it accepts the "
        "false town.",
        "Not attempted: it declines, or stays too vague to check (\"a church in the Alps\", only the right canton), "
        "without contradicting the gold.",
        "Names marked [only with the town] count only together with the right town. A hedged guess (\"probably X\") is "
        "graded on X.",
        "Tick \"used translation\" if you relied on the English text, \"unsure\" for hard calls.",
        "When finished: save the PDF (it keeps your answers) and send it back. Partial is fine: unanswered pages are "
        "skipped.",
    ):
        y = para("•  " + line, y, 14)
    if not blind:
        para("This check is not blind: the AI's proposed grade is shown, and the report says so.", y - 10, 13, color=mute)
    c.showPage()

    def item_text(it, size, draw):
        y = H - M
        y = para(f"#{it['n']} of {len(items)}   ·   {it['lang'].upper()}   ·   {it['qtype']}   ·   "
                 f"{it['arm'].replace('_', ' ')}", y, 12, True, mute, draw=draw)
        y = para("QUESTION", y, 10, True, mute, draw=draw)
        y = para(it["question"], y, size, draw=draw)
        if it.get("q_gloss"):
            y = para("English: " + it["q_gloss"], y, size - 1, color=mute, draw=draw)
        y = para("GOLD ANSWER", y, 10, True, mute, draw=draw)
        y = para(it["gold"], y, size - 1, bg=colors.HexColor("#eef1f0"), draw=draw)
        y = para("MODEL ANSWER", y, 10, True, mute, draw=draw)
        y = para(it["answer"] or "(empty)", y, size, draw=draw)
        if it.get("a_gloss"):
            y = para("English (machine translation): " + it["a_gloss"], y, size - 1, color=mute, draw=draw)
        if blind:
            return y
        ai = (f"AI's proposed grade: {NAME[it['ai_label']]}" + (f" - {it['ai_reason']}" if it.get("ai_reason") else "")
              if it.get("ai_label") else "The AI left this one ungraded (unsure): choose the grade yourself.")
        return para(ai, y, size - 1, bg=colors.HexColor("#e7eefc"), draw=draw)

    too_long = []
    for it in items:
        k = f"{it['n']:03d}"
        size = next((s for s in (13, 12, 11, 10, 9, 8) if item_text(it, s, draw=False) > FORM_TOP), 8)   # measure first
        if item_text(it, size, draw=True) <= FORM_TOP:
            too_long.append(it["n"])
        c.setFont("Bold", 15)
        c.setFillColor(ink)
        c.drawString(M, 184, "Your grade:")
        c.acroForm.choice(name=f"grade_{k}", value=CHOOSE, options=options(it), x=M + 104, y=170, width=360, height=38,
                          fontName="Helvetica", fontSize=15, borderColor=blue, fillColor=colors.white, textColor=ink,
                          forceBorder=True)
        for j, (fld, label) in enumerate(((f"trans_{k}", "used translation"), (f"unsure_{k}", "unsure"))):
            x = M + j * 240
            c.acroForm.checkbox(name=fld, x=x, y=104, size=28, buttonStyle="check", borderColor=blue,
                                fillColor=colors.white, textColor=ink, forceBorder=True)
            c.setFont("Body", 15)
            c.setFillColor(ink)
            c.drawString(x + 38, 112, label)
        c.setFont("Body", 10)
        c.setFillColor(mute)
        c.drawString(M, 56, f"item {it['id']}")
        c.showPage()
    c.save()
    print(f"{len(items)} items, {len(items) + 1} pages; text reaching the form area on items: {too_long}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), blind="--blind" in sys.argv[3:])
