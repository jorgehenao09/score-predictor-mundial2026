# Dashboard v2 (cards ricas + modal de detalle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cards de "Próximos" menos planas (barra 1X2 apilada, chips, confianza con color, clicables) y un modal de detalle al hacer clic (matriz de goles heatmap + peso de factores + mezcla).

**Architecture:** `predict_match` adjunta un `breakdown` (descomposición log-λ, matriz 6×6, probs, peso de mezcla, celdas a resaltar). `panel_style.py` añade CSS de los componentes nuevos. `panel.py` rediseña la card y arma un modal oculto por partido, mostrado con JS mínimo (mismo patrón que las tabs).

**Tech Stack:** Python 3.12 (numpy ya presente), HTML/CSS embebido, JS mínimo. Sin servidor ni frameworks. Fuente de verdad de diseño: `design-system/score-predictor/MASTER.md`.

**Convención (IMPORTANTE):** sin tests formales. Verificación = chequeo inline (`.venv/bin/python -c ...`) o generar `data/panel.html` e inspeccionar. Comentarios en español.

---

### Task 1: `breakdown` en `predict_match`

**Files:**
- Modify: `predictor/predict.py` (dentro de `predict_match`, justo antes del `return {`)

- [ ] **Step 1: Localizar el `return {` de `predict_match`.** Run:
`.venv/bin/python -c "import re; s=open('predictor/predict.py').read(); i=s.index('    return {\n        \"match_date\"'); print(s[i-200:i])"`
Expected: imprime las líneas previas al return (incluyen `gp_score`, `p_home`, etc.), confirmando que `lh, la, ah, da, aa, dh, ha_home, ha_away, uplift, M, mp, market_part, blend_w, p_home, p_draw, p_away, ti, tj, gi, gj` están en alcance.

- [ ] **Step 2: Insertar la construcción de `breakdown` inmediatamente antes de `return {`** (mismo nivel de indentación, 4 espacios):

```python
    # --- descomposición para el modal de detalle del dashboard
    _ht = [("Base", float(fit["mu"])), (f"Ataque {home}", float(ah)),
           (f"Defensa {away}", float(-da))]
    if ha_home:
        _ht.append(("Ventaja local", float(ha_home)))
    _ht.append(("Uplift goles", float(np.log(uplift))))
    _at = [("Base", float(fit["mu"])), (f"Ataque {away}", float(aa)),
           (f"Defensa {home}", float(-dh))]
    if ha_away:
        _at.append(("Ventaja local", float(ha_away)))
    _at.append(("Uplift goles", float(np.log(uplift))))
    _mkt = None
    if market_part and market_part.get("market_p_home") is not None:
        _mkt = (market_part["market_p_home"], market_part["market_p_draw"],
                market_part["market_p_away"])
    breakdown = {
        "lh": float(lh), "la": float(la),
        "home_terms": _ht, "away_terms": _at,
        "matrix6": [[float(M[i, j]) for j in range(6)] for i in range(6)],
        "model_probs": (mp["h"], mp["d"], mp["a"]),
        "market_probs": _mkt,
        "final_probs": (p_home, p_draw, p_away),
        "blend_w": float(blend_w) if M_mkt is not None else 0.0,
        "gp_cell": (gi, gj), "modal_cell": (ti, tj),
    }
```

- [ ] **Step 3: Añadir `breakdown` al dict que retorna `predict_match`.** En el `return {`, junto a `"gp_score": ...`, agregar la línea:
```python
        "breakdown": breakdown,
```

- [ ] **Step 4: Verificar.** Run:
`.venv/bin/python -c "from predictor import store, predict as P; from predictor.cli import ensure_fit, find_fixtures; con=store.connect(); fit,_=ensure_fit(con); fx=find_fixtures(con,limit=1)[0]; b=P.predict_match(con,fit,fx)['breakdown']; import numpy as np; assert abs(sum(v for _,v in b['home_terms'][:-1])+0) and len(b['matrix6'])==6 and len(b['matrix6'][0])==6; print('breakdown OK · lh',round(b['lh'],2),'terms',len(b['home_terms']),'w',round(b['blend_w'],2),'gp',b['gp_cell'])"`
Expected: `breakdown OK · lh <n> terms <n> w <n> gp (<i>, <j>)`, sin excepción.

- [ ] **Step 5: Commit.**
```bash
git add predictor/predict.py
git commit -m "predict: breakdown (descomposicion log-lambda + matriz) para el modal"
```

---

### Task 2: CSS de los componentes v2

**Files:**
- Modify: `predictor/panel_style.py` (añadir al final del string `CSS`, antes de las comillas de cierre `"""`)

- [ ] **Step 1: Añadir este bloque al final de la constante `CSS`** (justo antes del `"""` que la cierra):

