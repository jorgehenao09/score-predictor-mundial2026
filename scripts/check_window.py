"""Decide qué informes tocan AHORA. Solo stdlib (compuerta barata del cron).

Dos informes por partido, deduplicados con marcadores en data/notified/
(commiteados al repo por el workflow — el estado sobrevive entre runs):

  PREVIA  — ventana [T-230 min, T-150 min): el informe de las ~3 h.
  CIERRE  — ventana [T-10, T-85): se dispara apenas FIFA/ESPN publiquen las
            XI confirmadas (reglamento: entrega T-90, publicación típica
            T-75..T-60), o sí o sí a T-40 aunque no haya alineaciones.
            golpredictor.com bloquea el ingreso a T-10 (verificado en sus
            reglas), así que el peor caso deja ~25-30 min de margen.

Salida (stdout): found=true|false  — y en stderr el detalle.
FORCE_TYPE=previa|cierre fuerza el próximo partido (test).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lineups import lineups_confirmed, marker_read  # noqa: E402

PREVIA_MIN, PREVIA_MAX = 150, 230      # minutos antes del kickoff
CIERRE_MIN, CIERRE_MAX = 10, 85
CIERRE_FALLBACK = 40                   # sin XI a T-40: enviar igual


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
        h = (m.get("homeTeam") or {}).get("name")
        a = (m.get("awayTeam") or {}).get("name")
        if h and a:
            out.append({"utc": m["utcDate"], "home": h, "away": a})
    return out


def from_thesportsdb():
    try:
        data = _get_json("https://www.thesportsdb.com/api/v1/json/123/"
                         "eventsseason.php?id=4429&s=2026")
    except Exception:
        return None
    out = []
    for e in data.get("events") or []:
        ts = e.get("strTimestamp")
        if not ts or e.get("intHomeScore") is not None:
            continue
        out.append({"utc": ts if ts.endswith("Z") else ts + "Z",
                    "home": e.get("strHomeTeam", ""),
                    "away": e.get("strAwayTeam", "")})
    return out


def upcoming_fixtures():
    fixtures = from_football_data()
    if fixtures is None:
        fixtures = from_thesportsdb() or []
    now = datetime.now(timezone.utc)
    out = []
    for f in fixtures:
        try:
            ko = datetime.fromisoformat(f["utc"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko > now:
            out.append({**f, "kickoff": ko,
                        "date_utc": ko.strftime("%Y-%m-%d")})
    out.sort(key=lambda f: f["kickoff"])
    return out


def due_actions(probe_lineups=True):
    """Lista de {fixture..., tipo} que deben notificarse ahora mismo."""
    force = os.getenv("FORCE_TYPE", "").strip().lower()
    fixtures = upcoming_fixtures()
    if force in ("previa", "cierre"):
        return [{**f, "tipo": force} for f in fixtures[:1]]
    now = datetime.now(timezone.utc)
    due = []
    for f in fixtures:
        mins = (f["kickoff"] - now).total_seconds() / 60
        if mins > PREVIA_MAX:
            break  # ordenados por hora: nada más por revisar
        if PREVIA_MIN <= mins < PREVIA_MAX and \
                marker_read(f["date_utc"], f["home"], f["away"], "previa") is None:
            due.append({**f, "tipo": "previa"})
        elif CIERRE_MIN <= mins < CIERRE_MAX and \
                marker_read(f["date_utc"], f["home"], f["away"], "cierre") is None:
            ready = mins <= CIERRE_FALLBACK
            if not ready and probe_lineups:
                ready = lineups_confirmed(f["home"], f["away"], f["date_utc"])
            if ready:
                due.append({**f, "tipo": "cierre"})
    return due


if __name__ == "__main__":
    due = due_actions()
    print(f"found={'true' if due else 'false'}")
    for d in due:
        print(f"# {d['tipo'].upper()} {d['utc']} {d['home']} vs {d['away']}",
              file=sys.stderr)
