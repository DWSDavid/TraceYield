"""Render the daily prediction as a terminal + markdown report."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src.utils.config import DATA
from src.models.predictor import HorizonPrediction

_ARROW = {"Bull": "▼", "Bear": "▲", "Neutral": "▬"}


def to_markdown(preds: list[HorizonPrediction], current_10y: float,
                run_date: date | None = None) -> str:
    run_date = run_date or date.today()
    lines = [
        f"# UST 10Y Prediction — {run_date:%Y-%m-%d}",
        "",
        f"**Current 10Y:** {current_10y:.2f}%",
        "",
        "| Horizon | Direction | Conf | Target |",
        "|---------|-----------|------|--------|",
    ]
    for p in preds:
        lines.append(
            f"| {p.horizon} | {_ARROW[p.direction]} {p.direction} "
            f"| {p.probability:.0%} | {p.target_yield:.2f}% |"
        )
    # Driver attribution from the longest horizon (most factor-driven).
    longest = preds[-1]
    lines += ["", "### Top drivers (3m view)", ""]
    ranked = sorted(longest.contributions.items(),
                    key=lambda kv: abs(kv[1]), reverse=True)
    for factor, contrib in ranked:
        sign = "+" if contrib >= 0 else ""
        lines.append(f"- `[{sign}{contrib:.3f}]` {factor}")
    lines.append("")
    lines.append("*Positive contribution = upward yield pressure = bond bearish.*")
    return "\n".join(lines)


def save(markdown: str, run_date: date | None = None) -> Path:
    run_date = run_date or date.today()
    out = DATA / "reports" / f"report_{run_date:%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    return out
