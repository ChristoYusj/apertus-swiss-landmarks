"""Official municipality → language-region and canton mapping (Swiss Federal Statistical Office).

Source: BFS "Applikation der Schweizer Gemeinden" typology export
(https://www.agvchapp.bfs.admin.ch/api/communes/levels?date=DD-MM-YYYY), column
SPRGEB2020 = language region 2020 (1 German, 2 French, 3 Italian, 4 Romansh).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

from .sparql import USER_AGENT

BFS_URL = "https://www.agvchapp.bfs.admin.ch/api/communes/levels?date={date}"
REGION_CODE = {"1": "DE", "2": "FR", "3": "IT", "4": "RM"}
# Official BFS canton numbering 1..26 -> ISO 3166-2:CH suffix.
CANTON_BY_BFS_ID = {
    "1": "ZH", "2": "BE", "3": "LU", "4": "UR", "5": "SZ", "6": "OW", "7": "NW", "8": "GL", "9": "ZG",
    "10": "FR", "11": "SO", "12": "BS", "13": "BL", "14": "SH", "15": "AR", "16": "AI", "17": "SG",
    "18": "GR", "19": "AG", "20": "TG", "21": "TI", "22": "VD", "23": "VS", "24": "NE", "25": "GE", "26": "JU",
}


def load_bfs_table(work: Path, date: str = "01-10-2026", refresh: bool = False) -> dict[str, dict]:
    """Return {bfs_number: {name, canton_code, region}} for the municipalities valid on `date`."""
    path = work / f"bfs_levels_{date}.csv"
    if refresh or not path.exists():
        r = requests.get(BFS_URL.format(date=date), headers={"User-Agent": USER_AGENT}, timeout=120)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    text = path.read_bytes().decode("utf-8-sig")
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = row["SPRGEB2020"].strip()
        if code not in REGION_CODE:
            raise ValueError(f"unexpected SPRGEB2020 value {code!r} for {row['Name']}")
        out[row["BfsCode"].strip()] = {
            "name": row["Name"].strip(),
            "canton_code": CANTON_BY_BFS_ID[row["CantonId"].strip()],
            "region": REGION_CODE[code],
        }
    return out
