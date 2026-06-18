"""Puntaje de golpredictor.com y marcador que MAXIMIZA los puntos esperados.

Reglas verificadas en regulation.aspx (2026), componentes ADITIVOS e
INDEPENDIENTES (confirmado con sus ejemplos oficiales):

  fase de grupos:  5 resultado (1X2) + 2 goles local + 2 goles visita
                   + 1 diferencia de gol     → máx 10 (marcador exacto)
  eliminatorias:   todo ×2                    → máx 20
                   (el marcador cuenta solo 90'+reposición; sin prórroga/penales)

Por qué un módulo aparte: el marcador MÁS PROBABLE (modal de la matriz) NO es
el que más puntos da en esta tabla. Aquí se calcula el óptimo-EV: el marcador
(i,j) que maximiza la suma de puntos esperados sobre toda la distribución.
"""

import numpy as np

# La ronda de 32 (primera eliminatoria) arranca el 2026-06-28.
KNOCKOUT_START = "2026-06-28"
CAND = 7   # candidatos de marcador a evaluar (0..6 por lado; de sobra)


def is_knockout(match_date: str) -> bool:
    return bool(match_date) and match_date >= KNOCKOUT_START


def points(pred, actual, knockout=False) -> int:
    """pred=(gl,gv), actual=(gl,gv). Puntos golpredictor del pronóstico."""
    ph, pa = pred
    ah, ab = actual
    mult = 2 if knockout else 1
    p = 0
    if np.sign(ph - pa) == np.sign(ah - ab):
        p += 5
    if ph == ah:
        p += 2
    if pa == ab:
        p += 2
    if (ph - pa) == (ah - ab):
        p += 1
    return p * mult


def expected_points(M, score, knockout=False) -> float:
    """Puntos esperados de un marcador `score` dada la matriz de prob. M."""
    n = M.shape[0]
    home_marg = M.sum(axis=1)
    away_marg = M.sum(axis=0)
    ph_win = float(np.tril(M, -1).sum())
    draw = float(np.trace(M))
    pa_win = float(np.triu(M, 1).sum())
    i, j = score
    res = ph_win if i > j else (draw if i == j else pa_win)
    diff = 0.0
    for a in range(n):
        b = a - (i - j)
        if 0 <= b < n:
            diff += M[a, b]
    ev = 5 * res + 2 * home_marg[i] + 2 * away_marg[j] + 1 * diff
    return ev * (2 if knockout else 1)


def ev_optimal_score(M, knockout=False):
    """Marcador (i,j) que maximiza los puntos esperados de golpredictor.

    Usa la descomposición por marginales (los 4 componentes son aditivos):
        EV(i,j) = 5·P(resultado=signo(i-j)) + 2·P(local=i)
                  + 2·P(visita=j) + 1·P(dif=i-j)
    Desempate: a igual EV, el marcador exacto más probable.
    Devuelve (marcador, ev_puntos).
    """
    n = M.shape[0]
    home_marg = M.sum(axis=1)
    away_marg = M.sum(axis=0)
    ph_win = float(np.tril(M, -1).sum())
    draw = float(np.trace(M))
    pa_win = float(np.triu(M, 1).sum())
    diff_prob = {}
    for a in range(n):
        for b in range(n):
            d = a - b
            diff_prob[d] = diff_prob.get(d, 0.0) + M[a, b]

    best, best_key = (0, 0), (-1.0, -1.0)
    lim = min(CAND, n)
    for i in range(lim):
        for j in range(lim):
            res = ph_win if i > j else (draw if i == j else pa_win)
            ev = (5 * res + 2 * home_marg[i] + 2 * away_marg[j]
                  + 1 * diff_prob.get(i - j, 0.0))
            key = (ev, float(M[i, j]))   # desempate por prob. exacta
            if key > best_key:
                best_key, best = key, (i, j)
    return best, best_key[0] * (2 if knockout else 1)


def best_score_for_outcome(M, outcome):
    """Marcador (i,j) más probable de la matriz DENTRO de un resultado dado.
    outcome: 'H' (gana local), 'D' (empate), 'A' (gana visita)."""
    n = M.shape[0]
    best, bp = None, -1.0
    for i in range(n):
        for j in range(n):
            if outcome == "H" and not i > j:
                continue
            if outcome == "D" and i != j:
                continue
            if outcome == "A" and not j > i:
                continue
            if M[i, j] > bp:
                bp, best = M[i, j], (i, j)
    return best


def contrarian_pick(M, model_probs, market_probs, knockout=False,
                    min_edge=0.05):
    """Pick de 'remontada' para cuando vas detrás en la polla.

    El campo (los demás jugadores) sigue al mercado. El valor contrarian está
    donde TU MODELO ve más probabilidad que el mercado en un resultado que el
    campo infravalora. Devuelve el marcador más probable de ESE resultado, su
    EV de puntos, la divergencia, y el costo en EV frente al pick EV-óptimo.

    model_probs / market_probs: (p_local, p_empate, p_visita).
    Devuelve None si no hay borde contrarian apreciable (juega el seguro).
    """
    outcomes = ("H", "D", "A")
    edges = {o: model_probs[k] - market_probs[k] for k, o in enumerate(outcomes)}
    best_o = max(outcomes, key=lambda o: edges[o])
    edge = edges[best_o]
    if edge < min_edge:
        return None
    score = best_score_for_outcome(M, best_o)
    if score is None:
        return None
    ev = expected_points(M, score, knockout)
    opt_ev = ev_optimal_score(M, knockout)[1]
    return {
        "score": f"{score[0]}-{score[1]}",
        "outcome": best_o,
        "edge": float(edge),
        "ev": float(ev),
        "ev_cost": float(opt_ev - ev),   # cuánto sacrificas vs el EV-óptimo
    }


if __name__ == "__main__":
    # comprobaciones de la matemática (sin framework, a pedido del usuario)
    # ejemplo oficial: pronóstico 2-0, real 3-1 → 5 (resultado) + 1 (dif) = 6
    assert points((2, 0), (3, 1)) == 6, points((2, 0), (3, 1))
    # exacto = 10 en grupos, 20 en eliminatorias
    assert points((1, 0), (1, 0)) == 10
    assert points((1, 0), (1, 0), knockout=True) == 20
    # solo goles del visitante (pron 0-1, real 2-1) = 2
    assert points((0, 1), (2, 1)) == 2
    # el óptimo-EV de una matriz concentrada en 2-1 debe ser 2-1
    from predictor.predict import score_matrix
    M = score_matrix(1.6, 0.9, -0.034)
    s, ev = ev_optimal_score(M)
    print(f"golpredictor.py OK · óptimo de λ(1.6,0.9) = {s} (EV {ev:.2f} pts)")
