"""Auto-recalibración diaria con guardarraíles.

Filosofía (ver CLAUDE.md "gobernanza de calibración"):
  - Lo de ALTA señal por partido ya se auto-ajusta solo: ratings (cada
    resultado) y peso de mezcla modelo↔mercado (learning.py).
  - Lo ESTRUCTURAL (GOAL_UPLIFT) se audita a diario sobre TODO el histórico
    (WC2018 + WC2022 + lo jugado de WC2026). Se AUTO-APLICA solo dentro de la
    banda ya validada como segura [1.05, 1.15]; si la evidencia apunta fuera
    de la banda, NO toca nada y AVISA para decisión humana.
  - Auto-tunear estructurales a diario sobre ~100 partidos sobreajustaría; por
    eso el anclaje es el histórico multi-mundial, no solo los partidos en vivo.

Devuelve un reporte y, con apply=True, persiste el uplift en
data/tuned_params.json (committeado; la BD es efímera en CI).
"""

import json
import os

import numpy as np

from . import golpredictor as gp
from . import learning, ratings, sources, store
from .predict import (GOAL_UPLIFT_BAND, GOAL_UPLIFT_DEFAULT, TUNED_PARAMS_PATH,
                      goal_uplift, rps, score_matrix)

GRID = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35]
MIN_GAIN = 0.01      # mejora mínima relativa en puntos para cambiar (anti-churn)
OUT_OF_BAND_MARGIN = 0.02   # ventaja mín. fuera de banda para disparar alerta
LIVE_RPS_ALERT = 0.26       # RPS en vivo peor que esto (con muestra) = alerta
LIVE_MIN_N = 8


def _oos_sets(con):
    """Conjuntos OOS: (fit, partidos_test) para WC2018, WC2022 y WC2026-jugado."""
    known = ({r[0] for r in con.execute("SELECT DISTINCT home FROM matches")} |
             {r[0] for r in con.execute("SELECT DISTINCT away FROM matches")})
    elo = sources.fetch_elo(con, known)
    cups = [("2018-06-14", "2018-07-16"), ("2022-11-20", "2022-12-19"),
            ("2026-06-11", "2026-07-20")]
    out = []
    for cutoff, end in cups:
        test = [tuple(r) for r in con.execute(
            """SELECT home, away, home_score, away_score, neutral
               FROM matches WHERE tournament='FIFA World Cup'
               AND date >= ? AND date < ? AND home_score IS NOT NULL""",
            (cutoff, end)).fetchall()]
        if not test:
            continue
        fit = ratings.fit_full(ratings.load_training_matches(con, until=cutoff),
                               cutoff, elo=elo)
        out.append((fit, test))
    return out


def _per_match_points(oos, up):
    """Lista de puntos golpredictor (óptimo-EV) por partido, y RPS por partido,
    para un uplift dado. Permite comparaciones PAREADAS (mismo partido)."""
    pts, rpss = [], []
    for fit, test in oos:
        rho = fit["rho"]
        R = fit["ratings"]
        for h, a, hs, as_, neutral in test:
            ah, dh, _ = R.get(h, (0.0, 0.0, 0.0))
            aa, da, _ = R.get(a, (0.0, 0.0, 0.0))
            lh = np.exp(fit["mu"] + ah - da + fit["ha"] * (0 if neutral else 1)) * up
            la = np.exp(fit["mu"] + aa - dh) * up
            M = score_matrix(lh, la, rho)
            evs, _ = gp.ev_optimal_score(M)
            pts.append(gp.points(evs, (hs, as_)))
            probs = (float(np.tril(M, -1).sum()), float(np.trace(M)),
                     float(np.triu(M, 1).sum()))
            o = 0 if hs > as_ else (1 if hs == as_ else 2)
            rpss.append(rps(probs, o))
    return np.array(pts, dtype=float), float(np.mean(rpss)) if rpss else 0.0


def _paired_t(a, b):
    """t pareada de (a-b); |t|>~2 ≈ diferencia significativa. 0 si sin varianza."""
    d = a - b
    n = len(d)
    sd = d.std(ddof=1) if n > 1 else 0.0
    if sd == 0:
        return 0.0
    return float(d.mean() / (sd / np.sqrt(n)))


def _live_check(con):
    """Rendimiento en vivo: EV-opt vs modal y RPS sobre WC2026 resuelto."""
    rows = con.execute(
        """SELECT p.p_home,p.p_draw,p.p_away,p.top_score,p.gp_score,
                  m.home_score,m.away_score,p.match_date
           FROM predictions p JOIN matches m
             ON m.home=p.home AND m.away=p.away AND m.date=p.match_date
           WHERE m.home_score IS NOT NULL
             AND p.id IN (SELECT MAX(id) FROM predictions
                          WHERE substr(created_at,1,10)<=match_date
                          GROUP BY home,away,match_date)""").fetchall()
    modal_all = 0           # puntos modal sobre TODO lo resuelto (lo ganado)
    pair_modal = opt_pts = n_opt = 0   # comparación PAREADA (mismas partidos)
    rpss = []
    for ph, pd_, pa, ts, gps, hs, as_, d in rows:
        ko = gp.is_knockout(d)
        mp = gp.points(tuple(map(int, ts.split("-"))), (hs, as_), ko)
        modal_all += mp
        if gps:
            pair_modal += mp
            opt_pts += gp.points(tuple(map(int, gps.split("-"))), (hs, as_), ko)
            n_opt += 1
        o = 0 if hs > as_ else (1 if hs == as_ else 2)
        rpss.append(rps((ph, pd_, pa), o))
    return {"n": len(rows), "modal_pts": modal_all, "pair_modal": pair_modal,
            "opt_pts": opt_pts, "n_opt": n_opt,
            "rps": float(np.mean(rpss)) if rpss else None}


