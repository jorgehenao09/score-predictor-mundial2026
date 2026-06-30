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
"""