```css

/* === v2: card clicable, barra apilada, chips, modal, heatmap === */
.card{cursor:pointer;transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(15,23,42,.10)}
.card .teams{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-2)}

.stack{display:flex;height:14px;border-radius:99px;overflow:hidden;margin:var(--sp-2) 0 4px}
.stack > span{display:block}
.stack .s-home{background:var(--model-fill)}
.stack .s-draw{background:var(--draw)}
.stack .s-away{background:var(--market-fill)}
.stack-lbl{display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted)}

.chips{display:flex;flex-wrap:wrap;gap:var(--sp-1);margin-top:var(--sp-2)}
.chip{font-family:var(--mono);font-size:12px;font-weight:600;padding:2px 8px;
  border-radius:99px;background:var(--surface-2);color:var(--text)}
.chip.gp{background:rgba(21,128,61,.12);color:var(--final)}
.chip.rem{background:rgba(202,138,4,.14);color:var(--value)}
.chip.val{background:rgba(37,99,235,.12);color:var(--model)}

/* modal */
.backdrop{position:fixed;inset:0;background:rgba(15,23,42,.55);
  display:flex;align-items:flex-start;justify-content:center;padding:var(--sp-5);
  overflow:auto;z-index:50}
.backdrop[hidden]{display:none}
.modal{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);max-width:720px;width:100%;padding:var(--sp-5);
  box-shadow:0 20px 50px rgba(15,23,42,.25)}
.modal h2{font-size:18px;margin:0 0 var(--sp-4)}
.modal .x{float:right;border:0;background:var(--surface-2);cursor:pointer;
  width:32px;height:32px;border-radius:8px;font-size:16px;color:var(--text-muted)}
.modal .x:hover{color:var(--text)}
.modal h3{font-size:12px;text-transform:uppercase;letter-spacing:.03em;
  color:var(--text-muted);margin:var(--sp-5) 0 var(--sp-2)}

/* heatmap matriz de goles */
.heat{display:grid;grid-template-columns:auto repeat(6,1fr);gap:3px;font-size:11px;
  font-family:var(--mono)}
.heat .hd{color:var(--text-faint);text-align:center;align-self:center}
.heat .cell{aspect-ratio:1;border-radius:4px;border:2px solid transparent;
  display:flex;align-items:center;justify-content:center;color:var(--text)}
.heat .cell.gp{border-color:var(--final)}
.heat .cell.modal{border-color:var(--model)}

/* barras de peso de factores (divergentes) */
.fbar{display:grid;grid-template-columns:160px 1fr 56px;align-items:center;
  gap:var(--sp-2);font-size:12px;margin:3px 0}
.fbar .track2{height:10px;background:var(--surface-2);border-radius:4px;position:relative}
.fbar .pos,.fbar .neg{position:absolute;top:0;height:100%;border-radius:4px}
.fbar .pos{left:50%;background:var(--model)}
.fbar .neg{right:50%;background:var(--miss)}
.fbar .v{font-family:var(--mono);text-align:right}
```

- [ ] **Step 2: Verificar.** Run:
`.venv/bin/python -c "from predictor.panel_style import CSS; assert '.backdrop' in CSS and '.stack' in CSS and '.heat ' in CSS and '.fbar' in CSS; print('CSS v2 OK', len(CSS))"`
Expected: `CSS v2 OK <n>`

- [ ] **Step 3: Commit.**
```bash
git add predictor/panel_style.py
git commit -m "panel: CSS v2 (card clicable, barra apilada, chips, modal, heatmap)"
```

---

### Task 3: Rediseñar `_card` (Próximos)

**Files:**
- Modify: `predictor/panel.py` (reemplazar la función `_card` completa)

- [ ] **Step 1: Reemplazar la función `_card` actual por esta** (acepta `idx` para enlazar con su modal):

```python
def _stack(ph, pd, pa, home, away):
    return (
        '<div class="stack">'
        f'<span class="s-home" style="width:{ph*100:.0f}%"></span>'
        f'<span class="s-draw" style="width:{pd*100:.0f}%"></span>'
        f'<span class="s-away" style="width:{pa*100:.0f}%"></span></div>'
        f'<div class="stack-lbl"><span>{html.escape(home)} {ph:.0%}</span>'
        f'<span>Empate {pd:.0%}</span>'
        f'<span>{html.escape(away)} {pa:.0%}</span></div>')


def _card(pred, idx):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    v = venue_info(pred.get("city", ""))
    venue = f' · {html.escape(v[0])}' if v else ""
    conf = pred["confidence"].lower()
    chips = (f'<span class="chip gp">🎯 {html.escape(pred.get("gp_score", pred["top_score"]))}</span>'
             f'<span class="chip" title="más probable">≈ {html.escape(pred["top_score"])}</span>')
    c = pred.get("contrarian")
    if c:
        chips += (f'<span class="chip rem">🎲 {html.escape(c["score"])}</span>'
                  f'<span class="chip val">⚡ valor +{c["edge"]:.0%}</span>')
    bars = (_stack(pred["p_home"], pred["p_draw"], pred["p_away"], pred["home"],
                   pred["away"]) if "p_home" in pred else "")
    return f"""<div class="card" data-detail="d-{idx}" tabindex="0" role="button"
     aria-label="Ver detalle {h} vs {a}">
  <div class="teams"><b>{h} vs {a}</b>
    <span class="badge {html.escape(conf)}">{html.escape(pred['confidence'])}</span></div>
  <div class="meta">{html.escape(str(pred['match_date']))}{venue}</div>
  {bars}
  <div class="chips">{chips}</div>
  <div class="meta" style="margin-top:6px">λ {pred['exp_home']:.2f}–{pred['exp_away']:.2f}
    · <span style="color:var(--model)">ver detalle →</span></div>
</div>"""
```

