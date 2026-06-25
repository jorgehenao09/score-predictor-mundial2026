# Dashboard "Score Predictor" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el panel HTML actual en un dashboard de 3 pestañas (Próximos · Aciertos · Modelo), tema claro data-dense, con calibración escalable por competición.

**Architecture:** HTML estático autocontenido generado por `panel.py` (orquestador). Dos módulos nuevos: `panel_style.py` (tokens CSS) y `panel_data.py` (cálculos de aciertos y calibración). Las predicciones de "Próximos" ya las arma `cli.cmd_panel` y se pasan a `panel.render`. Tabs con JS mínimo embebido.

**Tech Stack:** Python 3.12 (stdlib + numpy ya presente), HTML/CSS embebido, sin frameworks ni servidor. Fuentes Google con fallback system-ui.

**Convención del proyecto (IMPORTANTE):** sin tests formales (CLAUDE.md). La verificación de cada tarea es un chequeo inline (`python -c ...`) o generar `panel.html` e inspeccionar. Fuente de verdad de diseño: `design-system/score-predictor/MASTER.md`.

---

### Task 1: Módulo de estilos (design tokens + componentes)

**Files:**
- Create: `predictor/panel_style.py`

- [ ] **Step 1: Crear `panel_style.py` con los tokens y estilos de componentes**

```python
"""CSS del dashboard: design tokens (tema claro, data-dense) + componentes.
Fuente de verdad: design-system/score-predictor/MASTER.md. Sin frameworks."""

FONTS = ("https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700"
         "&family=Fira+Sans:wght@400;500;600;700&display=swap")

CSS = """
:root{
  --bg:#F8FAFC; --surface:#FFFFFF; --surface-2:#F1F5F9; --border:#E2E8F0;
  --text:#0F172A; --text-muted:#475569; --text-faint:#94A3B8;
  --model:#2563EB; --market:#B45309; --final:#15803D; --value:#CA8A04;
  --hit:#16A34A; --miss:#DC2626; --draw:#64748B;
  --conf-alta:#16A34A; --conf-media:#D97706; --conf-baja:#DC2626;
  --model-fill:#3B82F6; --market-fill:#F59E0B;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px; --sp-6:32px;
  --r-sm:6px; --r-md:10px; --r-lg:14px;
  --mono:'Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:'Fira Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
  line-height:1.5;font-size:15px}
.wrap{max-width:1100px;margin:0 auto;padding:var(--sp-5)}
h1{font-size:22px;margin:0 0 var(--sp-1)}
.sub{color:var(--text-muted);font-size:13px;margin-bottom:var(--sp-5)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* tab-bar */
.tabs{display:flex;gap:var(--sp-1);background:var(--surface-2);
  padding:var(--sp-1);border-radius:var(--r-md);width:fit-content;
  margin-bottom:var(--sp-5)}
.tab{border:0;background:transparent;color:var(--text-muted);cursor:pointer;
  font-family:var(--sans);font-size:14px;font-weight:600;
  padding:var(--sp-2) var(--sp-4);border-radius:var(--r-sm);
  transition:background .2s,color .2s}
.tab:hover{color:var(--text)}
.tab[aria-selected="true"]{background:var(--surface);color:var(--text);
  box-shadow:0 1px 2px rgba(15,23,42,.08)}
.tab:focus-visible{outline:2px solid var(--model);outline-offset:2px}
.panel[hidden]{display:none}

/* match-card */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:var(--sp-4)}
.card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:var(--sp-4);
  box-shadow:0 1px 3px rgba(15,23,42,.06)}
.card .head{font-weight:600;margin-bottom:var(--sp-1)}
.card .meta{color:var(--text-muted);font-size:12px}
.pick{font-family:var(--mono);font-weight:600}
.pick.gp{color:var(--final)} .pick.rem{color:var(--value)}

/* bar-1x2 */
.bars{margin:var(--sp-3) 0;display:flex;flex-direction:column;gap:var(--sp-1)}
.bars .row{display:grid;grid-template-columns:64px 1fr 44px;align-items:center;
  gap:var(--sp-2);font-size:12px}
.track{height:8px;background:var(--surface-2);border-radius:99px;overflow:hidden}
.fill{height:100%;border-radius:99px}
.fill.model{background:var(--model-fill)} .fill.market{background:var(--market-fill)}
.fill.final{background:var(--final)}

/* badge */
.badge{display:inline-block;font-size:11px;font-weight:600;
  padding:2px var(--sp-2);border-radius:99px;border:1px solid currentColor}
.badge.alta{color:var(--conf-alta)} .badge.media{color:var(--conf-media)}
.badge.baja{color:var(--conf-baja)}
.badge.hit{color:var(--hit)} .badge.miss{color:var(--miss)}

/* kpi-tile */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:var(--sp-4);margin-bottom:var(--sp-5)}
.kpi{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:var(--sp-4)}
.kpi .v{font-family:var(--mono);font-size:32px;font-weight:700;line-height:1}
.kpi .l{color:var(--text-muted);font-size:12px;margin-top:var(--sp-1)}

/* tables */
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden}
th,td{padding:var(--sp-2) var(--sp-3);text-align:left;
  border-bottom:1px solid var(--border)}
th{color:var(--text-muted);font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.03em}
tbody tr:hover{background:var(--surface-2)}
tbody tr:last-child td{border-bottom:0}
td.n{font-family:var(--mono);font-variant-numeric:tabular-nums}

.explain{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:var(--sp-5);margin-bottom:var(--sp-5);
  color:var(--text-muted)}
.explain b{color:var(--text)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""
```

