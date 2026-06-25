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
