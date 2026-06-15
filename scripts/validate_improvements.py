"""Valida las mejoras (marcador óptimo-EV + corrección de volumen de goles)
en los Mundiales 2018 y 2022, entrenando SOLO con datos previos a cada uno.

Para cada factor de uplift mide, sobre los 128 partidos de esos dos Mundiales:
  - puntos golpredictor con marcador MODAL vs con marcador ÓPTIMO-EV
  - RPS del 1X2 (no debe empeorar)
  - acierto de marcador exacto

Así el dato decide el uplift, en vez de adivinarlo.
Uso: .venv/bin/python scripts/validate_improvements.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictor import ratings, sources, store              # noqa: E402
from predictor.predict import score_matrix, rps            # noqa: E402
from predictor import golpredictor as gp                    # noqa: E402

CUPS = [("2018-06-14", "2018-07-16"), ("2022-11-20", "2022-12-19")]
UPLIFTS = [1.00, 1.05, 1.10, 1.15, 1.20]


def main():
    con = store.connect()
    sources.sync_results(con)
    known = ({r[0] for r in con.execute("SELECT DISTINCT home FROM matches")} |
             {r[0] for r in con.execute("SELECT DISTINCT away FROM matches")})
    elo = sources.fetch_elo(con, known)

    # pre-ajustar un modelo por Mundial (con datos previos)
    fits = []
    tests = []
    for cutoff, end in CUPS:
        train = ratings.load_training_matches(con, until=cutoff)
        fits.append(ratings.fit_full(train, cutoff, elo=elo))
        tests.append([tuple(r) for r in con.execute(
            """SELECT home, away, home_score, away_score, neutral
               FROM matches WHERE tournament='FIFA World Cup'
               AND date >= ? AND date < ? AND home_score IS NOT NULL""",
            (cutoff, end)).fetchall()])
    n = sum(len(t) for t in tests)
    print(f"Validación sobre {n} partidos (WC2018+WC2022)\n")
    print(f"{'uplift':>7}{'gp_modal':>10}{'gp_EVopt':>10}{'mejora':>8}"
          f"{'RPS':>8}{'exact%':>8}{'goles/p':>9}")
    print("─" * 60)

    base_rps = None
    for up in UPLIFTS:
        modal_pts = opt_pts = 0
        rpss = []
        exact = 0
        goals_pred = 0
        for fit, test in zip(fits, tests):
            rho = fit["rho"]
            R = fit["ratings"]
            for h, a, hs, as_, neutral in test:
                ah, dh, _ = R.get(h, (0.0, 0.0, 0.0))
                aa, da, _ = R.get(a, (0.0, 0.0, 0.0))
                lh = np.exp(fit["mu"] + ah - da + fit["ha"] * (0 if neutral else 1)) * up
                la = np.exp(fit["mu"] + aa - dh) * up
                M = score_matrix(lh, la, rho)
                modal = max(((i, j) for i in range(11) for j in range(11)),
                            key=lambda ij: M[ij])
                evs, _ = gp.ev_optimal_score(M)
                modal_pts += gp.points(modal, (hs, as_))
                opt_pts += gp.points(evs, (hs, as_))
                goals_pred += sum(evs)
                if modal == (hs, as_):
                    exact += 1
                probs = (float(np.tril(M, -1).sum()), float(np.trace(M)),
                         float(np.triu(M, 1).sum()))
                o = 0 if hs > as_ else (1 if hs == as_ else 2)
                rpss.append(rps(probs, o))
        rps_m = np.mean(rpss)
        if base_rps is None:
            base_rps = rps_m
        improve = (opt_pts / modal_pts - 1) * 100
        flag = "" if rps_m <= base_rps + 0.001 else "  ⚠RPS"
        print(f"{up:>7.2f}{modal_pts:>10}{opt_pts:>10}{improve:>7.0f}%"
              f"{rps_m:>8.4f}{exact / n * 100:>7.1f}%{goals_pred / n:>9.2f}{flag}")

    print("\nLectura: elegir el uplift que MAXIMIZA gp_EVopt sin que el RPS "
          "suba respecto a uplift=1.00.")


if __name__ == "__main__":
    main()
