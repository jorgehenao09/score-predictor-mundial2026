"""Resolución de nombres de selecciones entre fuentes de datos.

El nombre canónico es el usado por martj42/results.csv (p.ej. "South Korea",
"United States", "Ivory Coast"). Cada fuente externa (eloratings, FIFA,
The Odds API, football-data.org) usa variantes; aquí se normalizan.
"""

import unicodedata

# alias (en minúsculas, sin acentos) -> nombre canónico martj42
ALIASES = {
    "usa": "United States",
    "united states of america": "United States",
    "korea republic": "South Korea",
    "korea dpr": "North Korea",
    "ir iran": "Iran",
    "iran ir": "Iran",
    "cote d'ivoire": "Ivory Coast",
    "cote divoire": "Ivory Coast",
    "turkiye": "Turkey",
    "czechia": "Czech Republic",
    "czech rep": "Czech Republic",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia": "Bosnia and Herzegovina",
    "cabo verde": "Cape Verde",
    "cape verde islands": "Cape Verde",
    "congo dr": "DR Congo",
    "dr congo": "DR Congo",
    "democratic republic of congo": "DR Congo",
    "congo kinshasa": "DR Congo",
    "curacao": "Curaçao",
    "netherlands antilles": "Curaçao",
    "korea south": "South Korea",
    "south korea": "South Korea",
    "saudiarabia": "Saudi Arabia",
    "uae": "United Arab Emirates",
    "england national team": "England",
    # nombres en español (entrada del usuario en la CLI)
    "espana": "Spain",
    "alemania": "Germany",
    "francia": "France",
    "inglaterra": "England",
    "paises bajos": "Netherlands",
    "holanda": "Netherlands",
    "belgica": "Belgium",
    "suiza": "Switzerland",
    "suecia": "Sweden",
    "noruega": "Norway",
    "croacia": "Croatia",
    "turquia": "Turkey",
    "marruecos": "Morocco",
    "egipto": "Egypt",
    "tunez": "Tunisia",
    "argelia": "Algeria",
    "senegal": "Senegal",
    "sudafrica": "South Africa",
    "costa de marfil": "Ivory Coast",
    "cabo verde": "Cape Verde",
    "republica checa": "Czech Republic",
    "chequia": "Czech Republic",
    "escocia": "Scotland",
    "austria": "Austria",
    "bosnia y herzegovina": "Bosnia and Herzegovina",
    "estados unidos": "United States",
    "mexico": "Mexico",
    "canada": "Canada",
    "panama": "Panama",
    "haiti": "Haiti",
    "brasil": "Brazil",
    "japon": "Japan",
    "corea del sur": "South Korea",
    "iran": "Iran",
    "irak": "Iraq",
    "jordania": "Jordan",
    "arabia saudita": "Saudi Arabia",
    "arabia saudi": "Saudi Arabia",
    "catar": "Qatar",
    "uzbekistan": "Uzbekistan",
    "nueva zelanda": "New Zealand",
    "rd congo": "DR Congo",
    "republica democratica del congo": "DR Congo",
    "ghana": "Ghana",
    "uruguay": "Uruguay",
    "paraguay": "Paraguay",
    "ecuador": "Ecuador",
    "colombia": "Colombia",
    "argentina": "Argentina",
    "portugal": "Portugal",
    "italia": "Italy",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("_", " ").split())


def canonical(name: str, known: set | None = None) -> str | None:
    """Devuelve el nombre canónico martj42 para `name`, o None si no se resuelve.

    `known` es el conjunto de nombres canónicos válidos (de results.csv);
    si se pasa, un nombre ya canónico se acepta directamente.
    """
    if not name:
        return None
    n = _norm(name)
    if n in ALIASES:
        return ALIASES[n]
    if known:
        for k in known:
            if _norm(k) == n:
                return k
        # coincidencia por contención (p.ej. "Iran" vs "IR Iran")
        for k in known:
            if _norm(k) in n or n in _norm(k):
                return k
    return None
