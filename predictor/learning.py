"""Autoaprendizaje del peso de mezcla modelo-mercado.

Los marcadores de cierre (data/notified/*.cierre.json) guardan, por partido,
las probabilidades del modelo puro y del mercado en el momento del informe.
Cuando esos partidos se resuelven, este módulo busca el peso w que minimiza
el RPS de la mezcla (1-w)·modelo + w·mercado sobre lo ya jugado, y lo encoge
hacia 0.5 con PRIOR_K pseudo-partidos (poca muestra → casi 0.5; mucha →
manda el dato). Los marcadores viven commiteados en el repo, así que la
memoria es la misma en local y en la nube.

Prioridad: env PREDICTOR_BLEND (override manual) > peso aprendido > 0.5.
"""

import glob
import json
import os

from . import store

NOTIFIED_DIR = os.path.join(store.BASE_DIR, "data", "notified")
GRID = [i / 20 for i in range(21)]
PRIOR_K = 10      # pseudo-partidos hacia w=0.5
MIN_RESOLVED = 6  # antes de esto, w=0.5 fijo

_cache = None


def _rps(probs, outcome):
    c1 = probs[0]
    c2 = probs[0] + probs[1]
    o1 = 1.0 if outcome == 0 else 0.0
    o2 = 1.0 if outcome <= 1 else 0.0
    return ((c1 - o1) ** 2 + (c2 - o2) ** 2) / 2


def resolved_rows(con):
    """[(model_probs, market_probs, outcome)] de cierres ya resueltos."""
    rows = []
    for path in glob.glob(os.path.join(NOTIFIED_DIR, "*.cierre.json")):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        model, market = d.get("model"), d.get("market")
        date, home, away = d.get("date"), d.get("home_c"), d.get("away_c")
        if not (model and market and date and home and away):
            continue
        r = con.execute(
            """SELECT home_score, away_score FROM matches
               WHERE date=? AND home=? AND away=?
               AND home_score IS NOT NULL""", (date, home, away)).fetchone()
        if not r:
            continue
        outcome = 0 if r[0] > r[1] else (1 if r[0] == r[1] else 2)
        rows.append(((model["ph"], model["pd"], model["pa"]),
                     (market["ph"], market["pd"], market["pa"]), outcome))
    return rows


def current_blend(con):
    """(peso_de_mezcla, n_partidos_aprendidos). Cacheado por proceso."""
    global _cache
    env = os.getenv("PREDICTOR_BLEND")
    if env:
        try:
            return max(0.0, min(1.0, float(env))), -1  # -1 = override manual
        except ValueError:
            pass
    if _cache is not None:
        return _cache
    rows = resolved_rows(con)
    n = len(rows)
    if n < MIN_RESOLVED:
        _cache = (0.5, n)
        return _cache

    def mean_rps(w):
        tot = 0.0
        for pm, pk, o in rows:
            mix = [(1 - w) * pm[i] + w * pk[i] for i in range(3)]
            tot += _rps(mix, o)
        return tot / n

    best = min(GRID, key=mean_rps)
    w = (n * best + PRIOR_K * 0.5) / (n + PRIOR_K)
    _cache = (round(w, 3), n)
    return _cache