- [ ] **Step 2: Verificar que el módulo importa y trae los tokens clave**

Run: `.venv/bin/python -c "from predictor.panel_style import CSS,FONTS; assert '--model:#2563EB' in CSS and '--bg:#F8FAFC' in CSS and 'Fira+Code' in FONTS; print('panel_style OK', len(CSS), 'chars')"`
Expected: `panel_style OK <n> chars`

- [ ] **Step 3: Commit**

```bash
git add predictor/panel_style.py
git commit -m "panel: design tokens y estilos de componentes (tema claro)"
```

---

### Task 2: Datos de calibración por competición

**Files:**
- Create: `predictor/panel_data.py`

- [ ] **Step 1: Crear `panel_data.py` con `calibration()`**

```python
"""Cálculos del dashboard, sin HTML: aciertos y calibración por competición.
Reutiliza la lógica de `precision` y el estado vivo (fit, learning, params)."""
import numpy as np

from . import golpredictor as gp
from . import learning, store
from .predict import brier, goal_uplift, rps

# Registro de competiciones: para escalar, añadir una entrada y su snapshot.
# Hoy solo Mundial 2026 (su calibración sale del estado vivo del modelo).
BASE = {  # defaults universales del modelo (no se recalculan)
    "xi": "0.0005", "rho": "—", "local": "—", "blend": "0.50", "uplift": "1.00",
    "autotune": "—",
}


def calibration(con):
    """(base, competiciones) para la tabla comparativa de la pestaña Modelo.
    Cada competición = una columna; hoy solo WC2026 desde el fit/learning vivos."""
    fit = con.execute(
        "SELECT xi, rho, home_adv FROM fits ORDER BY id DESC LIMIT 1").fetchone()
    xi, rho, ha = fit if fit else (0.0005, 0.0, 0.0)
    blend, _ = learning.current_blend(con)
    wc2026 = {
        "xi": f"{xi:.4f}",
        "rho": f"{rho:+.3f}",
        "local": f"+{(np.exp(ha) - 1) * 100:.0f}% (por sede)",
        "blend": f"{blend:.2f} (aprendido)",
        "uplift": f"{goal_uplift():.2f}",
        "autotune": "mezcla sí · resto vigilado",
    }
    competitions = [{"id": "wc2026", "name": "Mundial 2026", "params": wc2026}]
    return BASE, competitions
```

- [ ] **Step 2: Verificar que `calibration` corre y trae valores vivos**

Run: `.venv/bin/python -c "from predictor import store, panel_data; b,c=panel_data.calibration(store.connect()); print('BASE',b['xi']); print('WC2026',c[0]['params'])"`
Expected: imprime `BASE 0.0005` y el dict de WC2026 con xi/rho/local/blend/uplift reales.

