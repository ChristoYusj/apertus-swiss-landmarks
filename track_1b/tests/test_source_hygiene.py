"""Regression guard: no invisible control characters in source/config files (they silently break regexes)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def test_no_control_characters_in_text_files():
    bad = []
    for p in list((ROOT / "src").rglob("*")) + list((ROOT / "tests").glob("*.py")) + [ROOT / "Makefile", ROOT / "Dockerfile"]:
        if p.is_file() and p.suffix in {".py", ".yaml", ".rq", ".json", ".md", ""}:
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if CTRL.search(line.replace("\t", "")):
                    bad.append(f"{p.relative_to(ROOT)}:{n}")
    assert not bad, bad
