"""Convierte ratings + contexto en una predicción de marcador.

Matriz de goles 0..MAX_GOALS con corrección Dixon-Coles, ajustes de contexto
(altitud, descanso), comparación con el mercado de-vigueado y explicación de
los factores en español.
"""

from datetime import date

import numpy as np

from . import market, store
from .venues import HIGH_ALTITUDE_M, VENUES, altitude

MAX_GOALS = 10

# Selecciones razonablemente aclimatadas a la altitud (sede andina/altiplano
# o que disputan su localía en altura). Heurística documentada.
ALTITUDE_ACCLIMATED = {"Mexico", "Bolivia", "Ecuador", "Colombia", "Peru"}

REST_PENALTY_PER_DAY = 0.03   # 3% de goles esperados por día de déficit
REST_PENALTY_CAP = 0.09
ALTITUDE_PENALTY = 0.07       # 7% para no aclimatados por encima de 1500 m


def _poisson_vec(lam, n=MAX_GOALS):
    k = np.arange(n + 1)
    logp = k * np.log(lam) - lam - np.array([np.sum(np.log(np.arange(1, x + 1))) for x in k])
    return np.exp(logp)


def score_matrix(lh, la, rho):
    """Matriz P(home=i, away=j) con corrección DC en marcadores bajos."""
    M = np.outer(_poisson_vec(lh), _poisson_vec(la))
    M[0, 0] *= 1 - lh * la * rho
    M[0, 1] *= 1 + lh * rho
    M[1, 0] *= 1 + la * rho
    M[1, 1] *= 1 - rho
    return M / M.sum()


def rest_days(con, team, match_date):
    row = con.execute(
        """SELECT MAX(date) FROM matches
           WHERE (home=? OR away=?) AND date < ? AND home_score IS NOT NULL""",
        (team, team, match_date)).fetchone()
    if not row or not row[0]:
        return None
    return (date.fromisoformat(match_date) - date.fromisoformat(row[0])).days


def recent_form(con, team, match_date, n=5):
    rows = con.execute(
        """SELECT home, home_score, away_score FROM matches
           WHERE (home=? OR away=?) AND date < ? AND home_score IS NOT NULL
           ORDER BY date DESC LIMIT ?""", (team, team, match_date, n)).fetchall()
    out = []
    for home, hs, as_ in rows:
        gf, gc = (hs, as_) if home == team else (as_, hs)
        out.append("G" if gf > gc else ("E" if gf == gc else "P"))
    return "".join(reversed(out))  # cronológico: G=ganó E=empató P=perdió


