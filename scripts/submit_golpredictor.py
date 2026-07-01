"""Auto-envío del 🎯 a golpredictor, ~3h antes, solo en partidos vacíos.
Credenciales por env (GP_USER, GP_PASS). DRY_RUN=1 para no escribir."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_window import upcoming_fixtures                      # noqa: E402
from lineups import marker_read, marker_write                   # noqa: E402
from notify_telegram import find_fixture_row, send              # noqa: E402

from predictor import golpredictor_client as C                  # noqa: E402
from predictor import predict as P                              # noqa: E402
from predictor import sources                                   # noqa: E402
from predictor import store                                     # noqa: E402
from predictor.cli import ensure_fit                            # noqa: E402
from predictor.names import canonical                           # noqa: E402

WIN_MIN, WIN_MAX = 150, 240   # ventana de envío: 2.5–4h antes
MANUAL = {"Curazao": "Curaçao"}


def _canon(name, known):
    return MANUAL.get(name) or canonical(name, known) or name


def html_esc(x):
    import html as _h
    return _h.escape(str(x))


def main():
    dry = bool(os.getenv("DRY_RUN"))
    user, pwd = os.getenv("GP_USER"), os.getenv("GP_PASS")
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (user and pwd):
        print("Faltan GP_USER / GP_PASS"); return

    # 1) partidos en la ventana de envío, sin marcador 'enviado'
    now = datetime.now(timezone.utc)
    win = []
    for f in upcoming_fixtures():
        mins = (f["kickoff"] - now).total_seconds() / 60
        if WIN_MIN <= mins < WIN_MAX and \
                marker_read(f["date_utc"], f["home"], f["away"], "enviado") is None:
            win.append(f)
    if not win and not os.getenv("FORCE_SUBMIT"):
        print("Nada en la ventana de envío."); return

    # 2) login
    s = C.login(user, pwd)
    if s is None:
        if token and chat:
            send(token, chat, "⚠️ Auto-envío golpredictor: falló el login.")
        print("login FAIL"); return
    act, p1 = C.open_predictions(s)
    if not act:
        print("no pude abrir la polla"); return
    pending = C.pending_matches(s, act, p1)

    con = store.connect()
    sources.sync_results(con)          # BD efímera en CI: poblarla antes del fit
    fit, _ = ensure_fit(con)
    known = {x[0] for x in con.execute("SELECT DISTINCT home FROM matches")} | \
            {x[0] for x in con.execute("SELECT DISTINCT away FROM matches")}
    sources.fetch_odds(con, known, force=True)   # cuotas frescas para la mezcla
    pend_by_pair = {frozenset((_canon(m["home"], known), _canon(m["away"], known))): m
                    for m in pending}

    fills_by_page = {}        # page -> {ctl: (gl, gv)}
    enviados = []             # (fixture, "gl-gv") para aviso/marcadores
    for f in win:
        ch, ca = _canon(f["home"], known), _canon(f["away"], known)
        m = pend_by_pair.get(frozenset((ch, ca)))
        if not m:
            continue          # ya lleno, o no está en la polla
        fx = find_fixture_row(con, ch, ca, f["kickoff"])
        fx["kickoff_hour"] = f["kickoff"].hour
        pred = P.predict_match(con, fit, fx)
        gi, gj = map(int, pred["gp_score"].split("-"))   # 🎯 (orientación modelo)
        if _canon(m["home"], known) == ch:
            gl, gv = gi, gj
        else:
            gl, gv = gj, gi
        fills_by_page.setdefault(m["page"], {})[m["ctl"]] = (gl, gv)
        enviados.append((f, f"{gl}-{gv}"))

    if not enviados:
        print("Nada que enviar (todo lleno)."); return

    # 3) enviar por página (fresca para el viewstate)
    ok_all = True
    for page_n, fills in fills_by_page.items():
        pg = C.page(s, act, p1, page_n)
        res = C.submit(s, act, pg, fills, dry=dry)
        if dry:
            print(f"[DRY] página {page_n}: enviaría {fills}")
        elif not res:
            ok_all = False

    # 4) aviso + marcadores
    lines = "\n".join(f"· {html_esc(f['home'])} vs {html_esc(f['away'])}: <b>{sc}</b>"
                      for f, sc in enviados)
    msg = ("✅ <b>Auto-envío golpredictor</b> (verifica y cambia antes del cierre "
           f"si quieres):\n{lines}")
    if dry:
        print("[DRY] aviso:\n" + msg)
    else:
        if token and chat and ok_all:
            send(token, chat, msg)
        for f, sc in enviados:
            marker_write(f["date_utc"], f["home"], f["away"], "enviado",
                         {"sent_at": now.isoformat(), "score": sc})
    print(f"{'[DRY] ' if dry else ''}enviados: {len(enviados)} · ok={ok_all}")


if __name__ == "__main__":
    main()
