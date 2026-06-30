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


def _tab_proximos(preds):
    if not preds:
        return ('<section class="panel" id="proximos">'
                '<p class="meta">Sin partidos próximos.</p></section>')
    cards = "\n".join(_card(p, i) for i, p in enumerate(preds))
    modals = "\n".join(_modal(p, i) for i, p in enumerate(preds))
    return (f'<section class="panel" id="proximos"><div class="grid">{cards}'
            f'</div>{modals}</section>')


def _kpi(value, label, accent=""):
    return (f'<div class="kpi {accent}"><div class="v num">{value}</div>'
            f'<div class="l">{label}</div></div>')


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


PARAMS = [
    ("xi", "xi (decaimiento temporal)", "cuánto pesan los partidos viejos"),
    ("rho", "rho (marcadores bajos)", "corrección Dixon-Coles de 0-0 / 1-1"),
    ("local", "ventaja local", "bono al anfitrión que juega en su país"),
    ("blend", "mezcla modelo↔mercado", "peso del mercado, autoaprendido"),
    ("uplift", "goal uplift", "corrección de volumen de goles"),
    ("autotune", "¿auto-ajusta?", "qué se recalibra solo")]

LAYERS = ["Dixon-Coles", "prior Elo", "Shin de-vig", "óptimo-EV", "mezcla auto"]


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


def render(con, preds, data_version) -> str:
    from .store import now_iso
    acc = panel_data.accuracy(con)
    base, comps = panel_data.calibration(con)
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Score Predictor · Mundial 2026</title>
<link rel="stylesheet" href="{html.escape(FONTS)}">
<style>{CSS}</style></head><body><div class="wrap">
<h1>⚽ Score Predictor · Mundial 2026</h1>
<div class="sub">Generado {now_iso()} · {len(preds)} partidos próximos · datos: {html.escape(" · ".join(f"{k} {v}" for k, v in data_version.items()))}</div>
<div class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-target="proximos">Próximos</button>
  <button class="tab" role="tab" aria-selected="false" data-target="aciertos">Aciertos</button>
  <button class="tab" role="tab" aria-selected="false" data-target="modelo">Modelo</button>
</div>
{_tab_proximos(preds)}
{_tab_aciertos(acc)}
{_tab_modelo(base, comps)}
</div>{TABS_JS}{MODAL_JS}</body></html>"""
    with open(PANEL_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    return PANEL_PATH


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
  function open(id, trigger){var m=document.getElementById(id);if(!m)return;m._trigger=trigger;m.hidden=false;var f=m.querySelector('button, [tabindex], a, input');if(f)f.focus();}
  function closeAll(){document.querySelectorAll('.backdrop').forEach(function(b){if(!b.hidden&&b._trigger)b._trigger.focus();b.hidden=true;});}
  document.querySelectorAll('.card[data-detail]').forEach(function(c){
    c.addEventListener('click',function(){open(c.dataset.detail,c);});
    c.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open(c.dataset.detail,c);}});
  });
  document.querySelectorAll('.backdrop').forEach(function(b){
    b.addEventListener('click',function(e){if(e.target===b||e.target.dataset.close)closeAll();});
  });
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeAll();});
})();
</script>
"""
