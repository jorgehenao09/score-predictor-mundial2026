"""Motor de ratings: Dixon-Coles ponderado en el tiempo.

- Poisson bivariado independiente con corrección rho de Dixon-Coles para
  marcadores bajos (0-0, 1-0, 0-1, 1-1).
- Cada selección tiene fuerza OFENSIVA (attack) y DEFENSIVA (defense).
- Peso de cada partido = exp(-xi * días_transcurridos) * importancia_torneo.
- Regularización ridge: encoge hacia la media a selecciones con pocos datos.
- Prior Elo: para selecciones con poca muestra efectiva, la fuerza se mezcla
  con la implícita en su rating Elo (regresión sobre los equipos con datos).

Ajuste en dos pasos (estándar en la práctica):
  1) MLE Poisson penalizado con gradiente analítico (L-BFGS-B).
  2) rho por verosimilitud perfilada en 1-D con las fuerzas fijas.
"""

from datetime import date

import numpy as np
from scipy.optimize import minimize, minimize_scalar

# Importancia por torneo (multiplicador del peso). Heurística tipo K de Elo.
TOURNAMENT_W = {
    "FIFA World Cup": 2.0,
    "FIFA World Cup qualification": 1.5,
    "UEFA Euro": 1.8, "Copa América": 1.8, "African Cup of Nations": 1.6,
    "AFC Asian Cup": 1.6, "Gold Cup": 1.5, "UEFA Nations League": 1.3,
    "UEFA Euro qualification": 1.3, "African Cup of Nations qualification": 1.2,
    "AFC Asian Cup qualification": 1.2, "Gold Cup qualification": 1.2,
    "Copa América qualification": 1.2,
    "Friendly": 0.6,
}
DEFAULT_TOURNAMENT_W = 1.0

XI_DEFAULT = 0.0005      # decaimiento diario: vida media ~ 3.8 años
# Validado por backtest en WC2018 y WC2022 (ver scripts/backtest.py):
# RPS 0.217/0.216, acierto 1X2 56%/48%, marcador exacto 9.4% en ambos.
RIDGE = 5.0              # fuerza del encogimiento hacia la media
ELO_BLEND_K = 10.0       # muestra efectiva a la que el prior Elo pesa 50%
MIN_YEAR = 1990          # con xi>=0.001, antes de 1990 el peso es ~0


def _prepare(matches, ref_date, xi):
    """matches: lista (date_str, home, away, hs, as_, tournament, neutral).
    Devuelve arrays y el índice de equipos."""
    teams = sorted({m[1] for m in matches} | {m[2] for m in matches})
    idx = {t: i for i, t in enumerate(teams)}
    ref = date.fromisoformat(ref_date)
    h, a, gh, ga, w, home_flag = [], [], [], [], [], []
    for d, ht, at, hs, as_, tour, neutral in matches:
        dd = (ref - date.fromisoformat(d)).days
        if dd < 0:
            continue
        h.append(idx[ht]); a.append(idx[at]); gh.append(hs); ga.append(as_)
        w.append(np.exp(-xi * dd) * TOURNAMENT_W.get(tour, DEFAULT_TOURNAMENT_W))
        home_flag.append(0.0 if neutral else 1.0)
    return (teams, idx, np.array(h), np.array(a),
            np.array(gh, dtype=float), np.array(ga, dtype=float),
            np.array(w), np.array(home_flag))


def fit_poisson(matches, ref_date, xi=XI_DEFAULT, ridge=RIDGE):
    """Paso 1: MLE Poisson penalizado. Devuelve dict con mu, ha, att, def,
    teams, eff_matches."""
    teams, idx, h, a, gh, ga, w, hf = _prepare(matches, ref_date, xi)
    T = len(teams)
    W = w.sum()

    def unpack(x):
        return x[0], x[1], x[2:2 + T], x[2 + T:]

    def negloglik(x):
        mu, ha, att, dfn = unpack(x)
        lh = np.exp(mu + att[h] - dfn[a] + ha * hf)
        la = np.exp(mu + att[a] - dfn[h])
        ll = np.sum(w * (gh * np.log(lh) - lh + ga * np.log(la) - la))
        pen = ridge * (np.sum(att ** 2) + np.sum(dfn ** 2))
        # gradiente analítico
        rh = w * (gh - lh)   # residuo casa
        ra = w * (ga - la)   # residuo visita
        g = np.zeros_like(x)
        g[0] = np.sum(rh) + np.sum(ra)
        g[1] = np.sum(rh * hf)
        np.add.at(g, 2 + h, rh)          # att del local
        np.add.at(g, 2 + a, ra)          # att del visitante
        np.add.at(g, 2 + T + a, -rh)     # def del visitante
        np.add.at(g, 2 + T + h, -ra)     # def del local
        g[2:2 + T] -= 2 * ridge * att
        g[2 + T:] -= 2 * ridge * dfn
        return -(ll - pen) / W, -g / W

    x0 = np.zeros(2 + 2 * T)
    x0[0] = np.log(max(gh.mean(), 0.1))
    res = minimize(negloglik, x0, jac=True, method="L-BFGS-B",
                   options={"maxiter": 500})
    mu, ha, att, dfn = unpack(res.x)
    eff = np.zeros(T)
    np.add.at(eff, h, w)
    np.add.at(eff, a, w)
    return {"teams": teams, "idx": idx, "mu": mu, "ha": ha,
            "att": att, "def": dfn, "eff": eff, "converged": res.success,
            "arrays": (h, a, gh, ga, w, hf)}