- [ ] **Step 2: Verificar (parcial; `_tab_proximos` se actualiza en Task 5).** Run:
`.venv/bin/python -c "import predictor.panel as p; print('stack' in dir(p) or hasattr(p,'_stack'), hasattr(p,'_card'))"`
Expected: `True True`

- [ ] **Step 3: Commit.**
```bash
git add predictor/panel.py
git commit -m "panel: card rica (barra 1X2 apilada + chips + confianza + clicable)"
```

---

### Task 4: Modal de detalle + JS

**Files:**
- Modify: `predictor/panel.py` (añadir funciones nuevas y la constante JS)

- [ ] **Step 1: Añadir AL FINAL de `panel.py` estas funciones y el JS del modal:**

```python
def _heat(bd):
    gi, gj = bd["gp_cell"]
    ti, tj = bd["modal_cell"]
    m = bd["matrix6"]
    mx = max(max(r) for r in m) or 1.0
    out = ['<div class="heat"><span></span>']
    out += [f'<span class="hd">{j}</span>' for j in range(6)]
    for i in range(6):
        out.append(f'<span class="hd">{i}</span>')
        for j in range(6):
            p = m[i][j]
            cls = "cell" + (" gp" if (i, j) == (gi, gj) else "")
            cls += " modal" if (i, j) == (ti, tj) else ""
            op = 0.08 + 0.92 * (p / mx)
            out.append(f'<span class="{cls}" title="{i}-{j}: {p:.1%}" '
                       f'style="background:rgba(37,99,235,{op:.2f})">'
                       f'{p*100:.0f}</span>')
    out.append('</div>')
    return "".join(out)


def _fbars(terms):
    mx = max((abs(v) for _, v in terms), default=1.0) or 1.0
    rows = ""
    for label, v in terms:
        w = abs(v) / mx * 50
        seg = (f'<span class="pos" style="width:{w:.0f}%"></span>' if v >= 0
               else f'<span class="neg" style="width:{w:.0f}%"></span>')
        rows += (f'<div class="fbar"><span>{html.escape(label)}</span>'
                 f'<span class="track2">{seg}</span>'
                 f'<span class="v">{v:+.2f}</span></div>')
    return rows


def _modal(pred, idx):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    bd = pred["breakdown"]
    bars = _stack(pred["p_home"], pred["p_draw"], pred["p_away"],
                  pred["home"], pred["away"]) if "p_home" in pred else ""
    mkt = bd["market_probs"]
    mezcla = (f'{bd["blend_w"]:.0%} mercado / {1-bd["blend_w"]:.0%} modelo'
              if mkt else "sin mercado (solo modelo)")
    mrow = ""
    if mkt:
        mrow = (f'<div class="meta">Modelo {bd["model_probs"][0]:.0%}/'
                f'{bd["model_probs"][1]:.0%}/{bd["model_probs"][2]:.0%} · '
                f'Mercado {mkt[0]:.0%}/{mkt[1]:.0%}/{mkt[2]:.0%}</div>')
    return f"""<div class="backdrop" id="d-{idx}" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Detalle {h} vs {a}">
    <button class="x" aria-label="Cerrar" data-close="1">✕</button>
    <h2>{h} vs {a} · cómo se llegó al {html.escape(pred.get('gp_score', pred['top_score']))}</h2>
    {bars}
    <h3>Matriz de goles (probabilidad de cada marcador)</h3>
    {_heat(bd)}
    <div class="meta" style="margin-top:6px">Borde verde = 🎯 óptimo-EV ·
      borde azul = más probable. Local en filas, visita en columnas.</div>
    <h3>Peso de cada factor — {h} (goles esp., log)</h3>
    {_fbars(bd["home_terms"])}
    <h3>Peso de cada factor — {a}</h3>
    {_fbars(bd["away_terms"])}
    <h3>Mezcla modelo ↔ mercado</h3>
    <div class="meta">{mezcla}</div>
    {mrow}
  </div></div>"""


MODAL_JS = """
<script>
(function(){
  function open(id){var m=document.getElementById(id);if(m)m.hidden=false;}
  function closeAll(){document.querySelectorAll('.backdrop').forEach(function(b){b.hidden=true;});}
  document.querySelectorAll('.card[data-detail]').forEach(function(c){
    c.addEventListener('click',function(){open(c.dataset.detail);});
    c.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open(c.dataset.detail);}});
  });
  document.querySelectorAll('.backdrop').forEach(function(b){
    b.addEventListener('click',function(e){if(e.target===b||e.target.dataset.close)closeAll();});
  });
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeAll();});
})();
</script>
"""
```

