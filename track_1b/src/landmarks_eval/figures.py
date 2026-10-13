"""Report figures from scores.json (optional extra: pip install .[figures]).

  fig1_languages.png   same photos, four question languages: correct / incorrect / not attempted (name, place)
  fig2_graubunden.png  share of place answers that say Graubünden, by question language, vs the true share
  fig3_know_vs_see.png text-only vs photo place accuracy by fame tier; premise trap vs paired control
The subtitle states which grader produced the labels (judge or code grader), so drafts cannot pass as final.
"""

from __future__ import annotations

import json
from pathlib import Path

COLORS = {"correct": "#1f7a4d", "incorrect": "#c8102e", "not_attempted": "#b9b8b1"}
LANGS = [("fr", "French"), ("it", "Italian"), ("de", "German"), ("rm", "Romansh")]


def _grader(s: dict) -> str:
    src = s["coverage"]["final_source"]
    return "labels: LLM judge" if src.get("judge") else "labels: code grader (preliminary; judge pending)"


def make_figures(scores_path: Path, out: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = json.loads(scores_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    paths = []

    # 1. same photos, four languages
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0), sharey=True)
    for ax, q, title in ((axes[0], "name", "Q1 name"), (axes[1], "place", "Q2 municipality")):
        left = [0.0] * len(LANGS)
        for lab in ("incorrect", "not_attempted", "correct"):
            vals = [100 * s["photo_main_by_lang_qtype"][f"{l}|{q}"][f"pct_{lab}"] for l, _ in LANGS]
            ax.barh([n for _, n in LANGS], vals, left=left, color=COLORS[lab], label=lab.replace("_", " "))
            for i, v in enumerate(vals):
                if v >= 8:
                    ax.text(left[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", color="white" if lab != "not_attempted" else "black", fontsize=9)
            left = [a + b for a, b in zip(left, vals)]
        ax.set_title(title)
        ax.set_xlim(0, 100)
        ax.invert_yaxis()
    axes[0].legend(loc="lower center", bbox_to_anchor=(1.0, -0.42), ncol=3, frameon=False)
    fig.suptitle(f"Same 264 photos, four question languages (Apertus 1.5 70B) — {_grader(s)}", fontsize=10)
    fig.tight_layout()
    p = out / "fig1_languages.png"
    fig.savefig(p, dpi=200, bbox_inches="tight")
    paths.append(p)
    plt.close(fig)

    # 2. Graubünden pull
    loc = s.get("location_photo_main_place")
    if loc:
        fig, ax = plt.subplots(figsize=(5.2, 2.8))
        vals = [100 * loc[l]["pct_placed_in_GR"] for l, _ in LANGS]
        nongr = [100 * loc[l]["pct_nonGR_landmarks_placed_in_GR"] for l, _ in LANGS]
        x = range(len(LANGS))
        ax.bar([i - 0.2 for i in x], vals, width=0.4, color="#1d4ed8", label="all landmarks")
        ax.bar([i + 0.2 for i in x], nongr, width=0.4, color="#93a8e8", label="landmarks NOT in Graubünden")
        ax.axhline(100 * loc["gold_pct_GR"], ls="--", color="#555", lw=1)
        ax.text(3.45, 100 * loc["gold_pct_GR"] + 2, "true share", ha="right", fontsize=8, color="#555")
        ax.set_xticks(list(x), [n for _, n in LANGS])
        ax.set_ylabel("% of place answers\nsaying Graubünden")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        ax.set_title(f"Where the answer puts the landmark — {_grader(s)}", fontsize=9)
        fig.tight_layout()
        p = out / "fig2_graubunden.png"
        fig.savefig(p, dpi=200, bbox_inches="tight")
        paths.append(p)
        plt.close(fig)

    # 3. knowing vs seeing (by fame) + premise
    fig, axes = plt.subplots(1, 2, figsize=(9, 2.9), gridspec_kw={"width_ratios": [1.6, 1]})
    tiers = ["low", "mid", "high"]
    t = [100 * s["text_only_by_tier_qtype"][f"{k}|place"]["pct_correct"] for k in tiers]
    ph = [100 * s["photo_main_by_tier_qtype"][f"{k}|place"]["pct_correct"] for k in tiers]
    x = range(3)
    axes[0].bar([i - 0.2 for i in x], t, width=0.4, color="#1f7a4d", label="name given (text only)")
    axes[0].bar([i + 0.2 for i in x], ph, width=0.4, color="#8fc7a8", label="photo only")
    axes[0].set_xticks(list(x), ["low fame", "mid fame", "high fame"])
    axes[0].set_ylabel("% municipality correct")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_title("Knowing vs recognising (Q2)", fontsize=10)
    h4 = s.get("hypotheses", {}).get("H4")
    if h4:
        axes[1].bar(["plain question", "false town\nin question"], [100 * h4["control_incorrect_rate"], 100 * h4["premise_incorrect_rate"]],
                    color=["#e3a0a8", "#c8102e"])
        axes[1].set_ylabel("% incorrect")
        axes[1].set_title(f"False premise (n = {h4['pairs']} pairs)", fontsize=10)
    fig.suptitle(_grader(s), fontsize=9)
    fig.tight_layout()
    p = out / "fig3_know_vs_see.png"
    fig.savefig(p, dpi=200, bbox_inches="tight")
    paths.append(p)
    plt.close(fig)
    return paths
