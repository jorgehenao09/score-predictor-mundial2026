# Rediseño Aciertos + Modelo (línea v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Llevar las pestañas Aciertos y Modelo a la línea visual v2 (KPIs con acento de color, historial `predicho → real ✓/✗ pts`, capas como chips, tabla con BASE diferenciada + microcopy).

**Architecture:** `panel_data.accuracy` añade `pred` (marcador predicho) a cada item del historial. `panel_style.py` añade CSS mínimo (acentos KPI, tabla comparativa, chips de capas). `panel.py` reescribe `_kpi`, `_tab_aciertos`, `PARAMS` y `_tab_modelo`. Reutiliza tokens/componentes existentes.

**Tech Stack:** Python 3.12, HTML/CSS embebido, sin frameworks. Diseño: `design-system/score-predictor/MASTER.md`.

**Convención (IMPORTANTE):** sin tests formales. Verificación = chequeo inline (`.venv/bin/python -c ...`) o generar `data/panel.html`. Comentarios en español.

---

### Task 1: `pred` en el historial de aciertos

**Files:** Modify `predictor/panel_data.py` (función `accuracy`)

- [ ] **Step 1:** En `predictor/panel_data.py`, dentro de `accuracy`, localizar el `history.append({...})` del loop. Reemplazar esa llamada por:

```python
        history.append({"date": d, "home": h, "away": a, "verdict": vlabel,
                        "real": f"{hs}-{as_}", "ok": ok, "pts": pts,
                        "pred": (gps if gps else ts)})
```

- [ ] **Step 2: Verificar.** Run:
`.venv/bin/python -c "from predictor import store, panel_data; r=panel_data.accuracy(store.connect()); it=r['history'][0]; assert 'pred' in it; print('pred OK:', it['pred'], '->', it['real'])"`
Expected: `pred OK: <marcador> -> <marcador>`

- [ ] **Step 3: Commit.**
```bash
git add predictor/panel_data.py
git commit -m "panel_data: marcador predicho (pred) en cada item del historial"
```

---

### Task 2: CSS de los rediseños

**Files:** Modify `predictor/panel_style.py` (añadir al final del string `CSS`, antes del `"""` de cierre)

- [ ] **Step 1:** Insertar este bloque inmediatamente antes del `"""` que cierra la constante `CSS`:

```css

/* === Aciertos/Modelo v2 === */
.kpi.k-model .v{color:var(--model)}
.kpi.k-final .v{color:var(--final)}
.kpi.k-value .v{color:var(--value)}
.kpi.k-miss .v{color:var(--miss)}
.arrow{color:var(--text-faint)}
.layers{display:flex;flex-wrap:wrap;gap:var(--sp-1);margin:var(--sp-2) 0 var(--sp-3)}
.compare td.base,.compare th.base{background:var(--surface-2)}
.compare .desc{display:block;font-size:11px;color:var(--text-faint);font-weight:400}
```

- [ ] **Step 2: Verificar.** Run:
`.venv/bin/python -c "from predictor.panel_style import CSS; assert '.kpi.k-model' in CSS and '.compare td.base' in CSS and '.layers' in CSS; print('CSS OK', len(CSS))"`
Expected: `CSS OK <n>`

- [ ] **Step 3: Commit.**
```bash
git add predictor/panel_style.py
git commit -m "panel: CSS de Aciertos/Modelo (acentos KPI, tabla BASE, chips de capas)"
```

---

### Task 3: Rediseñar `_kpi` y `_tab_aciertos`

**Files:** Modify `predictor/panel.py` (`_kpi` y `_tab_aciertos`)

- [ ] **Step 1:** Reemplazar la función `_kpi` actual por:

```python
def _kpi(value, label, accent=""):
    return (f'<div class="kpi {accent}"><div class="v num">{value}</div>'
            f'<div class="l">{label}</div></div>')
```

- [ ] **Step 2:** Reemplazar la función `_tab_aciertos` completa por:

```python
def _tab_aciertos(acc):
    if not acc["n"]:
        return ('<section class="panel" id="aciertos" hidden>'
                '<p class="meta">Aún no hay partidos resueltos.</p></section>')
    roi_v = acc["roi"]
    roi = f"{roi_v:+.0f}%" if roi_v is not None else "—"
    roi_acc = "" if roi_v is None else ("k-final" if roi_v >= 0 else "k-miss")
    kpis = (
        _kpi(f"{acc['hits_1x2']:.0f}%", "1X2 acertado", "k-model")
        + _kpi(f"{acc['exact']:.0f}%", "Marcador exacto", "k-final")
        + _kpi(str(acc["gp_points"]), "Puntos golpredictor", "k-value")
        + _kpi(f"{acc['rps']:.3f}", "RPS (calidad, menor mejor)")
        + _kpi(roi, "ROI ilustrativo*", roi_acc))
    trs = ""
    for r in acc["history"]:
        badge = ('<span class="badge hit">✓</span>' if r["ok"]
                 else '<span class="badge miss">✗</span>')
        trs += (f'<tr><td class="n">{html.escape(r["date"])}</td>'
                f'<td>{html.escape(r["home"])} vs {html.escape(r["away"])}</td>'
                f'<td class="n">{html.escape(r.get("pred", "—"))} '
                f'<span class="arrow">→</span> {html.escape(r["real"])}</td>'
                f'<td>{badge}</td><td class="n">{r["pts"]}</td></tr>')
    return f"""<section class="panel" id="aciertos" hidden>
  <div class="kpis">{kpis}</div>
  <p class="meta">El modelo es fuerte prediciendo <b>quién gana</b>; el
    <b>marcador exacto</b> es intrínsecamente difícil. *ROI ilustrativo: apostar
    al veredicto a cuota de cierre; no es consejo de apuesta.</p>
  <table><thead><tr><th>Fecha</th><th>Partido</th><th>Predicho → Real</th>
    <th>✓/✗</th><th>Pts</th></tr></thead><tbody>{trs}</tbody></table>
</section>"""
```

- [ ] **Step 3: Verificar.** Run:
`.venv/bin/python -c "from predictor import store, panel, panel_data; h=panel._tab_aciertos(panel_data.accuracy(store.connect())); assert 'k-model' in h and 'class=\"arrow\"' in h and 'Predicho → Real' in h; print('aciertos v2 OK')"`
Expected: `aciertos v2 OK`

- [ ] **Step 4: Commit.**
```bash
git add predictor/panel.py
git commit -m "panel: Aciertos v2 (KPIs con color + historial predicho->real)"
```

---

### Task 4: Rediseñar `PARAMS` y `_tab_modelo`

**Files:** Modify `predictor/panel.py` (`PARAMS` y `_tab_modelo`)

- [ ] **Step 1:** Reemplazar la constante `PARAMS` (lista de tuplas de 2) por esta versión con descripción, y añadir la constante `LAYERS` justo después:

```python
PARAMS = [
    ("xi", "xi (decaimiento temporal)", "cuánto pesan los partidos viejos"),
    ("rho", "rho (marcadores bajos)", "corrección Dixon-Coles de 0-0 / 1-1"),
    ("local", "ventaja local", "bono al anfitrión que juega en su país"),
    ("blend", "mezcla modelo↔mercado", "peso del mercado, autoaprendido"),
    ("uplift", "goal uplift", "corrección de volumen de goles"),
    ("autotune", "¿auto-ajusta?", "qué se recalibra solo")]

LAYERS = ["Dixon-Coles", "prior Elo", "Shin de-vig", "óptimo-EV", "mezcla auto"]
```

- [ ] **Step 2:** Reemplazar la función `_tab_modelo` completa por:

```python
def _tab_modelo(base, competitions):
    cols = "".join(f'<th>{html.escape(c["name"])}</th>' for c in competitions)
    chips = "".join(f'<span class="chip">{html.escape(x)}</span>' for x in LAYERS)
    rows = ""
    for key, label, desc in PARAMS:
        cells = "".join(f'<td class="n">{html.escape(str(c["params"][key]))}</td>'
                        for c in competitions)
        rows += (f'<tr><td>{html.escape(label)}'
                 f'<span class="desc">{html.escape(desc)}</span></td>'
                 f'<td class="n base">{html.escape(str(base[key]))}</td>{cells}</tr>')
    return f"""<section class="panel" id="modelo" hidden>
  <div class="explain">
    <b>El modelo base (universal, no cambia entre competiciones).</b>
    <div class="layers">{chips}</div>
    Dixon-Coles ponderado por tiempo (ataque/defensa por selección, corrección
    rho de marcadores bajos) · prior Elo para selecciones con poca muestra ·
    de-vigging del mercado por método de Shin · marcador óptimo-EV para
    golpredictor · y una <b>mezcla modelo↔mercado autoaprendida</b> que minimiza
    el RPS sobre lo ya jugado.
  </div>
  <table class="compare"><thead><tr><th>Parámetro</th>
    <th class="base">BASE</th>{cols}</tr></thead>
    <tbody>{rows}</tbody></table>
  <p class="meta" style="margin-top:12px">Cada competición que se añada al
    registro aparece como una columna nueva. La fila BASE son los defaults
    universales del modelo.</p>
</section>"""
```

- [ ] **Step 3: Verificar.** Run:
`.venv/bin/python -c "from predictor import store, panel, panel_data; b,c=panel_data.calibration(store.connect()); h=panel._tab_modelo(b,c); assert 'class=\"layers\"' in h and 'class=\"chip\"' in h and 'class=\"n base\"' in h and 'class=\"desc\"' in h; print('modelo v2 OK')"`
Expected: `modelo v2 OK`

- [ ] **Step 4: Commit.**
```bash
git add predictor/panel.py
git commit -m "panel: Modelo v2 (capas en chips + tabla BASE diferenciada + microcopy)"
```

---

### Task 5: Generar y verificar el panel completo

**Files:** (ninguno — verificación)

- [ ] **Step 1: Generar y comprobar.** Run:
`.venv/bin/python -m predictor panel 6 --no-abrir && .venv/bin/python -c "h=open('data/panel.html',encoding='utf-8').read(); assert all(x in h for x in ['kpi k-model','class=\"arrow\"','Predicho → Real','class=\"layers\"','class=\"compare\"','class=\"desc\"']); print('panel completo OK', len(h), 'bytes')"`
(El comando `panel` hace un sync ligero de red; puede tardar ~30-60s.)
Expected: `panel completo OK <n> bytes`

- [ ] **Step 2: Revisión visual.** Abrir `data/panel.html`: pestaña Aciertos con KPIs de color (1X2 azul, exacto verde, puntos oro, ROI según signo) y el historial mostrando `predicho → real` con ✓/✗ y puntos; pestaña Modelo con las capas como chips y la tabla con la columna BASE con fondo sutil + microcopy bajo cada parámetro. Próximos y su modal siguen funcionando. Sin scroll horizontal a 375px.

- [ ] **Step 3: Commit (si la revisión visual no requirió cambios, no hay nada que commitear; si sí, commitear los ajustes).**
```bash
git status --short
```

---

## Self-Review

**Spec coverage:**
- `pred` en el historial → Task 1. ✓
- KPIs con acento de color → Tasks 2, 3. ✓
- Historial `predicho → real ✓/✗ pts` → Task 3. ✓
- Capas como chips → Tasks 2, 4. ✓
- Tabla BASE diferenciada + microcopy (`PARAMS` con descripción) → Tasks 2, 4. ✓
- Reutiliza tokens/componentes existentes; sin tocar modelo ni Próximos. ✓
- Accesibilidad (color en números/borde, ✓/✗ con símbolo, tabla con encabezados) → Tasks 2-4. ✓

**Placeholder scan:** sin TBD/TODO; código completo en cada paso.

**Type consistency:** `_kpi` ahora `(value, label, accent="")`; las llamadas en `_tab_aciertos` pasan el accent. `accuracy().history[i]` gana clave `pred` (Task 1), consumida con `.get("pred","—")` en Task 3 (seguro aunque falte). `PARAMS` pasa a tuplas de 3 `(key, label, desc)` (Task 4) y `_tab_modelo` desempaca las 3. `LAYERS` definida en Task 4 y usada en el mismo. La tabla de Modelo gana `class="compare"` y celdas BASE `class="...base"` que casan con el CSS de Task 2. ✓
