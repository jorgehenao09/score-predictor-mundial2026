"""Clientes de las fuentes de datos gratuitas, con caché local, cascada de
respaldo y contadores de peticiones contra los límites free.

Fuentes:
  - martj42/international_results (GitHub CSV)  -> historial + fixtures. Sin clave.
  - eloratings.net (TSV)                        -> Elo por selección. Sin clave.
  - FIFA ranking (JSON no oficial)              -> ranking FIFA. Sin clave.
  - The Odds API                                -> cuotas multi-casa. ODDS_API_KEY (500 créditos/mes).
  - football-data.org                           -> fixtures/resultados WC. FOOTBALL_DATA_TOKEN (10 req/min).
  - TheSportsDB (clave de prueba '123')         -> respaldo fixtures. ~30 req/min.
  - BSD API (sports.bzzoiro.com)                -> EXPERIMENTAL: xG/lesiones. BSD_TOKEN.

Toda descarga cruda se cachea en data/cache con timestamp; sólo se vuelve a
pedir si superó su TTL o se fuerza con force=True.
"""

import csv
import io
import json
import os
import time

import requests
from dotenv import load_dotenv

from . import store
from .names import canonical

load_dotenv(os.path.join(store.BASE_DIR, ".env"))

CACHE_DIR = os.path.join(store.BASE_DIR, "data", "cache")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# TTLs en segundos: "¿pudo haber cambiado esto?"
TTL = {
    "results": 6 * 3600,      # resultados: tras cada jornada
    "elo": 24 * 3600,         # eloratings actualiza a diario
    "fifa": 7 * 24 * 3600,    # FIFA actualiza cada varias semanas
    "odds": 6 * 3600,         # cuotas: 1-2 snapshots/día caben en 500/mes
    "fixtures_fd": 6 * 3600,
}

LIMITS = {  # límites reales de cada fuente
    "odds_api": ("mes", 500),
    "football_data": ("día", 1000),   # 10/min; usamos contador diario como guía
    "thesportsdb": ("día", 1000),
    "bsd": ("día", 5000),
}


def _cache_path(name): return os.path.join(CACHE_DIR, name)


def _cache_fresh(name, ttl):
    p = _cache_path(name)
    return os.path.exists(p) and (time.time() - os.path.getmtime(p)) < ttl


def _read_cache(name):
    with open(_cache_path(name), encoding="utf-8") as f:
        return f.read()


def _write_cache(name, text):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(name), "w", encoding="utf-8") as f:
        f.write(text)


def _get(url, headers=None, timeout=30):
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r.text


def warn_if_near_cap(con, source):
    """Devuelve un aviso (str) si la fuente está cerca de su límite free."""
    if source not in LIMITS:
        return None
    period, cap = LIMITS[source]
    used = (store.requests_this_month(con, source) if period == "mes"
            else store.requests_today(con, source))
    if used >= 0.8 * cap:
        return (f"⚠ {source}: {used}/{cap} peticiones usadas este {period} "
                f"({used / cap:.0%}) — cerca del límite gratuito")
    return None


# ---------------------------------------------------------------- martj42

RESULTS_URL = ("https://raw.githubusercontent.com/martj42/"
               "international_results/master/results.csv")


def sync_results(con, force=False):
    """Descarga results.csv (si toca) y lo vuelca en SQLite.
    Devuelve (n_nuevos_finalizados, fuente_usada)."""
    name = "results.csv"
    if force or not _cache_fresh(name, TTL["results"]):
        try:
            _write_cache(name, _get(RESULTS_URL))
            store.log_request(con, "github_martj42")
        except Exception as e:
            if not os.path.exists(_cache_path(name)):
                raise RuntimeError(f"No pude descargar results.csv: {e}")
    rows = []
    for r in csv.DictReader(io.StringIO(_read_cache(name))):
        hs = None if r["home_score"] in ("NA", "") else int(float(r["home_score"]))
        as_ = None if r["away_score"] in ("NA", "") else int(float(r["away_score"]))
        rows.append((r["date"], r["home_team"], r["away_team"], hs, as_,
                     r["tournament"], r["city"], r["country"],
                     1 if r["neutral"] == "TRUE" else 0))
    new = store.upsert_matches(con, rows)
    store.set_meta(con, "last_results_sync", store.now_iso())
    return new, "martj42 (GitHub)"


