"""CLI en español del predictor de marcadores.

Comandos:
  sync                  Actualiza datos (resultados, Elo, FIFA, cuotas) y reajusta.
  predecir "A vs B"     Predicción de un partido (con --fecha opcional).
  jornada YYYY-MM-DD    Predicciones de todos los partidos de una fecha.
  proximos [N]          Próximos N partidos del Mundial con predicción breve.
  estado                Frescura de datos, contadores de API, modelo vigente.
  precision             Brier/RPS de las predicciones ya resueltas.
  refit [--xi X]        Fuerza el reajuste del modelo.
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone

from . import predict as P
from . import ratings, sources, store
from .names import canonical


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def known_teams(con):
    return ({r[0] for r in con.execute("SELECT DISTINCT home FROM matches")} |
            {r[0] for r in con.execute("SELECT DISTINCT away FROM matches")})


def ensure_fit(con, force=False, xi=None):
    """Reajusta el modelo si hay resultados nuevos desde el último fit."""
    fit_row, ratings_db = store.latest_fit(con)
    n_finished = con.execute(
        "SELECT COUNT(*) FROM matches WHERE home_score IS NOT NULL").fetchone()[0]
    stale = (fit_row is None or force or
             fit_row["n_matches"] != n_finished or
             (xi is not None and abs(fit_row["xi"] - xi) > 1e-9))
    if not stale:
        return {"mu": fit_row["mu"], "ha": fit_row["home_adv"],
                "rho": fit_row["rho"], "xi": fit_row["xi"],
                "ratings": ratings_db, "fit_id": fit_row["id"],
                "fitted_at": fit_row["fitted_at"]}, False
    elo = sources.fetch_elo(con, known_teams(con))
    matches = ratings.load_training_matches(con)
    fit = ratings.fit_full(matches, _today(), elo=elo,
                           xi=xi or ratings.XI_DEFAULT)
    fit_id = store.save_fit(con, fit["xi"], fit["rho"], fit["ha"], fit["mu"],
                            n_finished, _today(), fit["ratings"])
    fit["fit_id"] = fit_id
    fit["fitted_at"] = store.now_iso()
    return fit, True


def light_sync(con):
    """Sincronización respetando TTLs de caché. Devuelve lista de avisos."""
    notes = []
    try:
        new, src = sources.sync_results(con)
        if new:
            notes.append(f"+{new} resultados nuevos desde {src}")
    except Exception as e:
        notes.append(f"⚠ resultados: {e}")
    kt = known_teams(con)
    sources.fetch_fifa(con, kt)
    n_odds, warn = sources.fetch_odds(con, kt)
    if n_odds > 0:
        notes.append(f"snapshot de cuotas guardado ({n_odds} partidos)")
    if warn:
        notes.append(warn)
    return notes


def find_fixtures(con, home=None, away=None, fecha=None, limit=20):
    q = ("SELECT date, home, away, city, country, neutral FROM matches "
         "WHERE home_score IS NULL AND date >= ?")
    args = [fecha or _today()]
    if fecha:
        q = q.replace("date >= ?", "date = ?")
    if home:
        q += " AND ((home=? AND away=?) OR (home=? AND away=?))"
        args += [home, away, away, home]
    q += " ORDER BY date LIMIT ?"
    args.append(limit)
    cols = ["date", "home", "away", "city", "country", "neutral"]
    return [dict(zip(cols, r)) for r in con.execute(q, args).fetchall()]


def data_version(con, fit):
    return {
        "resultados": store.get_meta(con, "last_results_sync", "nunca"),
        "cuotas": store.get_meta(con, "last_odds_sync", "sin datos"),
        "modelo": f"fit #{fit.get('fit_id', '?')} ({fit.get('fitted_at', '?')})",
    }


def print_prediction(con, fit, fx, brief=False):
    pred = P.predict_match(con, fit, fx)
    prev = store.previous_prediction(con, fx["home"], fx["away"], fx["date"])
    pred["data_version"] = data_version(con, fit)
    store.save_prediction(con, pred)

    h, a = fx["home"], fx["away"]
    if brief:
        print(f"  {fx['date']}  {h} vs {a}  →  {pred['top_score']}  "
              f"(1X2: {pred['p_home']:.0%}/{pred['p_draw']:.0%}/"
              f"{pred['p_away']:.0%}, conf. {pred['confidence']})")
        return

    line = "═" * 64
    print(line)
    print(f"  {h} vs {a}")
    venue = fx.get("city", "")
    info = f"  {fx['date']}"
    if venue:
        from .venues import VENUES
        v = VENUES.get(venue)
        info += f" · {v[0] + ', ' if v else ''}{venue}"
    print(info)
    print(line)
    print(f"\n  Consulta: {store.now_iso()}")
    dv = pred["data_version"]
    print(f"  Datos usados: resultados {dv['resultados']} · "
          f"cuotas {dv['cuotas']} · {dv['modelo']}")

    if prev:
        dh = pred["p_home"] - prev["p_home"]
        if abs(dh) >= 0.005 or prev["top_score"] != pred["top_score"]:
            print(f"\n  Desde tu última consulta ({prev['created_at']}):")
            print(f"    1X2 era {prev['p_home']:.0%}/{prev['p_draw']:.0%}/"
                  f"{prev['p_away']:.0%} → ahora {pred['p_home']:.0%}/"
                  f"{pred['p_draw']:.0%}/{pred['p_away']:.0%}")
            if prev["top_score"] != pred["top_score"]:
                print(f"    Marcador más probable era {prev['top_score']} → "
                      f"ahora {pred['top_score']}")
        else:
            print(f"\n  Sin cambios desde tu última consulta ({prev['created_at']})")

    print(f"\n  ► MARCADOR MÁS PROBABLE: {pred['top_score']} "
          f"({pred['top_score_prob']:.1%})")
    others = "  ".join(f"{s} ({p:.1%})" for s, p in pred["top_scores"][1:4])
    print(f"    Alternativas: {others}")
    print(f"\n  ► 1X2:  {h} {pred['p_home']:.1%}  ·  "
          f"Empate {pred['p_draw']:.1%}  ·  {a} {pred['p_away']:.1%}")
    print(f"    Goles esperados: {pred['exp_home']:.2f} - {pred['exp_away']:.2f}")
    print(f"\n  ► CONFIANZA: {pred['confidence']}")
    if "market_p_home" in pred:
        print(f"\n  ► MODELO vs MERCADO ({pred['n_books']} casas, "
              f"margen medio {pred['margin']:.1%}):")
        for label, pm, pk in [(h, pred["p_home"], pred["market_p_home"]),
                              ("Empate", pred["p_draw"], pred["market_p_draw"]),
                              (a, pred["p_away"], pred["market_p_away"])]:
            d = pm - pk
            flag = "  ← divergencia" if abs(d) >= 0.07 else ""
            print(f"    {label:<16} modelo {pm:>5.1%} · mercado {pk:>5.1%} "
                  f"({d:+.1%}){flag}")
    else:
        print("\n  ► MERCADO: sin cuotas disponibles "
              "(configura ODDS_API_KEY o ejecuta `sync`)")
    print("\n  ► FACTORES:")
    for f in pred["factors"]:
        print(f"    · {f}")
    print()


def resolve_team(con, name, kt=None):
    kt = kt or known_teams(con)
    c = canonical(name, kt)
    if not c:
        print(f"No reconozco la selección '{name}'. Prueba el nombre en "
              "inglés (p.ej. 'Spain') o español ('España').")
        sys.exit(1)
    return c


def cmd_predecir(args):
    con = store.connect()
    for n in light_sync(con):
        print(f"  [sync] {n}")
    fit, refitted = ensure_fit(con)
    if refitted:
        print("  [modelo] reajustado con los últimos resultados")
    if " vs " in args.partido.lower():
        parts = args.partido.lower().split(" vs ")
    elif "-" in args.partido:
        parts = args.partido.split("-", 1)
    else:
        print("Formato: \"EquipoA vs EquipoB\"")
        sys.exit(1)
    kt = known_teams(con)
    h = resolve_team(con, parts[0].strip(), kt)
    a = resolve_team(con, parts[1].strip(), kt)
    fxs = find_fixtures(con, h, a, fecha=args.fecha)
    if not fxs:
        # sin fixture programado: predicción hipotética en cancha neutral
        print(f"\n  (No hay fixture programado {h} vs {a}; "
              "predicción hipotética en cancha neutral)")
        fxs = [{"date": args.fecha or _today(), "home": h, "away": a,
                "city": "", "country": "", "neutral": 1}]
    print_prediction(con, fit, fxs[0])


def cmd_jornada(args):
    con = store.connect()
    for n in light_sync(con):
        print(f"  [sync] {n}")
    fit, _ = ensure_fit(con)
    fxs = find_fixtures(con, fecha=args.fecha, limit=50)
    if not fxs:
        print(f"No hay partidos programados el {args.fecha}.")
        return
    print(f"\nPartidos del {args.fecha} ({len(fxs)}):\n")
    for fx in fxs:
        print_prediction(con, fit, fx, brief=not args.detalle)


def cmd_proximos(args):
    con = store.connect()
    for n in light_sync(con):
        print(f"  [sync] {n}")
    fit, _ = ensure_fit(con)
    fxs = find_fixtures(con, limit=args.n)
    print(f"\nPróximos {len(fxs)} partidos:\n")
    for fx in fxs:
        print_prediction(con, fit, fx, brief=True)


def cmd_sync(args):
    con = store.connect()
    kt_before = None
    try:
        new, src = sources.sync_results(con, force=True)
        print(f"  resultados: +{new} nuevos finalizados ({src})")
    except Exception as e:
        print(f"  ⚠ resultados: {e}")
    kt = known_teams(con)
    elo = sources.fetch_elo(con, kt, force=True)
    print(f"  elo: {len(elo)} selecciones")
    fifa = sources.fetch_fifa(con, kt, force=True)
    print(f"  fifa: {len(fifa)} selecciones")
    n_odds, warn = sources.fetch_odds(con, kt, force=args.cuotas)
    if n_odds == -1:
        print("  cuotas: snapshot reciente en caché (usa --cuotas para forzar)")
    else:
        print(f"  cuotas: {n_odds} partidos con cuotas guardadas")
    if warn:
        print(f"  {warn}")
    fd, fd_warn = sources.fetch_fd_fixtures(con)
    if fd:
        print(f"  football-data.org: {len(fd)} partidos WC (validación cruzada OK)")
    elif fd_warn:
        print(f"  football-data.org: {fd_warn}")
    fit, refitted = ensure_fit(con)
    print(f"  modelo: {'reajustado' if refitted else 'al día'} "
          f"(fit #{fit.get('fit_id', '?')})")


def cmd_estado(args):
    con = store.connect()
    print("\nESTADO DEL SISTEMA\n" + "─" * 40)
    print(f"  Resultados sincronizados: "
          f"{store.get_meta(con, 'last_results_sync', 'nunca')}")
    print(f"  Último snapshot de cuotas: "
          f"{store.get_meta(con, 'last_odds_sync', 'sin datos')}")
    n_snap = con.execute("SELECT COUNT(DISTINCT fetched_at) "
                         "FROM odds_snapshots").fetchone()[0]
    n_match = con.execute("SELECT COUNT(*) FROM matches "
                          "WHERE home_score IS NOT NULL").fetchone()[0]
    n_fix = con.execute("SELECT COUNT(*) FROM matches "
                        "WHERE home_score IS NULL AND date>=?",
                        (_today(),)).fetchone()[0]
    print(f"  Partidos con resultado: {n_match} · fixtures futuros: {n_fix}")
    print(f"  Snapshots de cuotas acumulados: {n_snap} "
          "(histórico propio apertura/cierre)")
    fit_row, _ = store.latest_fit(con)
    if fit_row:
        print(f"  Modelo: fit #{fit_row['id']} de {fit_row['fitted_at']} "
              f"(xi={fit_row['xi']}, rho={fit_row['rho']:.3f}, "
              f"{fit_row['n_matches']} partidos)")
    print("\n  Consumo de APIs (hoy / este mes):")
    for src_name, (period, cap) in sources.LIMITS.items():
        used = (store.requests_this_month(con, src_name) if period == "mes"
                else store.requests_today(con, src_name))
        print(f"    {src_name:<15} {used:>4} / {cap} por {period}")
    for key in (("ODDS_API_KEY", "The Odds API"),
                ("FOOTBALL_DATA_TOKEN", "football-data.org"),
                ("BSD_TOKEN", "BSD API (experimental)")):
        ok = "configurada" if os.getenv(key[0]) else "FALTA (.env)"
        print(f"    clave {key[1]:<25} {ok}")


def cmd_precision(args):
    con = store.connect()
    rows = con.execute(
        """SELECT p.home, p.away, p.match_date, p.p_home, p.p_draw, p.p_away,
                  p.top_score, m.home_score, m.away_score
           FROM predictions p JOIN matches m
             ON m.home=p.home AND m.away=p.away AND m.date=p.match_date
           WHERE m.home_score IS NOT NULL
             AND p.id IN (SELECT MAX(id) FROM predictions
                          WHERE substr(created_at, 1, 10) <= match_date
                          GROUP BY home, away, match_date)
        """).fetchall()
    if not rows:
        print("Aún no hay predicciones resueltas para evaluar.")
        return
    briers, rpss, hits1x2, hits_exact = [], [], 0, 0
    for h, a, d, ph, pd_, pa, ts, hs, as_ in rows:
        outcome = 0 if hs > as_ else (1 if hs == as_ else 2)
        probs = (ph, pd_, pa)
        briers.append(P.brier(probs, outcome))
        rpss.append(P.rps(probs, outcome))
        if max(range(3), key=lambda i: probs[i]) == outcome:
            hits1x2 += 1
        if ts == f"{hs}-{as_}":
            hits_exact += 1
    n = len(rows)
    print(f"\nPRECISIÓN ({n} predicciones resueltas)\n" + "─" * 40)
    print(f"  Brier medio (1X2):    {sum(briers) / n:.4f}  (0=perfecto, "
          "0.667=azar uniforme)")
    print(f"  RPS medio:            {sum(rpss) / n:.4f}  (0=perfecto)")
    print(f"  Acierto 1X2:          {hits1x2}/{n} ({hits1x2 / n:.0%})")
    print(f"  Acierto marcador:     {hits_exact}/{n} ({hits_exact / n:.0%})")


def cmd_panel(args):
    import webbrowser

    from . import panel as panel_mod
    con = store.connect()
    for n in light_sync(con):
        print(f"  [sync] {n}")
    fit, refitted = ensure_fit(con)
    if refitted:
        print("  [modelo] reajustado con los últimos resultados")
    fxs = find_fixtures(con, limit=args.n)
    preds = []
    for fx in fxs:
        pred = P.predict_match(con, fit, fx)
        pred["data_version"] = data_version(con, fit)
        store.save_prediction(con, pred)
        preds.append(pred)
    path = panel_mod.render(con, preds, data_version(con, fit))
    print(f"Panel generado: {path}")
    if not args.no_abrir:
        webbrowser.open(f"file://{path}")


def cmd_refit(args):
    con = store.connect()
    fit, _ = ensure_fit(con, force=True, xi=args.xi)
    print(f"Modelo reajustado: fit #{fit['fit_id']} "
          f"(xi={fit['xi']}, rho={fit['rho']:.4f}, ha={fit['ha']:.3f})")


def main():
    ap = argparse.ArgumentParser(
        prog="predictor",
        description="Predictor de marcadores del Mundial 2026 "
                    "(datos gratuitos, conocimiento continuo)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("predecir", help="predice un partido: \"A vs B\"")
    p.add_argument("partido")
    p.add_argument("--fecha", default=None)
    p.set_defaults(fn=cmd_predecir)

    p = sub.add_parser("jornada", help="predice todos los partidos de una fecha")
    p.add_argument("fecha")
    p.add_argument("--detalle", action="store_true")
    p.set_defaults(fn=cmd_jornada)

    p = sub.add_parser("proximos", help="próximos N partidos")
    p.add_argument("n", nargs="?", type=int, default=10)
    p.set_defaults(fn=cmd_proximos)

    p = sub.add_parser("panel", help="genera y abre el panel HTML local")
    p.add_argument("n", nargs="?", type=int, default=16,
                   help="cuántos partidos próximos mostrar (def. 16)")
    p.add_argument("--no-abrir", action="store_true",
                   help="solo generar, sin abrir el navegador")
    p.set_defaults(fn=cmd_panel)

    p = sub.add_parser("sync", help="actualiza todas las fuentes ahora")
    p.add_argument("--cuotas", action="store_true",
                   help="fuerza snapshot de cuotas (gasta 1 crédito)")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("estado", help="frescura de datos y consumo de APIs")
    p.set_defaults(fn=cmd_estado)

    p = sub.add_parser("precision", help="Brier/RPS de predicciones resueltas")
    p.set_defaults(fn=cmd_precision)

    p = sub.add_parser("refit", help="fuerza reajuste del modelo")
    p.add_argument("--xi", type=float, default=None)
    p.set_defaults(fn=cmd_refit)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
