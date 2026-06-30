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
    cards = "\n".join(_card(p) for p in preds) or \
        '<p class="meta">Sin partidos próximos.</p>'
    return f'<section class="panel" id="proximos"><div class="grid">{cards}</div></section>'


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
</div>{TABS_JS}</body></html>"""
    with open(PANEL_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    return PANEL_PATH
