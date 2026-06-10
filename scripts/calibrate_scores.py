"""Genera predictor/calibration_table.json midiendo los sesgos por marcador
de Poisson-DC con ajustes rolling FUERA DE MUESTRA, y valida en WC2018+WC2022
que la calibración mejora (si no mejora, no escribe la tabla).

Método:
  - Para cada año Y en 2010..2025: ajustar con datos < Y-01-01 y predecir
    todos los internacionales de ese año (sin contexto, solo el motor puro).
  - Acumular masa esperada E[i,j] y conteos observados O[i,j] por marcador.
  - ratio crudo = O/E; encogido: r = (O + k·E) / (E·(1+k)) con k de
    pseudo-cuentas (más k = más conservador).
  - Validación: con la tabla puesta, ¿mejora exact-score y RPS en WC2018/22?

Uso: .venv/bin/python scripts/calibrate_scores.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictor import ratings, sources, store               # noqa: E402
from predictor.calibration import CAP, _TABLE_PATH           # noqa: E402
from predictor.predict import brier, rps, score_matrix       # noqa: E402

YEARS = range(2010, 2026)
SHRINK_K = 1.0   # peso del prior "ratio=1" relativo a la masa esperada


def fit_for(con, until, elo):
    train = ratings.load_training_matches(con, until=until)
    return ratings.fit_full(train, until, elo=elo)


def matrices_for(fit, test):
    R = fit["ratings"]
    for d, h, a, hs, as_, tour, neutral in test:
        ah, dh, _ = R.get(h, (0.0, 0.0, 0.0))
        aa, da, _ = R.get(a, (0.0, 0.0, 0.0))
        lh = np.exp(fit["mu"] + ah - da + fit["ha"] * (0 if neutral else 1))
        la = np.exp(fit["mu"] + aa - dh)
        yield score_matrix(lh, la, fit["rho"]), hs, as_


def main():
    con = store.connect()
    sources.sync_results(con)
    known = ({r[0] for r in con.execute("SELECT DISTINCT home FROM matches")} |
             {r[0] for r in con.execute("SELECT DISTINCT away FROM matches")})
    elo = sources.fetch_elo(con, known)

    E = np.zeros((CAP + 1, CAP + 1))
    O = np.zeros((CAP + 1, CAP + 1))
    n_used = 0
    for y in YEARS:
        until = f"{y}-01-01"
        test = [tuple(r) for r in con.execute(
            """SELECT date, home, away, home_score, away_score, tournament,
               neutral FROM matches WHERE home_score IS NOT NULL
               AND date >= ? AND date < ?""",
            (until, f"{y + 1}-01-01")).fetchall()]
        if not test:
            continue
        fit = fit_for(con, until, elo)
        for M, hs, as_ in matrices_for(fit, test):
            E += M[:CAP + 1, :CAP + 1]
            if hs <= CAP and as_ <= CAP:
                O[hs, as_] += 1
            n_used += 1
        print(f"  {y}: {len(test)} partidos (acumulado {n_used})")

    ratio_raw = np.where(E > 0, O / np.maximum(E, 1e-9), 1.0)
    ratio = (O + SHRINK_K * E) / (E * (1 + SHRINK_K))
    print("\nRatios encogidos (obs/esp), filas=goles local 0..3, "
          "cols=goles visita 0..3:")
    for i in range(4):
        print("   " + "  ".join(f"{ratio[i, j]:.3f}" for j in range(4)))
    print(f"  (crudo 1-1: {ratio_raw[1, 1]:.3f}, 0-0: {ratio_raw[0, 0]:.3f})")

    # ---- validación en WC2018 + WC2022 con/sin tabla
    def evaluate(with_table):
        out = {"rps": [], "brier": [], "hit": [], "exact": []}
        for cutoff, end in (("2018-06-14", "2018-07-16"),
                            ("2022-11-20", "2022-12-19")):
            test = [tuple(r) for r in con.execute(
                """SELECT date, home, away, home_score, away_score, tournament,
                   neutral FROM matches WHERE tournament='FIFA World Cup'
                   AND date >= ? AND date < ? AND home_score IS NOT NULL""",
                (cutoff, end)).fetchall()]
            fit = fit_for(con, cutoff, elo)
            for M, hs, as_ in matrices_for(fit, test):
                if with_table:
                    Mc = M.copy()
                    Mc[:CAP + 1, :CAP + 1] *= ratio
                    M = Mc / Mc.sum()
                probs = (float(np.tril(M, -1).sum()), float(np.trace(M)),
                         float(np.triu(M, 1).sum()))
                o = 0 if hs > as_ else (1 if hs == as_ else 2)
                top = max(((i, j) for i in range(11) for j in range(11)),
                          key=lambda ij: M[ij])
                out["rps"].append(rps(probs, o))
                out["brier"].append(brier(probs, o))
                out["hit"].append(max(range(3), key=lambda k: probs[k]) == o)
                out["exact"].append(top == (hs, as_))
        return {k: float(np.mean(v)) for k, v in out.items()}

    base = evaluate(False)
    cal = evaluate(True)
    print(f"\nValidación WC2018+WC2022 ({'mejora' if cal['rps'] <= base['rps'] else 'EMPEORA'}):")
    print(f"  sin tabla: RPS {base['rps']:.4f} · exacto {base['exact']:.1%} "
          f"· 1X2 {base['hit']:.0%}")
    print(f"  con tabla: RPS {cal['rps']:.4f} · exacto {cal['exact']:.1%} "
          f"· 1X2 {cal['hit']:.0%}")

    if cal["exact"] >= base["exact"] and cal["rps"] <= base["rps"] + 0.0005:
        table = {f"{i}-{j}": round(float(ratio[i, j]), 4)
                 for i in range(CAP + 1) for j in range(CAP + 1)}
        with open(_TABLE_PATH, "w", encoding="utf-8") as f:
            json.dump({"generated_from": f"{n_used} partidos OOS 2010-2025",
                       "shrink_k": SHRINK_K, "ratios": table}, f, indent=1)
        print(f"\nTabla escrita en {_TABLE_PATH}")
    else:
        print("\nNO se escribió la tabla (no mejora en validación).")


if __name__ == "__main__":
    main()
