"""Señal de mercado: de-vigging (eliminación del margen del bookmaker).

Dos métodos:
  - proporcional: p_i = (1/o_i) / sum(1/o_j). Simple, sesgado en longshots.
  - Shin (1992/93): modela la proporción z de apostadores con información
    privilegiada; corrige el sesgo favorito-longshot. Es el método preferido.

La probabilidad "del mercado" para un partido es el consenso (mediana entre
casas) de las probabilidades Shin de cada casa.
"""

import statistics

from scipy.optimize import brentq


def proportional(odds):
    """odds: [o_home, o_draw, o_away] decimales. -> probs que suman 1."""
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [p / s for p in inv]


def shin(odds):
    """De-vig por el método de Shin. Devuelve probs que suman 1.

    Con pi_i = 1/o_i y B = sum(pi), las probabilidades de Shin son
        p_i(z) = (sqrt(z^2 + 4(1-z) pi_i^2 / B) - z) / (2(1-z))
    y z* se elige tal que sum p_i(z*) = 1. Si B <= 1 (sin margen) se
    normaliza proporcionalmente.
    """
    pi = [1.0 / o for o in odds]
    B = sum(pi)
    if B <= 1.0:
        return [p / B for p in pi]

    def total(z):
        return sum((((z * z + 4 * (1 - z) * p * p / B) ** 0.5) - z)
                   / (2 * (1 - z)) for p in pi) - 1.0

    try:
        z = brentq(total, 1e-12, 0.4)
    except ValueError:
        return proportional(odds)
    return [(((z * z + 4 * (1 - z) * p * p / B) ** 0.5) - z) / (2 * (1 - z))
            for p in pi]


def consensus(book_odds_rows):
    """book_odds_rows: filas (bookmaker, o_h, o_d, o_a, fetched_at).
    Devuelve (p_home, p_draw, p_away, n_casas, margen_medio) con Shin por casa
    y mediana entre casas, o None si no hay datos."""
    if not book_odds_rows:
        return None
    probs, margins = [], []
    for row in book_odds_rows:
        o = [row[1], row[2], row[3]]
        if any(x is None or x <= 1.0 for x in o):
            continue
        probs.append(shin(o))
        margins.append(sum(1.0 / x for x in o) - 1.0)
    if not probs:
        return None
    med = [statistics.median(p[i] for p in probs) for i in range(3)]
    s = sum(med)
    med = [p / s for p in med]
    return med[0], med[1], med[2], len(probs), statistics.mean(margins)


if __name__ == "__main__":
    # comprobación rápida de la matemática (sin framework de tests, a pedido
    # del usuario): margen conocido, simetrías y recuperación del caso justo
    fair = [2.0, 4.0, 4.0]          # probs justas 0.5/0.25/0.25, sin margen
    assert all(abs(a - b) < 1e-9 for a, b in
               zip(shin(fair), [0.5, 0.25, 0.25]))
    vig = [1.83, 3.6, 3.7]          # cuotas reales con ~5% de margen
    ps, pp = shin(vig), proportional(vig)
    assert abs(sum(ps) - 1) < 1e-9 and abs(sum(pp) - 1) < 1e-9
    # Shin debe dar al favorito MÁS probabilidad que el método proporcional
    # (corrección del sesgo favorito-longshot)
    assert ps[0] > pp[0], (ps, pp)
    print("market.py: comprobaciones OK")
    print("  proporcional:", [round(p, 4) for p in pp])
    print("  shin:        ", [round(p, 4) for p in ps])
