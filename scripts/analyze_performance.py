"""Análisis post-jornadas: compara cada predicción con el resultado real,
cuantifica los puntos de golpredictor obtenidos y los que se habrían obtenido
optimizando para esa tabla de puntaje, y diagnostica sesgos.

golpredictor (fase de grupos): 5 acierto resultado (1X2), 2 goles local exactos,
2 goles visita exactos, 1 diferencia de gol. Máx 10 = marcador exacto.

Uso: .venv/bin/python scripts/analyze_performance.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictor import store                          # noqa: E402
from predictor.predict import score_matrix, MAX_GOALS, rps, brier  # noqa: E402


def golpredictor_points(pred, actual, knockout=False):
    """pred=(ph,pa), actual=(ah,ab). Devuelve puntos golpredictor."""
    ph, pa = pred
    ah, ab = actual
    mult = 2 if knockout else 1
    pts = 0
    if np.sign(ph - pa) == np.sign(ah - ab):
        pts += 5 * mult
    if ph == ah:
        pts += 2 * mult
    if pa == ab:
        pts += 2 * mult
    if (ph - pa) == (ah - ab):
        pts += 1 * mult
    return pts


def expected_points_score(M, knockout=False):
    """Marcador (i,j) que MAXIMIZA los puntos esperados de golpredictor según
    la matriz de probabilidad M. Distinto del marcador más probable (modal)."""
    best, best_ev = (0, 0), -1
    n = M.shape[0]
    for i in range(n):
        for j in range(n):
            ev = 0.0
            for a in range(n):
                for b in range(n):
                    ev += M[a, b] * golpredictor_points((i, j), (a, b), knockout)
            if ev > best_ev:
                best_ev, best = ev, (i, j)
    return best, best_ev


def main():
    con = store.connect()
    fit, _ = store.latest_fit(con)
    rho = fit["rho"]

    rows = con.execute(
        """SELECT p.home, p.away, p.match_date, p.exp_home, p.exp_away,
                  p.p_home, p.p_draw, p.p_away, p.top_score,
                  p.model_p_home, p.model_p_draw, p.model_p_away,
                  p.market_p_home, p.market_p_draw, p.market_p_away,
                  m.home_score, m.away_score
           FROM predictions p JOIN matches m
             ON m.home=p.home AND m.away=p.away AND m.date=p.match_date
           WHERE m.home_score IS NOT NULL
             AND p.id IN (SELECT MAX(id) FROM predictions
                          WHERE substr(created_at,1,10) <= match_date
                          GROUP BY home, away, match_date)
           ORDER BY p.match_date""").fetchall()

    if not rows:
        print("No hay predicciones resueltas.")
        return

    print(f"{'PARTIDO':<34}{'PRED':>6}{'REAL':>6}{'EV-opt':>7}"
          f"{'gp_modal':>9}{'gp_opt':>8}")
    print("─" * 78)

    tot_modal_pts = tot_opt_pts = 0
    sum_actual_goals = sum_modal_goals = sum_exp_goals = 0.0
    briers_blend, rpss_blend = [], []
    hit1x2 = hit_exact = 0
    n = len(rows)
    underpred = 0  # partidos donde el modal predijo menos goles que la realidad
    calib_bins = {}  # prob bin -> [hits, total] para el favorito

    for r in rows:
        (h, a, d, eh, ea, ph, pd_, pa, ts,
         mph, mpd, mpa, kph, kpd, kpa, hs, as_) = r
        # reconstruir la matriz del modelo a la hora de predecir
        M = score_matrix(eh, ea, rho)
        modal = tuple(map(int, ts.split("-")))
        evscore, _ = expected_points_score(M)
        actual = (hs, as_)

        gp_modal = golpredictor_points(modal, actual)
        gp_opt = golpredictor_points(evscore, actual)
        tot_modal_pts += gp_modal
        tot_opt_pts += gp_opt

        sum_actual_goals += hs + as_
        sum_modal_goals += sum(modal)
        sum_exp_goals += eh + ea
        if sum(modal) < hs + as_:
            underpred += 1

        probs = (ph, pd_, pa)
        out = 0 if hs > as_ else (1 if hs == as_ else 2)
        briers_blend.append(brier(probs, out))
        rpss_blend.append(rps(probs, out))
        if max(range(3), key=lambda i: probs[i]) == out:
            hit1x2 += 1
        if modal == actual:
            hit_exact += 1

        # calibración del favorito (prob máx 1X2)
        fav_p = max(probs)
        fav_out = max(range(3), key=lambda i: probs[i])
        b = round(fav_p * 10) / 10
        calib_bins.setdefault(b, [0, 0])
        calib_bins[b][1] += 1
        if fav_out == out:
            calib_bins[b][0] += 1

        match = f"{h} vs {a}"[:33]
        print(f"{match:<34}{ts:>6}{f'{hs}-{as_}':>6}"
              f"{f'{evscore[0]}-{evscore[1]}':>7}{gp_modal:>9}{gp_opt:>8}")

    print("─" * 78)
    print(f"\n{'PUNTOS GOLPREDICTOR':<30}")
    print(f"  Con marcador modal (lo que reportamos): {tot_modal_pts} "
          f"({tot_modal_pts / n:.2f}/partido)")
    print(f"  Con marcador óptimo-EV (mismo modelo):   {tot_opt_pts} "
          f"({tot_opt_pts / n:.2f}/partido)  → +{tot_opt_pts - tot_modal_pts} pts "
          f"({(tot_opt_pts / max(tot_modal_pts, 1) - 1) * 100:+.0f}%)")

    print(f"\n{'SESGO DE GOLES (¿predecimos pocos?)':<30}")
    print(f"  Goles reales totales:           {sum_actual_goals:.0f} "
          f"({sum_actual_goals / n:.2f}/partido)")
    print(f"  Goles del marcador modal:       {sum_modal_goals:.0f} "
          f"({sum_modal_goals / n:.2f}/partido)")
    print(f"  Goles esperados del modelo:     {sum_exp_goals:.0f} "
          f"({sum_exp_goals / n:.2f}/partido)")
    print(f"  Partidos donde el modal predijo MENOS goles que la realidad: "
          f"{underpred}/{n}")

    print(f"\n{'CALIDAD 1X2 (motor mezcla)':<30}")
    print(f"  Acierto 1X2:        {hit1x2}/{n} ({hit1x2 / n:.0%})")
    print(f"  Acierto exacto:     {hit_exact}/{n} ({hit_exact / n:.0%})")
    print(f"  Brier medio:        {np.mean(briers_blend):.4f}")
    print(f"  RPS medio:          {np.mean(rpss_blend):.4f} "
          f"(casas ~0.18-0.19)")

    print(f"\n{'CALIBRACIÓN DEL FAVORITO':<30}")
    print("  (si decimos 60%, ¿acierta ~60%?)")
    for b in sorted(calib_bins):
        hits, total = calib_bins[b]
        print(f"   prob≈{b:.0%}: acertó {hits}/{total} ({hits / total:.0%})")


if __name__ == "__main__":
    main()
