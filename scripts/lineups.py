"""Alineaciones confirmadas del Mundial 2026 — solo stdlib.

Fuente primaria: api.fifa.com (el canal que alimenta la propia app de FIFA;
latencia cero respecto a la publicación oficial, sin clave). Respaldo: la API
JSON pública de ESPN. Reglamento (Art. 32, FIFA WC26): las planillas se
entregan a más tardar 90 min antes y se publican cuando AMBOS equipos
entregan; en la práctica entre T-75 y T-60.

También define los marcadores de estado (data/notified/) que deduplican los
envíos del cron: un archivo JSON por partido y tipo de informe.
"""

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFIED_DIR = os.path.join(BASE_DIR, "data", "notified")

FIFA_COMPETITION = 17
FIFA_SEASON = 285023  # Mundial 2026

_fifa_calendar_cache = None


def _get_json(url, timeout=25, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                               **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# Equivalencias mínimas entre cómo nombran los equipos las distintas APIs
# (football-data/FIFA usan "Korea Republic", ESPN/martj42 "South Korea", etc.)
_EQUIV = {
    "korea-republic": "south-korea", "ir-iran": "iran", "iran-ir": "iran",
    "cote-d-ivoire": "ivory-coast", "turkiye": "turkey",
    "czechia": "czech-republic", "cabo-verde": "cape-verde",
    "congo-dr": "dr-congo", "usa": "united-states",
    "united-states-of-america": "united-states", "curacao": "curacao",
    "bosnia-herzegovina": "bosnia-and-herzegovina",
}


def team_key(name: str) -> str:
    n = norm(name)
    return _EQUIV.get(n, n)


def same_team(a: str, b: str) -> bool:
    ka, kb = team_key(a), team_key(b)
    return ka == kb or ka in kb or kb in ka


# ---------------------------------------------------------- marcadores

def marker_path(date_utc: str, home: str, away: str, tipo: str) -> str:
    return os.path.join(NOTIFIED_DIR,
                        f"{date_utc}_{team_key(home)}_{team_key(away)}.{tipo}.json")


def marker_read(date_utc, home, away, tipo):
    p = marker_path(date_utc, home, away, tipo)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def marker_write(date_utc, home, away, tipo, payload):
    os.makedirs(NOTIFIED_DIR, exist_ok=True)
    with open(marker_path(date_utc, home, away, tipo), "w",
              encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------- FIFA

def _fifa_calendar():
    global _fifa_calendar_cache
    if _fifa_calendar_cache is None:
        url = (f"https://api.fifa.com/api/v3/calendar/matches?"
               f"idCompetition={FIFA_COMPETITION}&idSeason={FIFA_SEASON}"
               f"&language=en&count=500")
        _fifa_calendar_cache = _get_json(url).get("Results", [])
    return _fifa_calendar_cache


def _fifa_name(team) -> str:
    tn = (team or {}).get("TeamName") or []
    if isinstance(tn, list) and tn:
        return tn[0].get("Description", "")
    return str(tn)


def _fifa_find_match(home, away):
    for m in _fifa_calendar():
        h, a = _fifa_name(m.get("Home")), _fifa_name(m.get("Away"))
        if h and a and same_team(h, home) and same_team(a, away):
            return m
    return None


def _fifa_extract_xi(team_obj):
    players = (team_obj or {}).get("Players") or []
    xi = []
    for p in players:
        if p.get("Status") == 1:  # 1 = titular
            nm = p.get("PlayerName") or []
            name = nm[0].get("Description", "?") if nm else "?"
            xi.append({"name": name, "num": p.get("ShirtNumber"),
                       "pos": p.get("Position"), "captain": p.get("Captain")})
    return xi


def fifa_lineups(home, away):
    """XI confirmadas vía api.fifa.com o None si aún no publican."""
    m = _fifa_find_match(home, away)
    if not m:
        return None
    url = (f"https://api.fifa.com/api/v3/live/football/{FIFA_COMPETITION}/"
           f"{m['IdSeason']}/{m['IdStage']}/{m['IdMatch']}?language=en")
    try:
        live = _get_json(url)
    except Exception:
        return None
    if not live:
        return None
    out = {}
    for side, key in (("home", "HomeTeam"), ("away", "AwayTeam")):
        team = live.get(key) or {}
        xi = _fifa_extract_xi(team)
        if len(xi) != 11:
            return None  # aún no están las dos XI completas
        out[side] = {"formation": team.get("Tactics") or "",
                     "players": xi}
    out["source"] = "FIFA"
    return out


# ---------------------------------------------------------- ESPN (respaldo)

def espn_lineups(home, away, date_utc):
    """XI confirmadas vía ESPN o None. date_utc: YYYY-MM-DD del kickoff."""
    d = date_utc.replace("-", "")
    try:
        sb = _get_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                       f"fifa.world/scoreboard?dates={d}")
    except Exception:
        return None
    event_id = None
    for ev in sb.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        names = [c.get("team", {}).get("displayName", "")
                 for c in comp.get("competitors", [])]
        if len(names) == 2 and (
                (same_team(names[0], home) and same_team(names[1], away)) or
                (same_team(names[1], home) and same_team(names[0], away))):
            event_id = ev.get("id")
            break
    if not event_id:
        return None
    try:
        summ = _get_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                         f"fifa.world/summary?event={event_id}")
    except Exception:
        return None
    rosters = summ.get("rosters") or []
    out = {}
    for r in rosters:
        team_name = (r.get("team") or {}).get("displayName", "")
        side = ("home" if same_team(team_name, home)
                else "away" if same_team(team_name, away) else None)
        if not side:
            continue
        xi = []
        for entry in r.get("roster") or []:
            if entry.get("starter"):
                ath = entry.get("athlete") or {}
                xi.append({"name": ath.get("displayName", "?"),
                           "num": entry.get("jersey"),
                           "pos": (entry.get("position") or {}).get(
                               "abbreviation", ""),
                           "captain": False})
        if len(xi) == 11:
            out[side] = {"formation": r.get("formation") or "", "players": xi}
    if "home" in out and "away" in out:
        out["source"] = "ESPN"
        return out
    return None