- [ ] **Step 3: Commit**

```bash
git add predictor/panel_data.py
git commit -m "panel_data: snapshot de calibracion por competicion"
```

---

### Task 3: Datos de aciertos (métricas + historial)

**Files:**
- Modify: `predictor/panel_data.py`

- [ ] **Step 1: Añadir `_resolved_rows`, `_closing_odds` y `accuracy()` a `panel_data.py`**

```python
def _resolved_rows(con):
    return con.execute(
        """SELECT p.home, p.away, p.match_date, p.p_home, p.p_draw, p.p_away,
                  p.top_score, m.home_score, m.away_score, p.gp_score
           FROM predictions p JOIN matches m
             ON m.home=p.home AND m.away=p.away AND m.date=p.match_date
           WHERE m.home_score IS NOT NULL
             AND p.id IN (SELECT MAX(id) FROM predictions
                          WHERE substr(created_at,1,10) <= match_date
                          GROUP BY home, away, match_date)
           ORDER BY p.match_date""").fetchall()


def _median(xs):
    xs = sorted(x for x in xs if x)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _closing_odds(con, home, away, outcome):
    """Cuota mediana de cierre para el outcome (0 local,1 empate,2 visita)."""
    col = ("home_odds", "draw_odds", "away_odds")[outcome]
    rows = con.execute(
        f"""SELECT {col} FROM odds_snapshots WHERE home=? AND away=?
            AND fetched_at=(SELECT MAX(fetched_at) FROM odds_snapshots
                            WHERE home=? AND away=? AND fetched_at<=commence_time)""",
        (home, away, home, away)).fetchall()
    return _median([r[0] for r in rows])


def accuracy(con):
    """Métricas (escalables, sin posición de polla) + historial resuelto.
    Devuelve dict: hits_1x2%, exact%, gp_points, rps, roi%, n, history[]."""
    rows = _resolved_rows(con)
    if not rows:
        return {"n": 0, "history": []}
    n = len(rows)
    hits = exact = 0
    rps_sum = 0.0
    modal_pts = 0
    staked = ret = 0
    STAKE = 10000
    history = []
    for (h, a, d, ph, pd, pa, ts, hs, as_, gps) in rows:
        outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
        probs = (ph, pd, pa)
        verdict = max(range(3), key=lambda i: probs[i])
        ok = verdict == outcome
        hits += ok
        rps_sum += rps(probs, outcome)
        is_exact = ts == f"{hs}-{as_}"
        exact += is_exact
        ko = gp.is_knockout(d)
        modal = tuple(map(int, ts.split("-")))
        pts = gp.points(modal, (hs, as_), ko)
        modal_pts += pts
        o = _closing_odds(con, h, a, verdict)
        if o:
            staked += STAKE
            ret += STAKE * o if ok else 0
        vlabel = (h if verdict == 0 else a if verdict == 2 else "Empate")
        history.append({"date": d, "home": h, "away": a, "verdict": vlabel,
                        "real": f"{hs}-{as_}", "ok": ok, "pts": pts})
    roi = ((ret - staked) / staked * 100) if staked else None
    return {
        "n": n,
        "hits_1x2": hits / n * 100,
        "exact": exact / n * 100,
        "gp_points": modal_pts,
        "rps": rps_sum / n,
        "roi": roi,
        "history": list(reversed(history)),
    }
```

- [ ] **Step 2: Verificar `accuracy` con datos reales**

Run: `.venv/bin/python -c "from predictor import store, panel_data; r=panel_data.accuracy(store.connect()); print('n',r['n'],'1X2',round(r['hits_1x2']),'exact',round(r['exact']),'pts',r['gp_points'],'roi',r['roi'])"`
Expected: imprime números sanos (p.ej. `n 30 1X2 64 exact 13 pts <n> roi <n>`); sin excepción.

- [ ] **Step 3: Commit**

```bash
git add predictor/panel_data.py
git commit -m "panel_data: metricas de aciertos + historial (sin posicion de polla)"
```

---

### Task 4: Reescribir `panel.py` — scaffolding de pestañas + tab Próximos

