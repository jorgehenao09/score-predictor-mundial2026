"""Convierte ratings + contexto en una predicción de marcador.

Matriz de goles 0..MAX_GOALS con corrección Dixon-Coles, ajustes de contexto
(altitud, descanso), comparación con el mercado de-vigueado y explicación de
los factores en español.
"""

import os
from datetime import date

import numpy as np

from . import calibration, golpredictor, learning, market, store, weather
from .venues import HIGH_ALTITUDE_M, VENUES, altitude, host_side

MAX_GOALS = 10

# Selecciones razonablemente aclimatadas a la altitud (sede andina/altiplano
# o que disputan su localía en altura). Heurística documentada.
ALTITUDE_ACCLIMATED = {"Mexico", "Bolivia", "Ecuador", "Colombia", "Peru"}

REST_PENALTY_PER_DAY = 0.03   # 3% de goles esperados por día de déficit
REST_PENALTY_CAP = 0.09
ALTITUDE_PENALTY = 0.07       # 7% para no aclimatados por encima de 1500 m

# Corrección de volumen de goles. El modelo corre ~12% por debajo del mercado
# en goles esperados (verificado: el mercado esperó más en 7/9 de la fase de
# grupos). HALLAZGO HONESTO del backtest WC2018/2022
# (scripts/validate_improvements.py): el uplift es NEUTRO en puntos
# golpredictor (dentro del ruido en 128 partidos) — mejora la tasa de marcador
# EXACTO (9.4%→12.5%), el RPS y el realismo, sin costar puntos.
# Valor DINÁMICO: lo auto-ajusta a diario `autocalibrate.py` dentro de la banda
# validada [1.05,1.15] y lo persiste en data/tuned_params.json (committeado;
# la BD es efímera en CI). Prioridad: env > archivo > default.
GOAL_UPLIFT_DEFAULT = 1.10
GOAL_UPLIFT_BAND = (1.05, 1.15)
TUNED_PARAMS_PATH = os.path.join(store.BASE_DIR, "data", "tuned_params.json")


def goal_uplift() -> float:
    env = os.getenv("PREDICTOR_GOAL_UPLIFT")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        import json as _json
        with open(TUNED_PARAMS_PATH, encoding="utf-8") as f:
            return float(_json.load(f)["goal_uplift"])
    except Exception:
        return GOAL_UPLIFT_DEFAULT


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


def implied_lambdas(p_home, p_away, rho, p_over=None, point=2.5):
    """Resuelve las medias de gol (λh, λa) implícitas en el mercado: las que
    reproducen el 1X2 de-vigueado y, si hay mercado de totales, P(over).
    El 1X2 es la señal PRIMARIA (exactamente determinada, 2 ecuaciones/2
    incógnitas); el over es secundario. Si al añadir el over el sistema queda
    sobredeterminado e inconsistente y rompe el ajuste del 1X2, se cae de vuelta
    a solo-1X2 en lugar de descartar el mercado entero. Devuelve (λh, λa) o
    None si ni siquiera el 1X2 converge."""
    from scipy.optimize import minimize as _minimize

    # inicialización: total ~2.6 goles repartidos según el sesgo del 1X2
    skew = np.clip(p_home - p_away, -0.6, 0.6)
    x0 = np.log([1.3 * (1 + skew), max(1.3 * (1 - skew), 0.2)])

    def solve(use_over):
        def loss(x):
            lh, la = np.exp(x)
            M = score_matrix(lh, la, rho)
            ph = float(np.tril(M, -1).sum())
            pa = float(np.triu(M, 1).sum())
            err = (ph - p_home) ** 2 + (pa - p_away) ** 2
            if use_over:
                tot = np.add.outer(np.arange(MAX_GOALS + 1),
                                   np.arange(MAX_GOALS + 1))
                err += (float(M[tot > point].sum()) - p_over) ** 2
            return err

        res = _minimize(loss, x0, method="Nelder-Mead",
                        options={"xatol": 1e-4, "fatol": 1e-10, "maxiter": 400})
        lh, la = np.exp(res.x)
        # aceptación: el 1X2 debe quedar clavado (el over es best-effort)
        M = score_matrix(lh, la, rho)
        e_1x2 = ((float(np.tril(M, -1).sum()) - p_home) ** 2
                 + (float(np.triu(M, 1).sum()) - p_away) ** 2)
        if res.success and e_1x2 < 1e-4 and 0.05 < lh < 6 and 0.05 < la < 6:
            return float(lh), float(la)
        return None

    if p_over is not None:
        r = solve(True)
        if r is not None:
            return r
    return solve(False)