def predict_match(con, fit, fixture):
    """fixture: dict con date, home, away, city, country, neutral.
    Devuelve dict con predicción completa + explicación en español."""
    home, away = fixture["home"], fixture["away"]
    mdate, city = fixture["date"], fixture.get("city", "")
    neutral = fixture.get("neutral", 1)
    R = fit["ratings"]
    ah, dh, eh = R.get(home, (0.0, 0.0, 0.0))
    aa, da, ea = R.get(away, (0.0, 0.0, 0.0))

    factors = []
    lh = np.exp(fit["mu"] + ah - da + fit["ha"] * (0 if neutral else 1))
    la = np.exp(fit["mu"] + aa - dh)
    factors.append(
        f"Fuerza (Dixon-Coles): {home} ataque {ah:+.2f} / defensa {dh:+.2f} · "
        f"{away} ataque {aa:+.2f} / defensa {da:+.2f}")
    if not neutral:
        local = home if fixture.get("country", "") != "" else home
        factors.append(f"Ventaja de local aplicada a {local} "
                       f"(+{(np.exp(fit['ha']) - 1) * 100:.0f}% goles esperados)")
    else:
        factors.append("Cancha neutral: sin ventaja de local")

    # --- altitud
    alt = altitude(city)
    if alt >= HIGH_ALTITUDE_M:
        v = VENUES.get(city)
        stadium = v[0] if v else city
        if home not in ALTITUDE_ACCLIMATED:
            lh *= 1 - ALTITUDE_PENALTY
        if away not in ALTITUDE_ACCLIMATED:
            la *= 1 - ALTITUDE_PENALTY
        pen = [t for t in (home, away) if t not in ALTITUDE_ACCLIMATED]
        if pen:
            factors.append(f"Altitud: {stadium} ({alt} m) penaliza a "
                           f"{' y '.join(pen)} (-{ALTITUDE_PENALTY * 100:.0f}%)")

    # --- descanso
    rh_, ra_ = rest_days(con, home, mdate), rest_days(con, away, mdate)
    if rh_ is not None and ra_ is not None and rh_ <= 30 and ra_ <= 30:
        diff = rh_ - ra_
        if abs(diff) >= 2:
            tired = home if diff < 0 else away
            pen = min(abs(diff) * REST_PENALTY_PER_DAY, REST_PENALTY_CAP)
            if tired == home:
                lh *= 1 - pen
            else:
                la *= 1 - pen
            factors.append(f"Descanso: {tired} llega con {abs(diff)} días menos "
                           f"de recuperación (-{pen * 100:.0f}%)")

    # --- forma reciente (informativa)
    fh, fa = recent_form(con, home, mdate), recent_form(con, away, mdate)
    if fh or fa:
        factors.append(f"Forma últimos 5: {home} [{fh}] · {away} [{fa}] "
                       "(ya ponderada en el modelo por recencia y rival)")

    # --- matriz de goles
    M = score_matrix(lh, la, fit["rho"])
    p_home = float(np.tril(M, -1).sum())
    p_draw = float(np.trace(M))
    p_away = float(np.triu(M, 1).sum())
    flat = [((i, j), M[i, j]) for i in range(MAX_GOALS + 1)
            for j in range(MAX_GOALS + 1)]
    flat.sort(key=lambda kv: -kv[1])
    top = flat[:5]
    (ti, tj), tp = top[0]

    # --- mercado
    mkt = market.consensus(store.latest_odds(con, home, away))
    market_part = {}
    if mkt:
        mp_h, mp_d, mp_a, n_books, margin = mkt
        market_part = {"market_p_home": mp_h, "market_p_draw": mp_d,
                       "market_p_away": mp_a, "n_books": n_books,
                       "margin": margin}
        edge = max(abs(p_home - mp_h), abs(p_draw - mp_d), abs(p_away - mp_a))
        factors.append(
            f"Mercado (Shin, {n_books} casas): {mp_h:.0%}/{mp_d:.0%}/{mp_a:.0%} "
            f"vs modelo {p_home:.0%}/{p_draw:.0%}/{p_away:.0%} "
            f"(divergencia máx {edge * 100:.0f} pts)")

    # --- confianza
    max_p = max(p_home, p_draw, p_away)
    sparse = min(eh, ea) < 10
    agree = mkt and abs(max_p - max(mkt[0], mkt[1], mkt[2])) < 0.08
    if sparse or max_p < 0.40:
        conf = "BAJA"
    elif (max_p > 0.55 and min(eh, ea) > 25) or agree:
        conf = "ALTA"
    else:
        conf = "MEDIA"
    if sparse:
        factors.append(f"Aviso: muestra efectiva escasa "
                       f"({home}: {eh:.0f}, {away}: {ea:.0f} partidos ponderados)")

    return {
        "match_date": mdate, "home": home, "away": away, "city": city,
        "exp_home": float(lh), "exp_away": float(la),
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "top_score": f"{ti}-{tj}", "top_score_prob": float(tp),
        "top_scores": [(f"{i}-{j}", float(p)) for (i, j), p in top],
        "confidence": conf,
        "explanation": " | ".join(factors),
        "factors": factors,
        **market_part,
    }


# ---------------------------------------------------------------- evaluación

def rps(probs, outcome):
    """Ranked Probability Score para 1X2. probs=(pH,pD,pA),
    outcome: 0=local, 1=empate, 2=visita. Menor es mejor."""
    c = np.cumsum(probs)
    o = np.zeros(3)
    o[outcome] = 1
    oc = np.cumsum(o)
    return float(np.sum((c[:2] - oc[:2]) ** 2) / 2)


def brier(probs, outcome):
    o = np.zeros(3)
    o[outcome] = 1
    return float(np.sum((np.array(probs) - o) ** 2))