- [ ] **Step 2: Verificar.** Run:
`.venv/bin/python -c "from predictor import store, panel as p; from predictor.cli import ensure_fit, find_fixtures; con=store.connect(); fit,_=ensure_fit(con); fx=find_fixtures(con,limit=1)[0]; import predictor.predict as P; pred=P.predict_match(con,fit,fx); pred['data_version']={}; html=p._modal(pred,0); assert 'class=\"heat\"' in html and 'class=\"fbar\"' in html and 'role=\"dialog\"' in html; print('modal OK', len(html))"`
Expected: `modal OK <n>`

- [ ] **Step 3: Commit.**
```bash
git add predictor/panel.py
git commit -m "panel: modal de detalle (heatmap matriz + barras de factores + mezcla)"
```

---

### Task 5: Ensamblar en `_tab_proximos` y `render`

**Files:**
- Modify: `predictor/panel.py` (`_tab_proximos` y `render`)

- [ ] **Step 1: Reemplazar `_tab_proximos` por esta versión** (pasa `idx` y añade los modales tras la grilla):

```python
def _tab_proximos(preds):
    if not preds:
        return ('<section class="panel" id="proximos">'
                '<p class="meta">Sin partidos próximos.</p></section>')
    cards = "\n".join(_card(p, i) for i, p in enumerate(preds))
    modals = "\n".join(_modal(p, i) for i, p in enumerate(preds))
    return (f'<section class="panel" id="proximos"><div class="grid">{cards}'
            f'</div>{modals}</section>')
```

- [ ] **Step 2: Añadir `MODAL_JS` a la página.** En `render`, localizar `</div>{TABS_JS}</body></html>` y cambiarlo por `</div>{TABS_JS}{MODAL_JS}</body></html>`.

- [ ] **Step 3: Generar el panel y verificar.** Run:
`.venv/bin/python -m predictor panel 6 --no-abrir && .venv/bin/python -c "h=open('data/panel.html',encoding='utf-8').read(); assert 'class=\"stack\"' in h and 'class=\"backdrop\"' in h and 'class=\"heat\"' in h and 'data-detail=\"d-0\"' in h and 'id=\"d-0\"' in h; print('panel v2 OK', len(h), 'bytes')"`
Expected: `panel v2 OK <n> bytes`

- [ ] **Step 4: Revisión visual.** Abrir `data/panel.html`: las cards muestran barra 1X2 apilada (3 colores) + chips; al hacer clic se abre el modal con heatmap (celdas resaltadas), barras de factores y la mezcla; cierra con ✕, Esc y clic fuera. Sin scroll horizontal a 375px.

- [ ] **Step 5: Commit.**
```bash
git add predictor/panel.py
git commit -m "panel: ensamblar cards v2 + modales en la pestana Proximos"
```

---

## Self-Review

**Spec coverage:**
- `breakdown` desde `predict_match` → Task 1. ✓
- Cards rediseñadas (barra apilada, chips, confianza color, clicable) → Tasks 2, 3. ✓
- Modal (1X2 + heatmap + factores con peso + mezcla) → Tasks 2, 4. ✓
- Ensamblaje + JS (clic/Esc/clic-fuera) → Tasks 4, 5. ✓
- #1 descartado → no es tarea (decisión documentada en spec). ✓
- Accesibilidad (role=dialog, aria-label, Esc, tabindex, title en celdas, reduced-motion del CSS base) → Tasks 2, 4. ✓

**Placeholder scan:** sin TBD/TODO; código completo en cada paso.

**Type consistency:** `breakdown` (Task 1) define las claves `lh,la,home_terms,away_terms,matrix6,model_probs,market_probs,final_probs,blend_w,gp_cell,modal_cell`; `_heat`/`_fbars`/`_modal` (Task 4) consumen exactamente esas claves. `_card` y `_modal` reciben `(pred, idx)` y `_tab_proximos` (Task 5) los llama con `enumerate`. `_stack` definido en Task 3 y reutilizado en Task 4. `MODAL_JS` definido en Task 4, usado en Task 5. ✓
