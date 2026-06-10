"""Calibración empírica de marcadores exactos.

Poisson-DC tiene sesgos sistemáticos por marcador (p.ej. subestima el 1-1).
`scripts/calibrate_scores.py` mide, con ajustes rolling FUERA DE MUESTRA
(2010-2025), el ratio frecuencia_observada / probabilidad_esperada por
marcador y lo guarda (encogido hacia 1) en calibration_table.json.

apply(M) multiplica la matriz por esos ratios (solo marcadores hasta CAP) y
renormaliza. Sin tabla generada, es la identidad.
"""

import json
import os

CAP = 5  # solo se calibran marcadores con ambos goles <= CAP

_TABLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "calibration_table.json")
_ratios = None


def _load():
    global _ratios
    if _ratios is None:
        if os.path.exists(_TABLE_PATH):
            with open(_TABLE_PATH, encoding="utf-8") as f:
                raw = json.load(f)["ratios"]
            _ratios = {tuple(map(int, k.split("-"))): v
                       for k, v in raw.items()}
        else:
            _ratios = {}
    return _ratios


def apply(M):
    ratios = _load()
    if not ratios:
        return M
    M = M.copy()
    for (i, j), r in ratios.items():
        if i < M.shape[0] and j < M.shape[1]:
            M[i, j] *= r
    return M / M.sum()
