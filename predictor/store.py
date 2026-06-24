"""Persistencia local en SQLite: partidos, odds, ratings, predicciones y
contadores de peticiones. Una sola base: data/predictor.db
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "predictor.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    date TEXT, home TEXT, away TEXT,
    home_score INTEGER, away_score INTEGER,
    tournament TEXT, city TEXT, country TEXT, neutral INTEGER,
    PRIMARY KEY (date, home, away)
);
CREATE TABLE IF NOT EXISTS odds_snapshots (
    fetched_at TEXT, source TEXT, home TEXT, away TEXT,
    commence_time TEXT, bookmaker TEXT,
    home_odds REAL, draw_odds REAL, away_odds REAL
);
CREATE TABLE IF NOT EXISTS fits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fitted_at TEXT, xi REAL, rho REAL, home_adv REAL,
    mu REAL, n_matches INTEGER, train_until TEXT
);
CREATE TABLE IF NOT EXISTS team_ratings (
    fit_id INTEGER, team TEXT, attack REAL, defense REAL,
    eff_matches REAL,
    PRIMARY KEY (fit_id, team)
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT, match_date TEXT, home TEXT, away TEXT, city TEXT,
    exp_home REAL, exp_away REAL,
    p_home REAL, p_draw REAL, p_away REAL,
    top_score TEXT, top_score_prob REAL,
    confidence TEXT, explanation TEXT,
    market_p_home REAL, market_p_draw REAL, market_p_away REAL,
    data_version TEXT
);
CREATE TABLE IF NOT EXISTS odds_totals (
    fetched_at TEXT, source TEXT, home TEXT, away TEXT,
    commence_time TEXT, bookmaker TEXT,
    point REAL, over_odds REAL, under_odds REAL
);
CREATE TABLE IF NOT EXISTS request_log (
    source TEXT, day TEXT, count INTEGER,
    PRIMARY KEY (source, day)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, value TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    # migraciones idempotentes sobre bases ya creadas
    for col in ("model_p_home", "model_p_draw", "model_p_away"):
        try:
            con.execute(f"ALTER TABLE predictions ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass  # ya existe
    for col in ("gp_score",):
        try:
            con.execute(f"ALTER TABLE predictions ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    return con


def set_meta(con, key: str, value):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                (key, json.dumps(value)))
    con.commit()


def get_meta(con, key: str, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def log_request(con, source: str, n: int = 1):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute(
        "INSERT INTO request_log VALUES (?,?,?) "
        "ON CONFLICT(source, day) DO UPDATE SET count = count + ?",
        (source, day, n, n))
    con.commit()


def requests_today(con, source: str) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = con.execute("SELECT count FROM request_log WHERE source=? AND day=?",
                      (source, day)).fetchone()
    return row[0] if row else 0


def requests_this_month(con, source: str) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    row = con.execute(
        "SELECT SUM(count) FROM request_log WHERE source=? AND day LIKE ?",
        (source, month + "%")).fetchone()
    return row[0] or 0


def upsert_matches(con, rows) -> int:
    """rows: iterable de tuplas (date, home, away, hs, as, tournament, city,
    country, neutral). Devuelve cuántos partidos NUEVOS con resultado entraron."""
    before = con.execute(
        "SELECT COUNT(*) FROM matches WHERE home_score IS NOT NULL").fetchone()[0]
    con.executemany(
        "INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    after = con.execute(
        "SELECT COUNT(*) FROM matches WHERE home_score IS NOT NULL").fetchone()[0]
    return after - before


def save_odds_snapshot(con, source: str, entries):
    """entries: lista de dicts con home, away, commence_time, bookmaker,
    home_odds, draw_odds, away_odds."""
    ts = now_iso()
    con.executemany(
        "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
        [(ts, source, e["home"], e["away"], e.get("commence_time", ""),
          e["bookmaker"], e["home_odds"], e["draw_odds"], e["away_odds"])
         for e in entries])
    con.commit()


def save_odds_totals(con, source: str, entries):
    ts = now_iso()
    con.executemany(
        "INSERT INTO odds_totals VALUES (?,?,?,?,?,?,?,?,?)",
        [(ts, source, e["home"], e["away"], e.get("commence_time", ""),
          e["bookmaker"], e["point"], e["over_odds"], e["under_odds"])
         for e in entries])
    con.commit()


def latest_totals(con, home: str, away: str):
    """Último snapshot de over/under por bookmaker (línea principal).
    Over/under son sobre el total de goles → no dependen de la orientación;
    si la fuente guardó el partido invertido, igual sirve."""
    sql = ("""SELECT bookmaker, point, over_odds, under_odds, fetched_at
              FROM odds_totals WHERE home=? AND away=?
              AND fetched_at = (SELECT MAX(fetched_at) FROM odds_totals
                                WHERE home=? AND away=?)""")
    rows = con.execute(sql, (home, away, home, away)).fetchall()
    return rows or con.execute(sql, (away, home, away, home)).fetchall()


def latest_odds(con, home: str, away: str):
    """Último snapshot de cuotas 1X2 por bookmaker para un partido."""
    return _odds_both_orientations(con, "MAX", home, away)


def first_odds(con, home: str, away: str):
    """Primer snapshot (nuestra 'línea de apertura' casera)."""
    return _odds_both_orientations(con, "MIN", home, away)


def _odds_both_orientations(con, agg: str, home: str, away: str):
    """Cuotas 1X2 tolerando que la fuente guarde el partido con la orientación
    local/visitante invertida (p.ej. The Odds API lista 'Switzerland vs Canada'
    cuando martj42 tiene 'Canada vs Switzerland' por ser Canadá anfitrión). Si
    solo hay datos en (away, home), se devuelven con las cuotas local↔visita ya
    intercambiadas (el empate no cambia). agg = 'MAX' (cierre) o 'MIN' (apertura)."""
    sql = (f"""SELECT bookmaker, home_odds, draw_odds, away_odds, fetched_at
               FROM odds_snapshots WHERE home=? AND away=?
               AND fetched_at = (SELECT {agg}(fetched_at) FROM odds_snapshots
                                 WHERE home=? AND away=?)""")
    rows = con.execute(sql, (home, away, home, away)).fetchall()
    if rows:
        return rows
    rev = con.execute(sql, (away, home, away, home)).fetchall()
    # orientación invertida: la 'home_odds' guardada es de nuestro visitante
    return [(bk, ao, do, ho, ts) for bk, ho, do, ao, ts in rev]


def save_fit(con, xi, rho, home_adv, mu, n_matches, train_until, ratings):
    cur = con.execute(
        "INSERT INTO fits (fitted_at, xi, rho, home_adv, mu, n_matches, train_until) "
        "VALUES (?,?,?,?,?,?,?)",
        (now_iso(), xi, rho, home_adv, mu, n_matches, train_until))
    fit_id = cur.lastrowid
    con.executemany(
        "INSERT INTO team_ratings VALUES (?,?,?,?,?)",
        [(fit_id, t, a, d, m) for t, (a, d, m) in ratings.items()])
    con.commit()
    return fit_id


def latest_fit(con):
    row = con.execute(
        "SELECT id, fitted_at, xi, rho, home_adv, mu, n_matches, train_until "
        "FROM fits ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None, {}
    fit = dict(zip(["id", "fitted_at", "xi", "rho", "home_adv", "mu",
                    "n_matches", "train_until"], row))
    ratings = {t: (a, d, m) for t, a, d, m in con.execute(
        "SELECT team, attack, defense, eff_matches FROM team_ratings "
        "WHERE fit_id=?", (fit["id"],))}
    return fit, ratings


def save_prediction(con, p: dict) -> int:
    cur = con.execute(
        """INSERT INTO predictions (created_at, match_date, home, away, city,
           exp_home, exp_away, p_home, p_draw, p_away, top_score,
           top_score_prob, confidence, explanation,
           market_p_home, market_p_draw, market_p_away, data_version,
           model_p_home, model_p_draw, model_p_away, gp_score)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (now_iso(), p["match_date"], p["home"], p["away"], p.get("city", ""),
         p["exp_home"], p["exp_away"], p["p_home"], p["p_draw"], p["p_away"],
         p["top_score"], p["top_score_prob"], p["confidence"],
         p["explanation"], p.get("market_p_home"), p.get("market_p_draw"),
         p.get("market_p_away"), json.dumps(p.get("data_version", {})),
         p.get("model_p_home"), p.get("model_p_draw"), p.get("model_p_away"),
         p.get("gp_score")))
    con.commit()
    return cur.lastrowid


def previous_prediction(con, home: str, away: str, match_date: str):
    row = con.execute(
        """SELECT created_at, p_home, p_draw, p_away, top_score, exp_home,
           exp_away FROM predictions
           WHERE home=? AND away=? AND match_date=?
           ORDER BY id DESC LIMIT 1""", (home, away, match_date)).fetchone()
    if not row:
        return None
    return dict(zip(["created_at", "p_home", "p_draw", "p_away", "top_score",
                     "exp_home", "exp_away"], row))