def fit_rho(fit):
    """Paso 2: rho de Dixon-Coles por verosimilitud perfilada (sólo afecta a
    marcadores 0-0, 1-0, 0-1, 1-1)."""
    h, a, gh, ga, w, hf = fit["arrays"]
    mu, ha, att, dfn = fit["mu"], fit["ha"], fit["att"], fit["def"]
    lh = np.exp(mu + att[h] - dfn[a] + ha * hf)
    la = np.exp(mu + att[a] - dfn[h])
    low = (gh <= 1) & (ga <= 1)
    lh, la, gh_l, ga_l, w_l = lh[low], la[low], gh[low], ga[low], w[low]

    def nll(rho):
        tau = np.ones_like(lh)
        m00 = (gh_l == 0) & (ga_l == 0)
        m01 = (gh_l == 0) & (ga_l == 1)
        m10 = (gh_l == 1) & (ga_l == 0)
        m11 = (gh_l == 1) & (ga_l == 1)
        tau[m00] = 1 - lh[m00] * la[m00] * rho
        tau[m01] = 1 + lh[m01] * rho
        tau[m10] = 1 + la[m10] * rho
        tau[m11] = 1 - rho
        if np.any(tau <= 0):
            return 1e9
        return -np.sum(w_l * np.log(tau))

    res = minimize_scalar(nll, bounds=(-0.2, 0.2), method="bounded")
    return float(res.x)


def elo_prior_blend(fit, elo: dict):
    """Mezcla las fuerzas ajustadas con un prior Elo para equipos con poca
    muestra efectiva. El prior se calibra regresando (att, def) sobre el Elo
    estandarizado de los equipos con muestra abundante."""
    teams, att, dfn, eff = fit["teams"], fit["att"], fit["def"], fit["eff"]
    elo_arr = np.array([elo.get(t, np.nan) for t in teams])
    have = ~np.isnan(elo_arr)
    if have.sum() < 30:
        return att, dfn  # sin Elo suficiente, no hay prior
    z = np.zeros_like(elo_arr)
    z[have] = (elo_arr[have] - np.nanmean(elo_arr)) / np.nanstd(elo_arr)
    rich = have & (eff > np.percentile(eff, 60))
    ba = np.polyfit(z[rich], att[rich], 1)   # att ~ b*z + c
    bd = np.polyfit(z[rich], dfn[rich], 1)
    att_prior = np.where(have, ba[0] * z + ba[1], 0.0)
    def_prior = np.where(have, bd[0] * z + bd[1], 0.0)
    wmix = eff / (eff + ELO_BLEND_K)
    wmix = np.where(have, wmix, 1.0)  # sin Elo: quedarse con lo ajustado
    return wmix * att + (1 - wmix) * att_prior, \
        wmix * dfn + (1 - wmix) * def_prior


def fit_full(matches, ref_date, elo=None, xi=XI_DEFAULT):
    """Ajuste completo: Poisson penalizado + rho + prior Elo.
    Devuelve dict listo para predecir."""
    fit = fit_poisson(matches, ref_date, xi=xi)
    rho = fit_rho(fit)
    att, dfn = fit["att"], fit["def"]
    if elo:
        att, dfn = elo_prior_blend(fit, elo)
    ratings = {t: (float(att[i]), float(dfn[i]), float(fit["eff"][i]))
               for i, t in enumerate(fit["teams"])}
    return {"mu": float(fit["mu"]), "ha": float(fit["ha"]), "rho": rho,
            "xi": xi, "ratings": ratings, "converged": fit["converged"],
            "n_matches": len(fit["arrays"][0]), "ref_date": ref_date}


def load_training_matches(con, until=None):
    """Partidos finalizados desde MIN_YEAR (opcionalmente hasta una fecha)."""
    q = ("SELECT date, home, away, home_score, away_score, tournament, neutral "
         "FROM matches WHERE home_score IS NOT NULL AND date >= ?")
    args = [f"{MIN_YEAR}-01-01"]
    if until:
        q += " AND date < ?"
        args.append(until)
    return [tuple(r) for r in con.execute(q, args).fetchall()]
