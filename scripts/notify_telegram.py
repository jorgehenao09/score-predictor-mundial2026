"""Envía a Telegram el informe corto de cada partido que arranca en ~3 h.

Pensado para correr en GitHub Actions (sin estado previo: reconstruye la base
desde los datos públicos en cada ejecución) pero funciona igual en local.

Variables de entorno:
  TELEGRAM_BOT_TOKEN   token del bot (@BotFather)
  TELEGRAM_CHAT_ID     @nombre_del_canal o id numérico
  ODDS_API_KEY         (opcional) activa la comparación con el mercado
  FOOTBALL_DATA_TOKEN  (opcional) horas de inicio exactas
  FORCE_NEXT=1         (test) envía el próximo partido aunque falten días
  DRY_RUN=1            imprime el mensaje en vez de enviarlo

Uso:  .venv/bin/python scripts/notify_telegram.py
"""

import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from check_window import matches_in_window          # noqa: E402
from predictor import predict as P                  # noqa: E402
from predictor import ratings, sources, store      # noqa: E402
from predictor.cli import ensure_fit, known_teams   # noqa: E402
from predictor.names import canonical               # noqa: E402
from predictor.venues import VENUES                 # noqa: E402

TZ_LOCAL = ZoneInfo("America/Bogota")


def find_fixture_row(con, h, a, ko):
    """Busca la fila martj42 (con ciudad/neutral) por equipos y fecha ±1 día."""
    d0 = (ko - timedelta(days=1)).strftime("%Y-%m-%d")
    d1 = (ko + timedelta(days=1)).strftime("%Y-%m-%d")
    row = con.execute(
        """SELECT date, home, away, city, country, neutral FROM matches
           WHERE home=? AND away=? AND date BETWEEN ? AND ?
           AND home_score IS NULL""", (h, a, d0, d1)).fetchone()
    if not row:
        return {"date": ko.strftime("%Y-%m-%d"), "home": h, "away": a,
                "city": "", "country": "", "neutral": 1}
    return dict(zip(["date", "home", "away", "city", "country", "neutral"], row))


def build_message(pred, fx, ko):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    v = VENUES.get(fx.get("city", ""))
    lines = [f"⚽ <b>{h} vs {a}</b>"]
    if v:
        alt = f" · {v[2]} m" if v[2] >= 1000 else ""
        lines.append(f"🏟 {html.escape(v[0])}, {html.escape(fx['city'])}{alt}")
    ko_local = ko.astimezone(TZ_LOCAL)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).astimezone(TZ_LOCAL).date()
    day = "Hoy" if ko_local.date() == today else ko_local.strftime("%a %d %b")
    lines.append(f"🕒 {day} {ko_local.strftime('%H:%M')} Bogotá "
                 f"({ko.strftime('%H:%M')} UTC)")
    lines.append("")
    alts = " · ".join(f"{s} ({p:.1%})" for s, p in pred["top_scores"][1:4])
    lines.append(f"🎯 Marcador más probable: <b>{pred['top_score']}</b> "
                 f"({pred['top_score_prob']:.1%})")
    lines.append(f"   Alternativas: {alts}")
    lines.append(f"📊 1X2: {h} {pred['p_home']:.0%} · Empate "
                 f"{pred['p_draw']:.0%} · {a} {pred['p_away']:.0%}")
    lines.append(f"   Goles esperados: {pred['exp_home']:.2f} – "
                 f"{pred['exp_away']:.2f}")
    lines.append(f"🔒 Confianza: {pred['confidence']}")
    if "market_p_home" in pred:
        edge = max(abs(pred["p_home"] - pred["market_p_home"]),
                   abs(pred["p_draw"] - pred["market_p_draw"]),
                   abs(pred["p_away"] - pred["market_p_away"]))
        flag = " ⚠️" if edge >= 0.07 else ""
        lines.append(f"🏦 Mercado ({pred['n_books']} casas): "
                     f"{pred['market_p_home']:.0%}/{pred['market_p_draw']:.0%}/"
                     f"{pred['market_p_away']:.0%} — divergencia máx "
                     f"{edge * 100:.0f} pts{flag}")
    lines.append("")
    lines.append("📋 " + html.escape(" | ".join(pred["factors"][:4])))
    return "\n".join(lines)


def send(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if not out.get("ok"):
        raise RuntimeError(f"Telegram respondió error: {out}")


def main():
    dry = bool(os.getenv("DRY_RUN"))
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not dry and (not token or not chat_id):
        print("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        sys.exit(1)

    upcoming = matches_in_window(force_next=bool(os.getenv("FORCE_NEXT")))
    if not upcoming:
        print("Sin partidos en la ventana de ~3 h. Nada que enviar.")
        return

    con = store.connect()
    sources.sync_results(con)
    fit, _ = ensure_fit(con)
    kt = known_teams(con)
    sources.fetch_odds(con, kt)  # 1 crédito; si no hay clave, sigue sin mercado

    for f in upcoming:
        h = canonical(f["home"], kt) or f["home"]
        a = canonical(f["away"], kt) or f["away"]
        fx = find_fixture_row(con, h, a, f["kickoff"])
        pred = P.predict_match(con, fit, fx)
        store.save_prediction(con, {**pred, "data_version":
                                    {"via": "telegram-notifier"}})
        msg = build_message(pred, fx, f["kickoff"])
        if dry:
            print("─" * 50)
            print(msg)
        else:
            send(token, chat_id, msg)
            print(f"Enviado: {h} vs {a}")


if __name__ == "__main__":
    main()
