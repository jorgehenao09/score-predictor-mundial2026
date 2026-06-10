"""Envía a Telegram los informes PREVIA (~3 h antes) y CIERRE (al publicarse
las alineaciones, típicamente T-65) de cada partido del Mundial.

Corre en GitHub Actions (estado entre runs = marcadores commiteados en
data/notified/) y también en local.

Variables de entorno:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (obligatorias salvo DRY_RUN)
  ODDS_API_KEY, FOOTBALL_DATA_TOKEN      (opcionales)
  FORCE_TYPE=previa|cierre               (test: fuerza el próximo partido)
  DRY_RUN=1                              (imprime en vez de enviar)
"""

import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_window import due_actions                 # noqa: E402
from lineups import (bsd_unavailable, get_lineups,   # noqa: E402
                     marker_read, marker_write)
from predictor import predict as P                  # noqa: E402
from predictor import sources, store                # noqa: E402
from predictor.cli import ensure_fit, known_teams   # noqa: E402
from predictor.names import canonical               # noqa: E402
from predictor.venues import VENUES                 # noqa: E402

TZ_LOCAL = ZoneInfo("America/Bogota")
GOLPREDICTOR_LOCK_MIN = 10  # verificado: golpredictor.com bloquea a T-10


def find_fixture_row(con, h, a, ko):
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


def _fmt_when(ko):
    ko_l = ko.astimezone(TZ_LOCAL)
    today = datetime.now(timezone.utc).astimezone(TZ_LOCAL).date()
    day = "Hoy" if ko_l.date() == today else ko_l.strftime("%a %d %b")
    lock = (ko - timedelta(minutes=GOLPREDICTOR_LOCK_MIN)).astimezone(TZ_LOCAL)
    return (f"🕒 {day} {ko_l.strftime('%H:%M')} Bogotá "
            f"({ko.strftime('%H:%M')} UTC)\n"
            f"⏳ golpredictor bloquea a las {lock.strftime('%H:%M')}")


def _fmt_xi(side_label, side):
    names = ", ".join(p["name"].split()[-1] +
                      (" (C)" if p.get("captain") else "")
                      for p in side["players"])
    form = f" ({side['formation']})" if side.get("formation") else ""
    return f"📋 <b>{html.escape(side_label)}</b>{form}: {html.escape(names)}"


def _market_block(pred, prev_marker):
    """Línea de mercado actual + interpretación del movimiento desde la previa."""
    if "market_p_home" not in pred:
        return ["🏦 Mercado: sin cuotas disponibles"]
    out = [f"🏦 Mercado AHORA ({pred['n_books']} casas): "
           f"{pred['market_p_home']:.0%}/{pred['market_p_draw']:.0%}/"
           f"{pred['market_p_away']:.0%}"]
    pm = (prev_marker or {}).get("market")
    if pm:
        dh = pred["market_p_home"] - pm["ph"]
        da = pred["market_p_away"] - pm["pa"]
        big = max(abs(dh), abs(da))
        det = (f"   Desde la previa: local {pm['ph']:.0%}→"
               f"{pred['market_p_home']:.0%} ({dh:+.0%}) · visita "
               f"{pm['pa']:.0%}→{pred['market_p_away']:.0%} ({da:+.0%})")
        if big >= 0.04:
            det += "\n   ⚠️ El mercado reaccionó FUERTE a las alineaciones"
        elif big >= 0.02:
            det += "\n   Movimiento moderado tras las alineaciones"
        else:
            det += "\n   Sin sorpresas: el mercado apenas se movió"
        out.append(det)
    return out


def _fmt_bajas(pred, bajas):
    if not bajas:
        return []
    out = ["🚑 Bajas (lesión/sanción, fuente BSD experimental):"]
    for side, label in (("home", pred["home"]), ("away", pred["away"])):
        items = bajas.get(side) or []
        if items:
            det = ", ".join(
                f"{p['name']}" + (f" ({p['reason']})" if p.get("reason") else "")
                for p in items[:6])
            out.append(f"   {html.escape(label)}: {html.escape(det)}")
        else:
            out.append(f"   {html.escape(label)}: sin bajas reportadas")
    return out


