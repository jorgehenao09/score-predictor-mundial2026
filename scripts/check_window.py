"""Comprueba si hay partidos del Mundial que arranquen en ~3 horas.

Solo stdlib (sin pip): se usa como compuerta barata en GitHub Actions para
no instalar numpy/scipy cada hora si no hay nada que notificar.

Fuente primaria: football-data.org (hora exacta de inicio, utcDate).
Respaldo: TheSportsDB (clave pública).

Uso:  python3 scripts/check_window.py            -> imprime found=true|false
      FORCE_NEXT=1 python3 scripts/check_window.py  -> el próximo partido,
                                                       esté o no en ventana
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

WINDOW_START_H = 2.5   # notificar partidos que empiezan entre 2.5 y 3.5 h
WINDOW_END_H = 3.5     # desde ahora (el cron corre cada hora: 1 aviso/partido)


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def from_football_data():
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        return None
    try:
        data = _get_json("https://api.football-data.org/v4/competitions/WC/matches",
                         {"X-Auth-Token": token})
    except Exception:
        return None
    out = []
    for m in data.get("matches", []):
        if m.get("status") not in ("SCHEDULED", "TIMED"):
            continue
        out.append({
            "utc": m["utcDate"],
            "home": (m.get("homeTeam") or {}).get("name", ""),
            "away": (m.get("awayTeam") or {}).get("name", ""),
        })
    return out


def from_thesportsdb():
    try:
        data = _get_json("https://www.thesportsdb.com/api/v1/json/123/"
                         "eventsseason.php?id=4429&s=2026")
    except Exception:
        return None
    out = []
    for e in data.get("events") or []:
        ts = e.get("strTimestamp")  # "2026-06-11T23:00:00"
        if not ts or e.get("intHomeScore") is not None:
            continue
        out.append({"utc": ts + "Z" if not ts.endswith("Z") else ts,
                    "home": e.get("strHomeTeam", ""),
                    "away": e.get("strAwayTeam", "")})
    return out


def matches_in_window(force_next=False):
    fixtures = from_football_data()
    if fixtures is None:
        fixtures = from_thesportsdb() or []
    now = datetime.now(timezone.utc)
    parsed = []
    for f in fixtures:
        try:
            ko = datetime.fromisoformat(f["utc"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko > now:
            parsed.append({**f, "kickoff": ko})
    parsed.sort(key=lambda f: f["kickoff"])
    if force_next:
        return parsed[:1]
    lo = now + timedelta(hours=WINDOW_START_H)
    hi = now + timedelta(hours=WINDOW_END_H)
    return [f for f in parsed if lo <= f["kickoff"] < hi]


if __name__ == "__main__":
    found = matches_in_window(force_next=bool(os.getenv("FORCE_NEXT")))
    print(f"found={'true' if found else 'false'}")
    for f in found:
        print(f"# {f['utc']} {f['home']} vs {f['away']}", file=sys.stderr)
