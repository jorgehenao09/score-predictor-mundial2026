"""Panel HTML local: genera data/panel.html con las predicciones de los
próximos partidos y lo abre en el navegador. Sin servidor, sin dependencias.
"""

import html
import os
from datetime import datetime, timezone

from . import store
from .venues import VENUES

PANEL_PATH = os.path.join(store.BASE_DIR, "data", "panel.html")

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; margin: 0; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0d1117;
       color: #e6edf3; padding: 24px; max-width: 980px; margin: 0 auto; }
h1 { font-size: 22px; margin-bottom: 4px; }
.sub { color: #8b949e; font-size: 13px; margin-bottom: 20px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 10px;
        padding: 16px 18px; margin-bottom: 14px; }
.head { display: flex; justify-content: space-between; align-items: baseline;
        flex-wrap: wrap; gap: 6px; }
.teams { font-size: 17px; font-weight: 600; }
.meta { color: #8b949e; font-size: 12px; }
.score { font-size: 26px; font-weight: 700; color: #58a6ff; margin: 8px 0 2px; }
.alts { color: #8b949e; font-size: 12px; margin-bottom: 10px; }
.bars { display: grid; grid-template-columns: 110px 1fr 52px; gap: 4px 10px;
        align-items: center; font-size: 13px; margin-bottom: 4px; }
.bar { background: #21262d; border-radius: 4px; height: 14px; overflow: hidden; }
.bar > div { height: 100%; border-radius: 4px; }
.h .bar > div { background: #3fb950; }
.d .bar > div { background: #d29922; }
.a .bar > div { background: #f85149; }
.mkt { color: #8b949e; font-size: 11px; }
.conf { display: inline-block; padding: 1px 8px; border-radius: 10px;
        font-size: 11px; font-weight: 600; }
.ALTA { background: #1f6f3f; } .MEDIA { background: #7a5b14; }
.BAJA { background: #6e2228; }
details { margin-top: 8px; font-size: 12.5px; color: #c9d1d9; }
summary { cursor: pointer; color: #8b949e; }
details li { margin: 4px 0 4px 16px; }
.diverge { color: #d29922; font-weight: 600; }
"""


def _bar(cls, label, p, pm):
    mkt = f'<span class="mkt">mercado {pm:.0%}</span>' if pm is not None else ""
    return (f'<div class="bars {cls}"><span>{html.escape(label)} {mkt}</span>'
            f'<div class="bar"><div style="width:{p * 100:.1f}%"></div></div>'
            f'<span>{p:.1%}</span></div>')


def _card(pred):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    v = VENUES.get(pred.get("city", ""))
    venue = f" · {html.escape(v[0])}, {html.escape(pred['city'])}" if v else ""
    alts = "  ·  ".join(f"{s} ({p:.1%})" for s, p in pred.get("top_scores", [])[1:4])
    mkt_note = ""
    if "market_p_home" in pred:
        edge = max(abs(pred["p_home"] - pred["market_p_home"]),
                   abs(pred["p_draw"] - pred["market_p_draw"]),
                   abs(pred["p_away"] - pred["market_p_away"]))
        n = pred.get("n_books", "?")
        note = (f'<span class="diverge">divergencia máx {edge * 100:.0f} pts</span>'
                if edge >= 0.07 else f"divergencia máx {edge * 100:.0f} pts")
        mkt_note = f'<span class="meta">vs mercado ({n} casas): {note}</span>'
    factors = "".join(f"<li>{html.escape(f)}</li>" for f in pred.get("factors", []))
    return f"""
<div class="card">
  <div class="head">
    <span class="teams">{h} vs {a}</span>
    <span class="meta">{pred['match_date']}{venue}</span>
  </div>
  <div class="score">{pred['top_score']} <span class="meta">({pred['top_score_prob']:.1%})</span>
    <span class="conf {pred['confidence']}">{pred['confidence']}</span></div>
  <div class="alts">Alternativas: {alts}</div>
  {_bar('h', h, pred['p_home'], pred.get('market_p_home'))}
  {_bar('d', 'Empate', pred['p_draw'], pred.get('market_p_draw'))}
  {_bar('a', a, pred['p_away'], pred.get('market_p_away'))}
  <div style="margin-top:6px" class="meta">Goles esperados:
    {pred['exp_home']:.2f} – {pred['exp_away']:.2f} {mkt_note}</div>
  <details><summary>Factores</summary><ul>{factors}</ul></details>
</div>"""


def render(con, preds, data_version) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cards = "\n".join(_card(p) for p in preds)
    dv = " · ".join(f"{k}: {v}" for k, v in data_version.items())
    n_snap = con.execute(
        "SELECT COUNT(DISTINCT fetched_at) FROM odds_snapshots").fetchone()[0]
    used = store.requests_this_month(con, "odds_api")
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Score Predictor — Mundial 2026</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style></head><body>
<h1>⚽ Score Predictor — Mundial 2026</h1>
<div class="sub">Generado: {now} &nbsp;·&nbsp; {dv}<br>
Snapshots de cuotas acumulados: {n_snap} · The Odds API: {used}/500 créditos este mes<br>
Regenerar: <code>.venv/bin/python -m predictor panel</code></div>
{cards}
</body></html>"""
    os.makedirs(os.path.dirname(PANEL_PATH), exist_ok=True)
    with open(PANEL_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    return PANEL_PATH
