"""Cálculos del dashboard, sin HTML: aciertos y calibración por competición.
Reutiliza la lógica de `precision` y el estado vivo (fit, learning, params)."""
import numpy as np

from . import golpredictor as gp
from . import learning, store
from .predict import goal_uplift, rps

# Registro de competiciones: para escalar, añadir una entrada y su snapshot.
# Hoy solo Mundial 2026 (su calibración sale del estado vivo del modelo).
BASE = {  # defaults universales del modelo (no se recalculan)
    "xi": "0.0005", "rho": "—", "local": "—", "blend": "0.50", "uplift": "1.10",
    "autotune": "—",
}


def calibration(con):
    """(base, competiciones) para la tabla comparativa de la pestaña Modelo.
    Cada competición = una columna; hoy solo WC2026 desde el fit/learning vivos."""
    fit = con.execute(
        "SELECT xi, rho, home_adv FROM fits ORDER BY id DESC LIMIT 1").fetchone()
    xi, rho, ha = fit if fit else (0.0005, 0.0, 0.0)
    blend, _ = learning.current_blend(con)
    wc2026 = {
        "xi": f"{xi:.4f}",
        "rho": f"{rho:+.3f}",
        "local": f"+{(np.exp(ha) - 1) * 100:.0f}% (por sede)",
        "blend": f"{blend:.2f} (aprendido)",
        "uplift": f"{goal_uplift():.2f}",
        "autotune": "mezcla sí · resto vigilado",
    }
    competitions = [{"id": "wc2026", "name": "Mundial 2026", "params": wc2026}]
    return BASE, competitions


def _resolved_rows(con):
    return con.execute(
        """SELECT p.home, p.away, p.match_date, p.p_home, p.p_draw, p.p_away,
                  p.top_score, m.home_score, m.away_score, p.gp_score
           FROM predictions p JOIN matches m
             ON m.home=p.home AND m.away=p.away AND m.date=p.match_date
           WHERE m.home_score IS NOT NULL
             AND p.id IN (SELECT MAX(id) FROM predictions
                          WHERE substr(created_at,1,10) <= match_date
                          GROUP BY home, away, match_date)
           ORDER BY p.match_date""").fetchall()


def _median(xs):
    xs = sorted(x for x in xs if x)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _closing_odds(con, home, away, outcome):
    """Cuota mediana de cierre para el outcome (0 local,1 empate,2 visita)."""
    col = ("home_odds", "draw_odds", "away_odds")[outcome]
    rows = con.execute(
        f"""SELECT {col} FROM odds_snapshots WHERE home=? AND away=?
            AND fetched_at=(SELECT MAX(fetched_at) FROM odds_snapshots
                            WHERE home=? AND away=? AND fetched_at<=commence_time)""",
        (home, away, home, away)).fetchall()
    return _median([r[0] for r in rows])


def accuracy(con):
    """Métricas (escalables, sin posición de polla) + historial resuelto.
    Devuelve dict: hits_1x2%, exact%, gp_points, rps, roi%, n, history[]."""
    rows = _resolved_rows(con)
    if not rows:
        return {"n": 0, "history": []}
    n = len(rows)
    hits = exact = 0
    rps_sum = 0.0
    modal_pts = 0
    staked = ret = 0
    STAKE = 10000
    history = []
    for (h, a, d, ph, pd, pa, ts, hs, as_, gps) in rows:
        outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
        probs = (ph, pd, pa)
        verdict = max(range(3), key=lambda i: probs[i])
        ok = verdict == outcome
        hits += ok
        rps_sum += rps(probs, outcome)
        is_exact = ts == f"{hs}-{as_}"
        exact += is_exact
        ko = gp.is_knockout(d)
        pick = tuple(map(int, (gps if gps else ts).split("-")))
        pts = gp.points(pick, (hs, as_), ko)
        modal_pts += pts
        o = _closing_odds(con, h, a, verdict)
        if o:
            staked += STAKE
            ret += STAKE * o if ok else 0
        vlabel = (h if verdict == 0 else a if verdict == 2 else "Empate")
        history.append({"date": d, "home": h, "away": a, "verdict": vlabel,
                        "real": f"{hs}-{as_}", "ok": ok, "pts": pts})
    roi = ((ret - staked) / staked * 100) if staked else None
    return {
        "n": n,
        "hits_1x2": hits / n * 100,
        "exact": exact / n * 100,
        "gp_points": modal_pts,
        "rps": rps_sum / n,
        "roi": roi,
        "history": list(reversed(history)),
    }
