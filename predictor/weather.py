"""Clima en la sede a la hora del partido — Open-Meteo (gratis, sin clave).

El calor extremo deprime el ritmo y los goles esperados (junio-julio en
USA/México: tardes de 33-38°C en Dallas, Houston, Kansas City, Monterrey).
Penalización heurística moderada, documentada:
  >= 32°C: -3% goles esperados ambos equipos · >= 35°C: -5%.

Pronóstico horario disponible ~16 días adelante: cubre siempre los informes
previa/cierre (mismo día) y el panel para la semana próxima.
"""

import json
import time
import urllib.parse
import urllib.request

from .venues import VENUES

_cache = {}  # (city, date) -> (fetched_monotonic, hourly_dict)
_TTL = 3 * 3600

HEAT_1, HEAT_1_PENALTY = 32.0, 0.03
HEAT_2, HEAT_2_PENALTY = 35.0, 0.05


def temp_at(city: str, date_iso: str, hour_utc: int):
    """Temperatura (°C) pronosticada/observada en la sede a esa hora UTC,
    o None si no hay dato."""
    v = VENUES.get(city)
    if not v:
        return None
    key = (city, date_iso)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _TTL:
        hourly = cached[1]
    else:
        params = urllib.parse.urlencode({
            "latitude": v[3], "longitude": v[4], "hourly": "temperature_2m",
            "timezone": "UTC", "start_date": date_iso, "end_date": date_iso})
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                hourly = json.loads(r.read().decode()).get("hourly", {})
        except Exception:
            return None
        _cache[key] = (time.monotonic(), hourly)
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    target = f"{date_iso}T{hour_utc:02d}:00"
    for t, temp in zip(times, temps):
        if t == target:
            return temp
    return None


def heat_penalty(temp_c):
    """Multiplicador (<1) por calor, o 1.0 si no aplica."""
    if temp_c is None:
        return 1.0, None
    if temp_c >= HEAT_2:
        return 1 - HEAT_2_PENALTY, HEAT_2_PENALTY
    if temp_c >= HEAT_1:
        return 1 - HEAT_1_PENALTY, HEAT_1_PENALTY
    return 1.0, None