# ---------------------------------------------------------- BSD (3ª fuente)

BSD_HOST = "https://sports.bzzoiro.com"
_bsd_lineup_cache = {}


def _bsd_headers():
    tok = os.getenv("BSD_TOKEN")
    return {"Authorization": f"Token {tok}"} if tok else None


def _bsd_event_id(home, away, date_utc):
    hdr = _bsd_headers()
    if not hdr:
        return None
    url = (f"{BSD_HOST}/api/v2/events/?team_name="
           f"{urllib.parse.quote(home)}&date_from={date_utc}"
           f"&date_to={date_utc}T23:59:59Z")
    try:
        data = _get_json(url, headers=hdr)
    except Exception:
        return None
    for e in data.get("results", []):
        if same_team(e.get("home_team", ""), home) and \
                same_team(e.get("away_team", ""), away):
            return e.get("id")
    return None


def _bsd_lineup_payload(home, away, date_utc):
    """Respuesta cruda de /lineups/ del BSD (cacheada por evento)."""
    key = (team_key(home), team_key(away), date_utc)
    if key in _bsd_lineup_cache:
        return _bsd_lineup_cache[key]
    hdr = _bsd_headers()
    ev = _bsd_event_id(home, away, date_utc) if hdr else None
    payload = None
    if ev:
        try:
            payload = _get_json(f"{BSD_HOST}/api/v2/events/{ev}/lineups/",
                                headers=hdr)
        except Exception:
            payload = None
    _bsd_lineup_cache[key] = payload
    return payload


def bsd_lineups(home, away, date_utc):
    """XI confirmadas vía BSD (experimental) o None."""
    d = _bsd_lineup_payload(home, away, date_utc)
    if not d or d.get("lineup_status") != "confirmed":
        return None
    ln = d.get("lineups") or {}
    out = {}
    for side in ("home", "away"):
        sd = ln.get(side) or {}
        ps = sd.get("players") or []
        if len(ps) != 11:
            return None
        out[side] = {"formation": sd.get("formation") or "",
                     "players": [{"name": p.get("name") or
                                  p.get("short_name", "?"),
                                  "num": p.get("jersey_number"),
                                  "pos": p.get("position"),
                                  "captain": p.get("captain", False)}
                                 for p in ps]}
    out["source"] = "BSD"
    return out


def bsd_unavailable(home, away, date_utc):
    """Bajas (lesionados/suspendidos) por lado: {'home': [...], 'away': [...]}
    con name/status/reason, o None si no hay dato. EXPERIMENTAL."""
    d = _bsd_lineup_payload(home, away, date_utc)
    if not d:
        return None
    up = d.get("unavailable_players")
    if not isinstance(up, dict) or not (up.get("home") or up.get("away")):
        return None
    return {s: [{"name": p.get("short_name") or p.get("name", "?"),
                 "status": p.get("status", ""), "reason": p.get("reason", "")}
                for p in (up.get(s) or [])] for s in ("home", "away")}


def get_lineups(home, away, date_utc):
    """Cascada FIFA -> ESPN -> BSD. None si no hay XI confirmadas."""
    for fn in (lambda: fifa_lineups(home, away),
               lambda: espn_lineups(home, away, date_utc),
               lambda: bsd_lineups(home, away, date_utc)):
        try:
            ln = fn()
            if ln:
                return ln
        except Exception:
            continue
    return None


def lineups_confirmed(home, away, date_utc) -> bool:
    return get_lineups(home, away, date_utc) is not None