**Files:**
- Modify: `predictor/panel.py` (reescritura completa; hoy 111 líneas)

- [ ] **Step 1: Reescribir `panel.py` con el scaffolding, JS de tabs y el render de "Próximos"**

```python
"""Dashboard HTML estático: 3 pestañas (Próximos · Aciertos · Modelo).
Autocontenido, sin servidor. Estilos en panel_style; datos en panel_data."""
import html
import os

from . import panel_data, store
from .panel_style import CSS, FONTS
from .venues import venue_info

PANEL_PATH = os.path.join(store.BASE_DIR, "data", "panel.html")

TABS_JS = """
<script>
document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click',function(){
    document.querySelectorAll('.tab').forEach(function(x){
      x.setAttribute('aria-selected', x===t ? 'true':'false');});
    document.querySelectorAll('.panel').forEach(function(p){
      p.hidden = p.id !== t.dataset.target;});
  });
});
</script>
"""


def _bar(cls, label, p):
    return (f'<div class="row"><span>{html.escape(label)}</span>'
            f'<div class="track"><div class="fill {cls}" '
            f'style="width:{p * 100:.0f}%"></div></div>'
            f'<span class="num">{p * 100:.0f}%</span></div>')


def _card(pred):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    v = venue_info(pred.get("city", ""))
    venue = f' · {html.escape(v[0])}' if v else ""
    conf = pred["confidence"].lower()
    alts = "  ".join(f'{html.escape(s)} <span class="meta">{p:.0%}</span>'
                     for s, p in pred.get("top_scores", [])[1:4])
    rem = ""
    c = pred.get("contrarian")
    if c:
        rem = (f'<div>🎲 <span class="pick rem">remontada {html.escape(c["score"])}'
               f'</span> <span class="meta">(mercado infravalora '
               f'+{c["edge"]:.0%})</span></div>')
    bars = ""
    if "market_p_home" in pred:
        bars = ('<div class="bars">'
                + _bar("model", f"{pred['home'][:10]} modelo", pred["model_p_home"])
                + _bar("market", "mercado", pred["market_p_home"])
                + _bar("final", "final", pred["p_home"]) + '</div>')
    factors = "".join(f"<li>{html.escape(f)}</li>"
                      for f in pred.get("factors", []))
    return f"""<div class="card">
  <div class="head">{h} vs {a}</div>
  <div class="meta">{pred['match_date']}{venue}</div>
  <div style="margin-top:8px">🎯 <span class="pick gp">golpredictor
    {html.escape(pred.get('gp_score', pred['top_score']))}</span>
    <span class="meta">· más probable {html.escape(pred['top_score'])}</span></div>
  {rem}
  <div class="meta" style="margin-top:6px">Alternativas: {alts}</div>
  {bars}
  <div style="margin-top:8px"><span class="badge {conf}">confianza
    {html.escape(pred['confidence'])}</span></div>
  <ul class="meta" style="margin:8px 0 0;padding-left:18px">{factors}</ul>
</div>"""


def _tab_proximos(preds):
    cards = "\n".join(_card(p) for p in preds) or \
        '<p class="meta">Sin partidos próximos.</p>'
    return f'<section class="panel" id="proximos"><div class="grid">{cards}</div></section>'
```

- [ ] **Step 2: Verificación parcial (se completa en Task 7); chequear que importa**

Run: `.venv/bin/python -c "import predictor.panel as p; print('imports OK', bool(p.TABS_JS), bool(p._tab_proximos))"`
Expected: `imports OK True True` (puede faltar `render`; se añade en Task 7).

- [ ] **Step 3: Commit**

```bash
git add predictor/panel.py
git commit -m "panel: scaffolding de pestanas + tab Proximos restyled"
```

---

### Task 5: Render de la pestaña "Aciertos"

**Files:**
- Modify: `predictor/panel.py`

- [ ] **Step 1: Añadir `_tab_aciertos` a `panel.py`**