# ---------------------------------------------------------------- eloratings

def fetch_elo(con, known_teams, force=False):
    """Devuelve {equipo_canónico: elo}. Caché 24h."""
    if force or not _cache_fresh("elo_world.tsv", TTL["elo"]):
        try:
            _write_cache("elo_world.tsv",
                         _get("https://www.eloratings.net/World.tsv"))
            _write_cache("elo_teams.tsv",
                         _get("https://www.eloratings.net/en.teams.tsv"))
            store.log_request(con, "eloratings")
        except Exception:
            pass  # usamos caché si existe
    if not os.path.exists(_cache_path("elo_world.tsv")):
        return {}
    code2name = {}
    for line in _read_cache("elo_teams.tsv").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            code2name[p[0]] = p[1]
    out = {}
    for line in _read_cache("elo_world.tsv").splitlines():
        p = line.split("\t")
        if len(p) > 3:
            c = canonical(code2name.get(p[2], p[2]), known_teams)
            if c:
                out[c] = float(p[3])
    return out


# ---------------------------------------------------------------- FIFA

FIFA_URL = "https://inside.fifa.com/api/ranking-overview?locale=en&dateId=id14870"


def fetch_fifa(con, known_teams, force=False):
    """Devuelve {equipo_canónico: puntos_fifa}. Caché 7 días. No oficial."""
    if force or not _cache_fresh("fifa_ranking.json", TTL["fifa"]):
        try:
            _write_cache("fifa_ranking.json", _get(FIFA_URL))
            store.log_request(con, "fifa")
        except Exception:
            pass
    if not os.path.exists(_cache_path("fifa_ranking.json")):
        return {}
    out = {}
    try:
        data = json.loads(_read_cache("fifa_ranking.json"))["rankings"]
    except Exception:
        return {}
    for it in data:
        item = it.get("rankingItem", {})
        c = canonical(item.get("name", ""), known_teams)
        if c:
            out[c] = float(item.get("totalPoints", 0))
    return out


# ---------------------------------------------------------------- The Odds API

ODDS_HOST = "https://api.the-odds-api.com/v4"


