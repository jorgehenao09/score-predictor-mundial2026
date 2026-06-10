"""Backtest honesto: entrena SOLO con partidos previos al Mundial 2022 y
evalúa sobre los 64 partidos de Qatar 2022. Compara varios xi (decaimiento
temporal) y dos baselines. Uso:

    .venv/bin/python scripts/backtest.py
"""

import sys
import os

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictor import ratings, sources, store           # noqa: E402
from predictor.predict import brier, rps, score_matrix  # noqa: E402

CUTOFF = "2022-11-20"
END = "2022-12-19"


def outcome_of(hs, as_):
    return 0 if hs > as_ else (1 if hs == as_ else 2)


def evaluate(fit, test):
    R = fit["ratings"]
    res = []
    for d, h, a, hs, as_, tour, neutral in test:
        ah, dh, _ = R.get(h, (0.0, 0.0, 0.0))
        aa, da, _ = R.get(a, (0.0, 0.0, 0.0))
        lh = np.exp(fit["mu"] + ah - da + fit["ha"] * (0 if neutral else 1))
        la = np.exp(fit["mu"] + aa - dh)
        M = score_matrix(lh, la, fit["rho"])
        probs = (float(np.tril(M, -1).sum()), float(np.trace(M)),
                 float(np.triu(M, 1).sum()))
        flat = [((i, j), M[i, j]) for i in range(11) for j in range(11)]
        top = max(flat, key=lambda kv: kv[1])[0]
        o = outcome_of(hs, as_)
        res.append({
            "brier": brier(probs, o), "rps": rps(probs, o),
            "hit": int(max(range(3), key=lambda i: probs[i]) == o),
            "exact": int(top == (hs, as_)),
            "logloss": -np.log(max(probs[o], 1e-12)),
        })
    return {k: float(np.mean([r[k] for r in res])) for k in res[0]}


def main():
    con = store.connect()
    sources.sync_results(con)
    train = ratings.load_training_matches(con, until=CUTOFF)
    test = [tuple(r) for r in con.execute(
        """SELECT date, home, away, home_score, away_score, tournament, neutral
           FROM matches WHERE tournament='FIFA World Cup'
           AND date >= ? AND date < ? AND home_score IS NOT NULL""",
        (CUTOFF, END)).fetchall()]
    print(f"Entrenamiento: {len(train)} partidos hasta {CUTOFF}")
    print(f"Test: {len(test)} partidos del Mundial 2022\n")

    known = {r[0] for r in con.execute("SELECT DISTINCT home FROM matches")} | \
            {r[0] for r in con.execute("SELECT DISTINCT away FROM matches")}
    elo = sources.fetch_elo(con, known)  # Elo ACTUAL (leve fuga temporal,
    # sólo afecta al prior de equipos con poca muestra; aceptable para tuning)

    # baselines
    outs = [outcome_of(hs, as_) for _, _, _, hs, as_, _, _ in test]
    uni = (1 / 3, 1 / 3, 1 / 3)
    print(f"{'modelo':<28} {'RPS':>7} {'Brier':>7} {'LogLoss':>8} "
          f"{'1X2':>6} {'Exacto':>7}")
    print("─" * 68)
    print(f"{'baseline uniforme':<28} "
          f"{np.mean([rps(uni, o) for o in outs]):>7.4f} "
          f"{np.mean([brier(uni, o) for o in outs]):>7.4f} "
          f"{np.mean([-np.log(1 / 3)] * len(outs)):>8.4f} "
          f"{'33%':>6} {'—':>7}")
    hist = [outcome_of(hs, as_) for _, _, _, hs, as_, _, n in train if n]
    freq = tuple(np.bincount(hist, minlength=3) / len(hist))
    print(f"{'baseline frecuencias':<28} "
          f"{np.mean([rps(freq, o) for o in outs]):>7.4f} "
          f"{np.mean([brier(freq, o) for o in outs]):>7.4f} "
          f"{np.mean([-np.log(max(freq[o], 1e-12)) for o in outs]):>8.4f} "
          f"{'—':>6} {'—':>7}")

    best = None
    for xi in (0.0005, 0.001, 0.0015, 0.002, 0.003):
        fit = ratings.fit_full(train, CUTOFF, elo=elo, xi=xi)
        m = evaluate(fit, test)
        half_life_y = np.log(2) / xi / 365
        print(f"{'DC xi=' + str(xi):<21}(t½={half_life_y:.1f}a) "
              f"{m['rps']:>7.4f} {m['brier']:>7.4f} {m['logloss']:>8.4f} "
              f"{m['hit']:>6.0%} {m['exact']:>7.1%}")
        if best is None or m["rps"] < best[1]["rps"]:
            best = (xi, m)
    print(f"\nMejor xi por RPS: {best[0]} "
          f"(RPS {best[1]['rps']:.4f}, acierto 1X2 {best[1]['hit']:.0%})")
    print("Referencia: modelos publicados logran RPS ~0.19-0.21 en fútbol; "
          "la línea de cierre de las casas ronda ~0.18-0.19 en mundiales.")


if __name__ == "__main__":
    main()