def run_audit(con, apply=True):
    sources.sync_results(con)
    oos = _oos_sets(con)
    per_match = {up: _per_match_points(oos, up) for up in GRID}
    scored = {up: float(arr.sum()) for up, (arr, _) in per_match.items()}
    n_oos = len(next(iter(per_match.values()))[0])

    in_band = [u for u in GRID if GOAL_UPLIFT_BAND[0] <= u <= GOAL_UPLIFT_BAND[1]]
    best_band = max(in_band, key=lambda u: scored[u])
    best_any = max(GRID, key=lambda u: scored[u])
    current = goal_uplift()
    cur_pts = scored.get(round(current, 2), scored[best_band])

    report = {
        "n_oos": n_oos, "current_uplift": current,
        "best_in_band": best_band, "best_in_band_pts": scored[best_band],
        "best_any": best_any, "best_any_pts": scored[best_any],
        "grid": {u: scored[u] for u in GRID},
        "live": _live_check(con),
        "blend_w": learning.current_blend(con),
        "applied": None, "alerts": [],
    }

    # auto-aplicar dentro de banda si mejora de forma no trivial
    gain = (scored[best_band] - cur_pts) / max(cur_pts, 1)
    if apply and abs(best_band - current) > 1e-9 and gain >= MIN_GAIN:
        _write_uplift(best_band, report)
        report["applied"] = best_band

    # alerta fuera de banda SOLO si la ventaja es (a) material y (b)
    # estadísticamente significativa por partido (pareada). Sin el guard de
    # significancia la alarma suena por ruido de 1-2 partidos (banda elegida a
    # propósito por exacto/realismo, no por puntos crudos planos).
    if best_any not in in_band:
        adv = (scored[best_any] - scored[best_band]) / max(scored[best_band], 1)
        t = abs(_paired_t(per_match[best_any][0], per_match[best_band][0]))
        if adv >= OUT_OF_BAND_MARGIN and t >= 2.0:
            report["alerts"].append(
                f"El uplift óptimo OOS es {best_any} (fuera de la banda "
                f"{GOAL_UPLIFT_BAND}): {adv * 100:.1f}% mejor y SIGNIFICATIVO "
                f"(t={t:.1f}, {n_oos} partidos). Requiere tu decisión.")

    live = report["live"]
    if live["rps"] and live["n"] >= LIVE_MIN_N and live["rps"] > LIVE_RPS_ALERT:
        report["alerts"].append(
            f"RPS en vivo {live['rps']:.3f} sobre {live['n']} partidos, peor de "
            f"lo esperado (~0.21). Revisar si el modelo se está desviando.")
    if (live["n_opt"] >= LIVE_MIN_N
            and live["opt_pts"] < 0.9 * live["modal_pts"]):
        report["alerts"].append(
            f"En vivo el óptimo-EV ({live['opt_pts']} pts) va >10% bajo el modal "
            f"({live['modal_pts']}) en {live['n_opt']} partidos; revisar la "
            f"estrategia de marcador.")

    return report


def _write_uplift(value, report):
    os.makedirs(os.path.dirname(TUNED_PARAMS_PATH), exist_ok=True)
    payload = {"goal_uplift": round(value, 3), "updated_at": store.now_iso(),
               "note": f"auto-aplicado por autocalibrate (OOS {report['n_oos']} "
                       f"partidos); banda {GOAL_UPLIFT_BAND}"}
    with open(TUNED_PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def format_report(r) -> str:
    lines = [f"AUTOCALIBRACIÓN ({r['n_oos']} partidos OOS)", "─" * 40]
    grid = "  ".join(f"{u}:{p}" for u, p in r["grid"].items())
    lines.append(f"  Puntos golpredictor por uplift: {grid}")
    lines.append(f"  Uplift actual: {r['current_uplift']} · "
                 f"mejor en banda: {r['best_in_band']} · "
                 f"mejor sin restricción: {r['best_any']}")
    if r["applied"] is not None:
        lines.append(f"  ✅ Auto-aplicado uplift = {r['applied']} (dentro de banda)")
    else:
        lines.append("  Sin cambios (ya óptimo en banda o mejora despreciable)")
    w, nlearn = r["blend_w"]
    lines.append(f"  Peso mezcla auto-aprendido: {w} ({nlearn} partidos)")
    live = r["live"]
    if live["n_opt"]:
        lines.append(f"  En vivo (pareado, {live['n_opt']} partidos con óptimo "
                     f"guardado): óptimo-EV {live['opt_pts']} vs modal "
                     f"{live['pair_modal']} pts")
    if r["alerts"]:
        lines.append("  ⚠️ ALERTAS:")
        for a in r["alerts"]:
            lines.append(f"    · {a}")
    else:
        lines.append("  ✓ Sin alertas: parámetros estructurales en zona segura")
    return "\n".join(lines)


def telegram_message(r):
    """Mensaje para Telegram solo si hay algo que reportar (cambio o alerta).
    Devuelve None si el día fue rutinario (evita spam diario)."""
    if r["applied"] is None and not r["alerts"]:
        return None
    head = ("🔧 <b>Autocalibración diaria</b>\n"
            if not r["alerts"] else "⚠️ <b>Autocalibración — atención</b>\n")
    return head + format_report(r)


def send_telegram(text) -> bool:
    import urllib.parse
    import urllib.request
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                   "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage", data=data),
            timeout=30)
        return True
    except Exception:
        return False


def main():
    import sys
    con = store.connect()
    r = run_audit(con, apply=True)
    print(format_report(r))
    if "--telegram" in sys.argv:
        msg = telegram_message(r)
        if msg and send_telegram(msg):
            print("  (alerta/cambio enviado a Telegram)")


if __name__ == "__main__":
    main()
