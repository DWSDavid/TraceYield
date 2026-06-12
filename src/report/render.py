"""Render the daily prediction as a terminal + markdown report."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.utils.config import DATA
from src.models.predictor import HorizonPrediction

_ARROW = {"Bull": "▼", "Bear": "▲", "Neutral": "▬"}


def to_markdown(
    preds: list[HorizonPrediction], current_10y: float, run_date: date | None = None
) -> str:
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
    lines += ["", f"### Top drivers ({longest.horizon} view)", ""]
    ranked = sorted(
        longest.contributions.items(), key=lambda kv: abs(kv[1]), reverse=True
    )
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


# --- HTML report -----------------------------------------------------------

_DIR_COLOR = {"Bull": "#16a34a", "Bear": "#dc2626", "Neutral": "#6b7280"}


def _bar(value: float, scale: float = 0.5) -> str:
    """A signed horizontal bar (red=up/bearish, green=down/bullish), centered."""
    pct = max(-1.0, min(1.0, value / scale)) * 50
    color = "#dc2626" if value >= 0 else "#16a34a"
    if value >= 0:
        left, width = 50, pct
    else:
        left, width = 50 + pct, -pct
    return (
        f'<div class="track"><div class="fill" style="left:{left}%;'
        f'width:{width}%;background:{color}"></div></div>'
    )


def to_html(
    preds,
    current_10y: float,
    factors: dict,
    fomc: dict | None = None,
    run_date: date | None = None,
) -> str:
    run_date = run_date or date.today()
    rows = ""
    for p in preds:
        c = _DIR_COLOR[p.direction]
        move = p.target_yield - current_10y
        rows += (
            f"<tr><td class='h'>{p.horizon}</td>"
            f"<td style='color:{c};font-weight:600'>{_ARROW[p.direction]} {p.direction}</td>"
            f"<td>{p.probability:.0%}</td>"
            f"<td>{p.target_yield:.2f}%</td>"
            f"<td style='color:{'#dc2626' if move>=0 else '#16a34a'}'>"
            f"{move*100:+.0f} bp</td></tr>"
        )

    longest = preds[-1]
    frows = ""
    for f, contrib in sorted(
        longest.contributions.items(), key=lambda kv: abs(kv[1]), reverse=True
    ):
        raw = factors.get(f, 0.0)
        frows += (
            f"<tr><td class='fname'>{f}</td>"
            f"<td>{_bar(raw)}</td>"
            f"<td class='num'>{raw:+.2f}</td>"
            f"<td class='num'>{contrib:+.3f}</td></tr>"
        )

    def _doc_block(label: str, rec: dict | None) -> str:
        if not rec:
            return ""
        col = "#dc2626" if rec.get("blended", 0) >= 0 else "#16a34a"
        quotes = "".join(
            f"<blockquote>“{q}”</blockquote>" for q in rec.get("key_quotes", [])[:4]
        )
        phrases = "".join(
            f"<span class='chip'>{p}</span>" for p in rec.get("key_phrases", [])[:6]
        )
        return f"""
          <div class="doc">
            <div class="dochead"><span class="badge">{label}</span>
              <span class="docfile">{rec.get('file','')}</span>
              <b style="color:{col};margin-left:auto">{rec.get('blended',0):+.2f}</b></div>
            <p class="muted">LLM {rec.get('llm_score')} · keyword
              {rec.get('keyword_score')} · {rec.get('provider','')}</p>
            <p class="rationale">{rec.get('rationale','')}</p>
            {quotes}
            <div class="chips">{phrases}</div>
          </div>"""

    fomc_block = ""
    if fomc:
        comb = fomc.get("blended", 0)
        col = "#dc2626" if comb >= 0 else "#16a34a"
        fomc_block = f"""
        <div class="card">
          <h2>FOMC tone &amp; evidence</h2>
          <p class="score">combined hawkish score
            <b style="color:{col}">{comb:+.2f}</b>
            <span class="muted">(0.6·statement + 0.4·minutes)</span></p>
          {_doc_block('STATEMENT', fomc.get('statement'))}
          {_doc_block('MINUTES', fomc.get('minutes'))}
        </div>"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TraceYield — {run_date:%Y-%m-%d}</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f172a;
   color:#e2e8f0;margin:0;padding:32px}}
 .wrap{{max-width:760px;margin:0 auto}}
 h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#94a3b8;margin:0 0 24px}}
 .card{{background:#1e293b;border:1px solid #334155;border-radius:12px;
   padding:20px 24px;margin-bottom:20px}}
 h2{{font-size:15px;text-transform:uppercase;letter-spacing:.05em;color:#94a3b8;
   margin:0 0 14px}}
 table{{width:100%;border-collapse:collapse}}
 td,th{{padding:8px 10px;text-align:left;border-bottom:1px solid #334155}}
 th{{color:#94a3b8;font-size:12px;text-transform:uppercase}}
 .h{{font-weight:700;color:#f1f5f9}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
 .fname{{color:#cbd5e1}} .big{{font-size:34px;font-weight:700;color:#f1f5f9}}
 .track{{position:relative;height:10px;background:#0f172a;border-radius:5px;
   width:160px;border:1px solid #334155}}
 .track::before{{content:'';position:absolute;left:50%;top:-2px;bottom:-2px;
   width:1px;background:#475569}}
 .fill{{position:absolute;top:0;bottom:0;border-radius:5px}}
 .chip{{display:inline-block;background:#0f172a;border:1px solid #334155;
   border-radius:6px;padding:3px 8px;margin:3px 4px 0 0;font-size:12px;color:#cbd5e1}}
 .rationale{{color:#cbd5e1}} .muted{{color:#64748b;font-size:13px;font-weight:400}}
 .score{{font-size:15px}} .foot{{color:#64748b;font-size:12px;text-align:center;
   margin-top:8px}}
 .doc{{border-top:1px solid #334155;padding-top:14px;margin-top:14px}}
 .dochead{{display:flex;align-items:center;gap:10px;margin-bottom:4px}}
 .badge{{background:#2563eb;color:#fff;font-size:11px;font-weight:700;
   letter-spacing:.04em;padding:2px 8px;border-radius:5px}}
 .docfile{{color:#94a3b8;font-size:13px}}
 blockquote{{margin:8px 0;padding:8px 14px;border-left:3px solid #2563eb;
   background:#0f172a;border-radius:0 6px 6px 0;color:#e2e8f0;font-size:13.5px;
   font-style:italic}}
</style></head><body><div class="wrap">
 <h1>UST 10Y Yield Prediction</h1>
 <p class="sub">{run_date:%A, %B %d, %Y} · current 10Y <b class="big"
   style="font-size:18px">{current_10y:.2f}%</b></p>

 <div class="card"><h2>Forecast</h2>
  <table><tr><th>Horizon</th><th>Direction</th><th>Conf</th><th>Target</th>
   <th>Move</th></tr>{rows}</table></div>

 <div class="card"><h2>Factor drivers ({longest.horizon})</h2>
  <table><tr><th>Factor</th><th>Tilt (← dovish · hawkish →)</th>
   <th class='num'>Score</th><th class='num'>Contrib</th></tr>{frows}</table>
  <p class="muted">Red = upward yield pressure (bond bearish). Green = downward.</p>
 </div>
 {fomc_block}
 <p class="foot">TraceYield · research tool, not investment advice ·
   generated {run_date:%Y-%m-%d}</p>
</div></body></html>"""


def save_html(html: str, run_date: date | None = None) -> Path:
    run_date = run_date or date.today()
    rdir = DATA / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"report_{run_date:%Y%m%d}.html").write_text(html, encoding="utf-8")
    latest = rdir / "latest.html"  # stable path the daily job overwrites
    latest.write_text(html, encoding="utf-8")
    return latest