def market_matrix(con, home, away, rho):
    """Matriz de goles implícita del mercado (1X2 Shin + totales si hay).
    Devuelve (M, info) o (None, {})."""
    mkt = market.consensus(store.latest_odds(con, home, away))
    if not mkt:
        return None, {}
    mp_h, mp_d, mp_a, n_books, margin = mkt
    tot = market.totals_consensus(store.latest_totals(con, home, away))
    p_over, point = (tot[0], tot[1]) if tot else (None, 2.5)
    lam = implied_lambdas(mp_h, mp_a, rho, p_over=p_over, point=point)
    info = {"market_p_home": mp_h, "market_p_draw": mp_d, "market_p_away": mp_a,
            "n_books": n_books, "margin": margin,
            "market_p_over": p_over, "totals_point": point if tot else None}
    if lam is None:
        return None, info
    return score_matrix(lam[0], lam[1], rho), info


def _kickoff_hour_from_fd(con, home, away, match_date):
    """Hora UTC del kickoff desde el caché de football-data (martj42 solo
    trae fechas). None si no hay token/caché o no aparece el partido."""
    from . import sources
    from .names import canonical
    try:
        fd, _ = sources.fetch_fd_fixtures(con)
    except Exception:
        return None
    known = {home, away}
    for m in fd or []:
        ud = m.get("utcDate", "")
        if not ud.startswith(match_date):
            continue
        h = canonical((m.get("homeTeam") or {}).get("name", ""), known)
        a = canonical((m.get("awayTeam") or {}).get("name", ""), known)
        if h == home and a == away:
            try:
                return int(ud[11:13])
            except ValueError:
                return None
    return None


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
    # Localía POR SEDE (no por la localía nominal del calendario): el host real
    # —quien juega en su país— recibe la ventaja, aunque figure como visitante.
    # Si la sede no está registrada (otras competiciones), se usa el flag del
    # dataset. Sin anfitriones quemados.
    side = host_side(home, away, city)
    if side is None:
        side = "home" if not neutral else "neutral"
    ha_home = fit["ha"] if side == "home" else 0.0
    ha_away = fit["ha"] if side == "away" else 0.0
    lh = np.exp(fit["mu"] + ah - da + ha_home)
    la = np.exp(fit["mu"] + aa - dh + ha_away)
    factors.append(
        f"Fuerza (Dixon-Coles): {home} ataque {ah:+.2f} / defensa {dh:+.2f} · "
        f"{away} ataque {aa:+.2f} / defensa {da:+.2f}")
    pct = (np.exp(fit["ha"]) - 1) * 100
    if side == "home":
        factors.append(f"Ventaja de local aplicada a {home} (juega en casa, "
                       f"+{pct:.0f}% goles esperados)")
    elif side == "away":
        factors.append(f"Ventaja de local aplicada a {away} (juega en casa pese "
                       f"a figurar de visita, +{pct:.0f}% goles esperados)")
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

    # --- clima (calor a la hora del partido)
    ko_h = fixture.get("kickoff_hour")
    if ko_h is None:
        ko_h = _kickoff_hour_from_fd(con, home, away, mdate)
    if ko_h is not None and city:
        t = weather.temp_at(city, mdate, ko_h)
        mult, pen = weather.heat_penalty(t)
        if pen:
            lh *= mult
            la *= mult
            factors.append(f"Calor: {t:.0f}°C previstos en la sede a la hora "
                           f"del partido (-{pen * 100:.0f}% goles esperados)")
        elif t is not None and t >= 28:
            factors.append(f"Clima: {t:.0f}°C previstos a la hora del partido")

    # --- forma reciente (informativa)
    fh, fa = recent_form(con, home, mdate), recent_form(con, away, mdate)
    if fh or fa:
        factors.append(f"Forma últimos 5: {home} [{fh}] · {away} [{fa}] "
                       "(ya ponderada en el modelo por recencia y rival)")

    # --- matriz del modelo (corrección de volumen + calibración empírica)
    uplift = goal_uplift()
    lh *= uplift
    la *= uplift
    M_model = calibration.apply(score_matrix(lh, la, fit["rho"]))
    mp = {"h": float(np.tril(M_model, -1).sum()),
          "d": float(np.trace(M_model)),
          "a": float(np.triu(M_model, 1).sum())}

    # --- matriz implícita del mercado + mezcla
    M_mkt, market_part = market_matrix(con, home, away, fit["rho"])
    blend_w, n_learned = learning.current_blend(con)
    if M_mkt is not None and 0 < blend_w <= 1:
        M = (1 - blend_w) * M_model + blend_w * M_mkt
        tot_note = ""
        if market_part.get("market_p_over") is not None:
            tot_note = (f", over {market_part['totals_point']}: "
                        f"{market_part['market_p_over']:.0%}")
        if n_learned == -1:
            w_note = "peso fijado manualmente"
        elif n_learned >= learning.MIN_RESOLVED:
            w_note = f"peso aprendido de {n_learned} partidos resueltos"
        else:
            w_note = "peso inicial (aprenderá con los partidos resueltos)"
        factors.append(
            f"Marcador final = mezcla {1 - blend_w:.0%} modelo + "
            f"{blend_w:.0%} mercado ({market_part['n_books']} casas{tot_note}; "
            f"{w_note})")
    else:
        M = M_model
    if market_part:
        mh, md, ma = (market_part["market_p_home"],
                      market_part["market_p_draw"],
                      market_part["market_p_away"])
        edge = max(abs(mp["h"] - mh), abs(mp["d"] - md), abs(mp["a"] - ma))
        factors.append(
            f"Mercado (Shin, {market_part['n_books']} casas): "
            f"{mh:.0%}/{md:.0%}/{ma:.0%} vs modelo puro "
            f"{mp['h']:.0%}/{mp['d']:.0%}/{mp['a']:.0%} "
            f"(divergencia máx {edge * 100:.0f} pts)")

    p_home = float(np.tril(M, -1).sum())
    p_draw = float(np.trace(M))
    p_away = float(np.triu(M, 1).sum())
    flat = [((i, j), M[i, j]) for i in range(MAX_GOALS + 1)
            for j in range(MAX_GOALS + 1)]
    flat.sort(key=lambda kv: -kv[1])
    top = flat[:5]
    (ti, tj), tp = top[0]

    # --- marcador óptimo para golpredictor (maximiza puntos esperados; suele
    #     diferir del modal porque equilibra resultado + goles + diferencia)
    knockout = golpredictor.is_knockout(mdate)
    (gi, gj), gp_ev = golpredictor.ev_optimal_score(M, knockout=knockout)
    gp_score = f"{gi}-{gj}"
    gp_prob = float(M[gi, gj])
    if gp_score != f"{ti}-{tj}":
        factors.append(
            f"Óptimo golpredictor: {gp_score} (maximiza puntos esperados, "
            f"{gp_ev:.1f} pts esp.) — distinto del más probable {ti}-{tj}")

    # --- pick "remontada" (versión ligera de estrategia de ranking): cuando vas
    #     detrás, el valor está donde el MODELO discrepa del mercado/campo
    contrarian = None
    if market_part and market_part.get("market_p_home") is not None:
        contrarian = golpredictor.contrarian_pick(
            M,
            (mp["h"], mp["d"], mp["a"]),
            (market_part["market_p_home"], market_part["market_p_draw"],
             market_part["market_p_away"]),
            knockout=knockout)
        if contrarian and contrarian["score"] == gp_score:
            contrarian = None   # no aporta nada si coincide con el EV-óptimo

    # --- confianza (el acuerdo modelo-puro vs mercado informa fiabilidad)
    max_p = max(p_home, p_draw, p_away)
    sparse = min(eh, ea) < 10
    agree = market_part and abs(
        max(mp["h"], mp["d"], mp["a"]) -
        max(market_part.get("market_p_home", 0),
            market_part.get("market_p_draw", 0),
            market_part.get("market_p_away", 0))) < 0.08
    if sparse or max_p < 0.40:
        conf = "BAJA"
    elif (max_p > 0.55 and min(eh, ea) > 25) or agree:
        conf = "ALTA"
    else:
        conf = "MEDIA"
    if sparse:
        factors.append(f"Aviso: muestra efectiva escasa "
                       f"({home}: {eh:.0f}, {away}: {ea:.0f} partidos ponderados)")

    market_part.pop("market_p_over", None)
    market_part.pop("totals_point", None)

    # --- descomposición para el modal de detalle del dashboard
    _ht = [("Base", float(fit["mu"])), (f"Ataque {home}", float(ah)),
           (f"Defensa {away}", float(-da))]
    if ha_home:
        _ht.append(("Ventaja local", float(ha_home)))
    _ht.append(("Uplift goles", float(np.log(uplift))))
    _at = [("Base", float(fit["mu"])), (f"Ataque {away}", float(aa)),
           (f"Defensa {home}", float(-dh))]
    if ha_away:
        _at.append(("Ventaja local", float(ha_away)))
    _at.append(("Uplift goles", float(np.log(uplift))))
    _mkt = None
    if market_part and market_part.get("market_p_home") is not None:
        _mkt = (market_part["market_p_home"], market_part["market_p_draw"],
                market_part["market_p_away"])
    breakdown = {
        "lh": float(lh), "la": float(la),
        "home_terms": _ht, "away_terms": _at,
        "matrix6": [[float(M[i, j]) for j in range(6)] for i in range(6)],
        "model_probs": (mp["h"], mp["d"], mp["a"]),
        "market_probs": _mkt,
        "final_probs": (p_home, p_draw, p_away),
        "blend_w": float(blend_w) if M_mkt is not None else 0.0,
        "gp_cell": (gi, gj), "modal_cell": (ti, tj),
    }

    return {
        "match_date": mdate, "home": home, "away": away, "city": city,
        "exp_home": float(lh), "exp_away": float(la),
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "model_p_home": mp["h"], "model_p_draw": mp["d"],
        "model_p_away": mp["a"],
        "top_score": f"{ti}-{tj}", "top_score_prob": float(tp),
        "top_scores": [(f"{i}-{j}", float(p)) for (i, j), p in top],
        "gp_score": gp_score, "gp_score_prob": gp_prob, "gp_ev": float(gp_ev),
        "breakdown": breakdown,
        "contrarian": contrarian,
        "knockout": knockout,
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