```python
def _kpi(value, label):
    return f'<div class="kpi"><div class="v num">{value}</div><div class="l">{label}</div></div>'


def _tab_aciertos(acc):
    if not acc["n"]:
        return ('<section class="panel" id="aciertos" hidden>'
                '<p class="meta">Aún no hay partidos resueltos.</p></section>')
    roi = f"{acc['roi']:+.0f}%" if acc["roi"] is not None else "—"
    kpis = (
        _kpi(f"{acc['hits_1x2']:.0f}%", "1X2 acertado")
        + _kpi(f"{acc['exact']:.0f}%", "Marcador exacto")
        + _kpi(str(acc["gp_points"]), "Puntos golpredictor")
        + _kpi(f"{acc['rps']:.3f}", "RPS (calidad, menor mejor)")
        + _kpi(roi, "ROI ilustrativo*"))
    trs = ""
    for r in acc["history"]:
        badge = ('<span class="badge hit">✓</span>' if r["ok"]
                 else '<span class="badge miss">✗</span>')
        trs += (f'<tr><td class="n">{html.escape(r["date"])}</td>'
                f'<td>{html.escape(r["home"])} vs {html.escape(r["away"])}</td>'
                f'<td>{html.escape(r["verdict"])}</td>'
                f'<td class="n">{html.escape(r["real"])}</td>'
                f'<td>{badge}</td><td class="n">{r["pts"]}</td></tr>')
    return f"""<section class="panel" id="aciertos" hidden>
  <div class="kpis">{kpis}</div>
  <p class="meta">El modelo es fuerte prediciendo <b>quién gana</b>; el
    <b>marcador exacto</b> es intrínsecamente difícil. *ROI ilustrativo: apostar
    al veredicto a cuota de cierre; no es consejo de apuesta.</p>
  <table><thead><tr><th>Fecha</th><th>Partido</th><th>Veredicto</th>
    <th>Real</th><th>✓/✗</th><th>Pts</th></tr></thead><tbody>{trs}</tbody></table>
</section>"""
```

- [ ] **Step 2: Verificar el render con datos reales**

Run: `.venv/bin/python -c "from predictor import store, panel, panel_data; print('<table' in panel._tab_aciertos(panel_data.accuracy(store.connect())))"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add predictor/panel.py
git commit -m "panel: tab Aciertos (KPIs + historial)"
```

---

### Task 6: Render de la pestaña "Modelo y calibración"

**Files:**
- Modify: `predictor/panel.py`

- [ ] **Step 1: Añadir `_tab_modelo` a `panel.py`**

```python
PARAMS = [("xi", "xi (decaimiento temporal)"), ("rho", "rho (marcadores bajos)"),
          ("local", "ventaja local"), ("blend", "mezcla modelo↔mercado"),
          ("uplift", "goal uplift"), ("autotune", "¿auto-ajusta?")]


def _tab_modelo(base, competitions):
    cols = "".join(f"<th>{html.escape(c['name'])}</th>" for c in competitions)
    rows = ""
    for key, label in PARAMS:
        cells = "".join(f'<td class="n">{html.escape(str(c["params"][key]))}</td>'
                        for c in competitions)
        rows += (f'<tr><td>{html.escape(label)}</td>'
                 f'<td class="n">{html.escape(str(base[key]))}</td>{cells}</tr>')
    return f"""<section class="panel" id="modelo" hidden>
  <div class="explain">
    <b>El modelo base (universal, no cambia entre competiciones).</b><br>
    Dixon-Coles ponderado por tiempo (ataque/defensa por selección, corrección
    rho de marcadores bajos) · prior Elo para selecciones con poca muestra ·
    de-vigging del mercado por método de Shin · marcador óptimo-EV para
    golpredictor · y una <b>mezcla modelo↔mercado autoaprendida</b> que minimiza
    el RPS sobre lo ya jugado.
  </div>
  <table><thead><tr><th>Parámetro</th><th>BASE</th>{cols}</tr></thead>
    <tbody>{rows}</tbody></table>
  <p class="meta" style="margin-top:12px">Cada competición que se añada al
    registro aparece como una columna nueva. La fila BASE son los defaults
    universales del modelo.</p>
</section>"""
```

- [ ] **Step 2: Verificar el render**

