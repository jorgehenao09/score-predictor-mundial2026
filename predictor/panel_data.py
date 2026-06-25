"""Cálculos del dashboard, sin HTML: aciertos y calibración por competición.
Reutiliza la lógica de `precision` y el estado vivo (fit, learning, params)."""
import numpy as np

from . import golpredictor as gp
from . import learning, store
from .predict import brier, goal_uplift, rps

# Registro de competiciones: para escalar, añadir una entrada y su snapshot.
# Hoy solo Mundial 2026 (su calibración sale del estado vivo del modelo).
BASE = {  # defaults universales del modelo (no se recalculan)
    "xi": "0.0005", "rho": "—", "local": "—", "blend": "0.50", "uplift": "1.00",
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
