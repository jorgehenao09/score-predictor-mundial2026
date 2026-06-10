"""Sedes del Mundial 2026: altitud, coordenadas y zona horaria.

Datos estáticos tomados de Wikipedia (junio 2026). La clave es el nombre de
ciudad tal como aparece en el dataset martj42 (results.csv).
"""

# city -> (stadium, country, altitude_m, lat, lon, tz)
VENUES = {
    "Arlington": ("AT&T Stadium", "United States", 184, 32.747, -97.094, "America/Chicago"),
    "Atlanta": ("Mercedes-Benz Stadium", "United States", 320, 33.755, -84.401, "America/New_York"),
    "East Rutherford": ("MetLife Stadium", "United States", 2, 40.813, -74.074, "America/New_York"),
    "Foxborough": ("Gillette Stadium", "United States", 43, 42.091, -71.264, "America/New_York"),
    "Guadalupe": ("Estadio BBVA", "Mexico", 540, 25.669, -100.244, "America/Monterrey"),
    "Houston": ("NRG Stadium", "United States", 15, 29.685, -95.411, "America/Chicago"),
    "Inglewood": ("SoFi Stadium", "United States", 30, 33.953, -118.339, "America/Los_Angeles"),
    "Kansas City": ("Arrowhead Stadium", "United States", 270, 39.049, -94.484, "America/Chicago"),
    "Mexico City": ("Estadio Azteca", "Mexico", 2240, 19.303, -99.150, "America/Mexico_City"),
    "Miami Gardens": ("Hard Rock Stadium", "United States", 3, 25.958, -80.239, "America/New_York"),
    "Philadelphia": ("Lincoln Financial Field", "United States", 12, 39.901, -75.168, "America/New_York"),
    "Santa Clara": ("Levi's Stadium", "United States", 3, 37.403, -121.970, "America/Los_Angeles"),
    "Seattle": ("Lumen Field", "United States", 4, 47.595, -122.332, "America/Los_Angeles"),
    "Toronto": ("BMO Field", "Canada", 76, 43.633, -79.418, "America/Toronto"),
    "Vancouver": ("BC Place", "Canada", 5, 49.277, -123.112, "America/Vancouver"),
    "Zapopan": ("Estadio Akron", "Mexico", 1560, 20.682, -103.462, "America/Mexico_City"),
}

# Umbral a partir del cual la altitud penaliza a equipos no aclimatados.
HIGH_ALTITUDE_M = 1500


def altitude(city: str) -> int:
    v = VENUES.get(city)
    return v[2] if v else 0


def venue_info(city: str):
    return VENUES.get(city)