Run: `.venv/bin/python -c "from predictor import store, panel, panel_data; b,c=panel_data.calibration(store.connect()); print('Mundial 2026' in panel._tab_modelo(b,c))"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add predictor/panel.py
git commit -m "panel: tab Modelo (base + tabla comparativa de calibracion)"
```

---

### Task 7: Ensamblar `render()` y verificación visual final

**Files:**
- Modify: `predictor/panel.py`

- [ ] **Step 1: Añadir `render()` que arma la página completa con las 3 pestañas**

```python
def render(con, preds, data_version) -> str:
    from .store import now_iso
    acc = panel_data.accuracy(con)
    base, comps = panel_data.calibration(con)
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Score Predictor · Mundial 2026</title>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style></head><body><div class="wrap">
<h1>⚽ Score Predictor · Mundial 2026</h1>
<div class="sub">Generado {now_iso()} · {len(preds)} partidos próximos</div>
<div class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-target="proximos">Próximos</button>
  <button class="tab" role="tab" aria-selected="false" data-target="aciertos">Aciertos</button>
  <button class="tab" role="tab" aria-selected="false" data-target="modelo">Modelo</button>
</div>
{_tab_proximos(preds)}
{_tab_aciertos(acc)}
{_tab_modelo(base, comps)}
</div>{TABS_JS}</body></html>"""
    with open(PANEL_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    return PANEL_PATH
```

- [ ] **Step 2: Generar el panel real y comprobar estructura**

Run: `.venv/bin/python -m predictor panel 5 --no-abrir && .venv/bin/python -c "h=open('data/panel.html',encoding='utf-8').read(); assert all(x in h for x in ['role=\"tablist\"','id=\"proximos\"','id=\"aciertos\"','id=\"modelo\"','--model:#2563EB']); print('panel.html OK', len(h), 'bytes')"`

(Si `cmd_panel` no acepta `--no-abrir`, usar `PREDICTOR_NO_OPEN=1` o quitar el flag; ver `cli.py:cmd_panel`. Si el flag no existe, añadirlo en este paso a `cli.py` argparse del subcomando `panel`.)

Expected: `panel.html OK <n> bytes`

- [ ] **Step 3: Revisión visual + accesibilidad**

Abrir `data/panel.html` en el navegador y verificar el checklist:
- Las 3 pestañas cambian al hacer clic; foco visible con teclado (Tab).
- Contraste legible (texto oscuro sobre claro); barras modelo(azul)/mercado(ámbar)/final(verde).
- Sin scroll horizontal a 375px (responsive).
- `prefers-reduced-motion` respetado (sin animaciones si está activo).

- [ ] **Step 4: Commit**

```bash
git add predictor/panel.py predictor/cli.py
git commit -m "panel: ensamblar dashboard de 3 pestanas (render completo)"
```

---

## Self-Review

**Spec coverage:**
- Arquitectura (panel.py + panel_data.py + panel_style.py) → Tasks 1–7. ✓
- Tab Próximos (🎯/🎲/barras/confianza/factores) → Task 4. ✓
- Tab Aciertos (KPIs sin posición de polla + historial) → Tasks 3, 5. ✓
- Tab Modelo (base + tabla comparativa escalable) → Tasks 2, 6. ✓
- Tokens/tema claro → Task 1 (deriva de MASTER.md). ✓
- Escalado por competición → `panel_data.calibration` registro `competitions` (Task 2) + nota en Task 6. ✓
- Accesibilidad → Task 7 Step 3 + CSS (focus-visible, reduced-motion). ✓

**Placeholder scan:** sin TBD/TODO; todo el código está completo. El único condicional ("si `--no-abrir` no existe, añadirlo") es una instrucción concreta verificable contra `cli.py`, no un placeholder de código.

**Type consistency:** `accuracy()` devuelve claves `hits_1x2/exact/gp_points/rps/roi/n/history` usadas igual en `_tab_aciertos`. `calibration()` devuelve `(base, competitions)` con `params[key]` para cada `key` de `PARAMS`; las claves de `BASE`/`wc2026` coinciden con `PARAMS` (xi, rho, local, blend, uplift, autotune). `_card` usa claves de `predict_match` ya existentes (gp_score, top_scores, contrarian, market_p_home, confidence, factors). ✓