def build_message(tipo, pred, fx, ko, lineups, prev_marker, bajas=None):
    h, a = html.escape(pred["home"]), html.escape(pred["away"])
    head = ("🚨 <b>INFORME DE CIERRE</b>" if tipo == "cierre"
            else "📅 <b>INFORME PREVIA (~3 h antes)</b>")
    lines = [head, f"⚽ <b>{h} vs {a}</b>"]
    v = VENUES.get(fx.get("city", ""))
    if v:
        alt = f" · {v[2]} m" if v[2] >= 1000 else ""
        lines.append(f"🏟 {html.escape(v[0])}, {html.escape(fx['city'])}{alt}")
    lines.append(_fmt_when(ko))
    lines.append("")
    if tipo == "cierre":
        if lineups:
            lines.append(f"✅ Alineaciones confirmadas (vía {lineups['source']}):")
            lines.append(_fmt_xi(pred["home"], lineups["home"]))
            lines.append(_fmt_xi(pred["away"], lineups["away"]))
        else:
            lines.append("⚠️ FIFA aún no publica las XI — informe enviado "
                         "para que alcances a registrar tu marcador")
        lines += _fmt_bajas(pred, bajas)
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
    lines += _market_block(pred, prev_marker if tipo == "cierre" else None)
    if tipo == "previa":
        lines.append("")
        lines.append("💡 Registra ya este marcador en golpredictor; con el "
                     "informe de cierre (al salir las alineaciones) lo ajustas "
                     "si hace falta.")
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

    due = due_actions(probe_lineups=False)  # el gate ya decidió; no re-sondear
    if not due:
        print("Nada que enviar.")
        return

    con = store.connect()
    sources.sync_results(con)
    fit, _ = ensure_fit(con)
    kt = known_teams(con)
    sources.fetch_odds(con, kt, force=True)  # cuotas frescas: 1 crédito/run

    for d in due:
        h = canonical(d["home"], kt) or d["home"]
        a = canonical(d["away"], kt) or d["away"]
        fx = find_fixture_row(con, h, a, d["kickoff"])
        fx["kickoff_hour"] = d["kickoff"].hour  # para la capa de clima
        pred = P.predict_match(con, fit, fx)
        store.save_prediction(con, {**pred, "data_version":
                                    {"via": f"telegram-{d['tipo']}"}})
        lineups, bajas = None, None
        if d["tipo"] == "cierre":
            lineups = get_lineups(d["home"], d["away"], d["date_utc"])
            try:
                bajas = bsd_unavailable(d["home"], d["away"], d["date_utc"])
            except Exception:
                bajas = None
        prev_marker = marker_read(d["date_utc"], d["home"], d["away"], "previa")
        msg = build_message(d["tipo"], pred, fx, d["kickoff"], lineups,
                            prev_marker, bajas=bajas)
        if dry:
            print("─" * 50)
            print(msg)
        else:
            send(token, chat_id, msg)
            print(f"Enviado [{d['tipo']}]: {h} vs {a}")
        payload = {"sent_at": store.now_iso(), "tipo": d["tipo"],
                   "p_home": pred["p_home"], "p_draw": pred["p_draw"],
                   "p_away": pred["p_away"], "top_score": pred["top_score"],
                   "lineups_source": (lineups or {}).get("source")}
        if "market_p_home" in pred:
            payload["market"] = {"ph": pred["market_p_home"],
                                 "pd": pred["market_p_draw"],
                                 "pa": pred["market_p_away"],
                                 "n_books": pred["n_books"]}
        # con FORCE_TYPE activo (tests) no se escribe marcador: un test de hoy
        # no debe bloquear el informe real de mañana
        forced = os.getenv("FORCE_TYPE", "").strip().lower() in ("previa",
                                                                 "cierre")
        if not dry and not forced:
            marker_write(d["date_utc"], d["home"], d["away"], d["tipo"],
                         payload)


if __name__ == "__main__":
    main()