def fetch_odds(con, known_teams, force=False):
    """Snapshot de cuotas 1X2 del Mundial desde The Odds API.
    Cada llamada cuesta 1 crédito por región (usamos eu). 500/mes.
    Persiste el snapshot (así construimos nuestro histórico apertura/cierre).
    Devuelve (n_partidos_con_cuotas, aviso)."""
    key = os.getenv("ODDS_API_KEY")
    if not key:
        return 0, "ODDS_API_KEY no configurada en .env — capa de mercado inactiva"
    if not force and _cache_fresh("odds_last.json", TTL["odds"]):
        return -1, None  # snapshot reciente ya persistido; no gastar crédito
    used = store.requests_this_month(con, "odds_api")
    if used >= 495:
        return 0, f"odds_api al límite mensual ({used}/500): no pido más"
    # h2h + totals en una llamada = 2 créditos (mercados × regiones).
    # El mercado de totales (over/under) alimenta la matriz de goles
    # implícita del mercado, no solo el 1X2.
    url = (f"{ODDS_HOST}/sports/soccer_fifa_world_cup/odds/"
           f"?apiKey={key}&regions=eu&markets=h2h,totals&oddsFormat=decimal")
    try:
        text = _get(url)
    except requests.HTTPError as e:
        return 0, f"The Odds API error: {e}"
    store.log_request(con, "odds_api", n=2)
    _write_cache("odds_last.json", text)
    games = json.loads(text)
    entries, totals = [], []
    for g in games:
        h = canonical(g.get("home_team", ""), known_teams)
        a = canonical(g.get("away_team", ""), known_teams)
        if not h or not a:
            continue
        for bk in g.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") == "h2h":
                    prices = {}
                    for o in mk.get("outcomes", []):
                        nm = o.get("name", "")
                        if nm == "Draw":
                            prices["draw"] = o["price"]
                        else:
                            cn = canonical(nm, known_teams)
                            if cn == h:
                                prices["home"] = o["price"]
                            elif cn == a:
                                prices["away"] = o["price"]
                    if len(prices) == 3:
                        entries.append({
                            "home": h, "away": a,
                            "commence_time": g.get("commence_time", ""),
                            "bookmaker": bk.get("key", "?"),
                            "home_odds": prices["home"],
                            "draw_odds": prices["draw"],
                            "away_odds": prices["away"]})
                elif mk.get("key") == "totals":
                    by_point = {}
                    for o in mk.get("outcomes", []):
                        pt = o.get("point")
                        if pt is None:
                            continue
                        by_point.setdefault(pt, {})[o.get("name", "")] = o["price"]
                    if not by_point:
                        continue
                    # preferir la línea 2.5; si no, la más cercana
                    pt = min(by_point, key=lambda p: abs(p - 2.5))
                    pr = by_point[pt]
                    if "Over" in pr and "Under" in pr:
                        totals.append({
                            "home": h, "away": a,
                            "commence_time": g.get("commence_time", ""),
                            "bookmaker": bk.get("key", "?"), "point": pt,
                            "over_odds": pr["Over"],
                            "under_odds": pr["Under"]})
    if entries:
        store.save_odds_snapshot(con, "odds_api", entries)
        store.set_meta(con, "last_odds_sync", store.now_iso())
    if totals:
        store.save_odds_totals(con, "odds_api", totals)
    n_matches = len({(e['home'], e['away']) for e in entries})
    return n_matches, warn_if_near_cap(con, "odds_api")


# ---------------------------------------------------------------- football-data.org

FD_HOST = "https://api.football-data.org/v4"


def fetch_fd_fixtures(con, force=False):
    """Fixtures/resultados del Mundial desde football-data.org (respaldo y
    validación cruzada de martj42). Devuelve lista de partidos o []."""
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        return [], "FOOTBALL_DATA_TOKEN no configurada — uso sólo martj42"
    name = "fd_wc.json"
    if force or not _cache_fresh(name, TTL["fixtures_fd"]):
        try:
            _write_cache(name, _get(f"{FD_HOST}/competitions/WC/matches",
                                    headers={"X-Auth-Token": token}))
            store.log_request(con, "football_data")
        except Exception as e:
            if not os.path.exists(_cache_path(name)):
                return [], f"football-data.org error: {e}"
    try:
        data = json.loads(_read_cache(name))
        return data.get("matches", []), None
    except Exception as e:
        return [], f"football-data.org parse error: {e}"


# ---------------------------------------------------------------- TheSportsDB (respaldo)

TSDB_HOST = "https://www.thesportsdb.com/api/v1/json/123"


def fetch_tsdb_fixtures(con):
    """Respaldo keyless de fixtures WC2026 (league 4429)."""
    try:
        text = _get(f"{TSDB_HOST}/eventsseason.php?id=4429&s=2026")
        store.log_request(con, "thesportsdb")
        return json.loads(text).get("events") or []
    except Exception:
        return []


# ---------------------------------------------------------------- BSD (experimental)

BSD_HOST = "https://sports.bzzoiro.com"


def bsd_get(con, path):
    """Cliente mínimo del BSD API. EXPERIMENTAL: datos sin verificar."""
    token = os.getenv("BSD_TOKEN")
    if not token:
        return None
    try:
        text = _get(f"{BSD_HOST}{path}",
                    headers={"Authorization": f"Token {token}"})
        store.log_request(con, "bsd")
        return json.loads(text)
    except Exception:
        return None
