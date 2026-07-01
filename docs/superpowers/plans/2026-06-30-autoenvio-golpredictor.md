# Auto-envío de pronósticos a golpredictor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir automáticamente el marcador 🎯 del modelo a golpredictor ~3h antes de cada partido, solo en los partidos vacíos, desde la nube, con aviso por Telegram.

**Architecture:** Un cliente ASP.NET reutilizable (`golpredictor_client.py`) hace login, lee los partidos con cajas vacías y envía marcadores (botón `butGuardar`). Un orquestador (`submit_golpredictor.py`) mira la ventana de tiempo, calcula el 🎯 con `predict_match`, rellena solo vacíos, avisa por Telegram y deduplica con marcadores. Un workflow lo dispara en la nube.

**Tech Stack:** Python 3.12 (`requests` ya instalado), ASP.NET WebForms scraping, GitHub Actions. Credenciales por env (`GP_USER`, `GP_PASS`).

**Convención (IMPORTANTE):** sin tests formales. Verificación = comandos inline con `.venv/bin/python`. Las credenciales se pasan por env (`$GP_USER`/`$GP_PASS`); NUNCA escribir la contraseña en archivos (el plan se committea al repo público). Comentarios en español.

---

### Task 1: Cliente golpredictor — login y helpers

**Files:** Create `predictor/golpredictor_client.py`

- [ ] **Step 1: Crear `predictor/golpredictor_client.py` con:**

```python
"""Cliente de golpredictor (ASP.NET WebForms): login, leer pronósticos
pendientes y enviar marcadores. Credenciales por parámetro; nunca se imprimen."""
import html as _html
import re

import requests

BASE = "https://www.golpredictor.com/"
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def _clean(x):
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip()


def _form_fields(h):
    """name->value de todos los inputs del aspnetForm (para postbacks reales)."""
    f = {}
    for m in re.finditer(r"<input\b[^>]*>", h, re.I):
        tag = m.group(0)
        nm = re.search(r'name="([^"]*)"', tag)
        if not nm:
            continue
        tp = re.search(r'type="([^"]*)"', tag)
        tp = tp.group(1).lower() if tp else "text"
        if tp in ("submit", "image", "button"):
            continue
        v = re.search(r'value="([^"]*)"', tag)
        f[nm.group(1)] = _html.unescape(v.group(1)) if v else ""
    return f


def login(user, pwd):
    """requests.Session autenticada, o None si falla."""
    s = requests.Session()
    s.headers.update(_UA)
    try:
        r = s.get(BASE + "login.aspx", timeout=25)
        d = _form_fields(r.text)
        d.update({
            "ctl00$ContentPlaceInner$txtUserName": user,
            "ctl00$ContentPlaceInner$txtPassword": pwd,
            "ctl00$ContentPlaceInner$btnLogin.x": "12",
            "ctl00$ContentPlaceInner$btnLogin.y": "8",
        })
        s.post(BASE + "login.aspx", data=d, timeout=25)
    except Exception:
        return None
    return s if any("AUTH" in c.name.upper() for c in s.cookies) else None
```

- [ ] **Step 2: Verificar login (usa credenciales de env, provistas aparte).** Run:
`GP_USER="$GP_USER" GP_PASS="$GP_PASS" .venv/bin/python -c "import os; from predictor.golpredictor_client import login; s=login(os.environ['GP_USER'], os.environ['GP_PASS']); print('login OK' if s else 'login FAIL', [c.name for c in (s.cookies if s else [])])"`
Expected: `login OK ['ASP.NET_SessionId', '.WEBSITEAUTH']`

- [ ] **Step 3: Commit.**
```bash
git add predictor/golpredictor_client.py
git commit -m "golpredictor_client: login ASP.NET + helpers de formulario"
```

---

### Task 2: Cliente — navegar y detectar partidos vacíos

**Files:** Modify `predictor/golpredictor_client.py`

- [ ] **Step 1: Añadir estas funciones al final del archivo:**

```python
def open_predictions(s):
    """Navega a la polla (postback lnkUrlPronostico).
    Devuelve (action_url, html_pagina1) o (None, None)."""
    try:
        acc = s.get(BASE + "myaccount.aspx", timeout=25).text
        d = _form_fields(acc)
        d["__EVENTTARGET"] = "ctl00$ContentPlaceInner$gvPollas$ctl02$lnkUrlPronostico"
        d["__EVENTARGUMENT"] = ""
        page = s.post(BASE + "myaccount.aspx", data=d, timeout=25).text
        m = re.search(r'<form[^>]*action="([^"]+)"', page)
        return (m.group(1).lstrip("./"), page) if m else (None, None)
    except Exception:
        return None, None


def page(s, action, page1, n):
    """HTML de la página n (1..4) de gvPartidos."""
    if n == 1:
        return page1
    d = _form_fields(page1)
    d["__EVENTTARGET"] = "ctl00$ContentPlaceInner$gvPartidos"
    d["__EVENTARGUMENT"] = f"Page${n}"
    return s.post(BASE + action, data=d, timeout=25).text


def _input(row, suffix):
    """(name_completo, ctl, value) de la caja <suffix> en una fila, o (None,)*3.
    value = '' si la caja no trae atributo value (caja vacía/editable)."""
    m = re.search(r'<input\b[^>]*name="([^"]*\$(ctl\d+)\$' + suffix + r')"[^>]*>', row)
    if not m:
        return None, None, None
    v = re.search(r'value="([^"]*)"', m.group(0))
    return m.group(1), m.group(2), (v.group(1) if v else "")


def _rows(page_html):
    """Filas de gvPartidos con cajas de marcador: {ctl, home, away, empty}."""
    out = []
    gm = re.search(r'<table[^>]*id="ctl00_ContentPlaceInner_gvPartidos".*?</table>',
                   page_html, re.S)
    if not gm:
        return out
    for row in re.findall(r"<tr.*?</tr>", gm.group(0), re.S):
        nl, ctl, vl = _input(row, "txtGolLocal")
        nv, _, vv = _input(row, "txtGolVisitante")
        if not nl or not nv:
            continue
        cs = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        cs = [c for c in cs if c]
        part = cs[2].split(" - ") if len(cs) >= 3 else []
        if len(part) != 2:
            continue
        out.append({"ctl": ctl, "home": part[0].strip(), "away": part[1].strip(),
                    "empty": (vl == "" and vv == "")})
    return out


def pending_matches(s, action, page1):
    """Partidos con cajas VACÍAS en las 4 páginas: [{page, ctl, home, away}]."""
    out = []
    for n in (1, 2, 3, 4):
        h = page(s, action, page1, n)
        for r in _rows(h):
            if r["empty"]:
                out.append({"page": n, "ctl": r["ctl"],
                            "home": r["home"], "away": r["away"]})
    return out
```

- [ ] **Step 2: Verificar detección de pendientes.** Run:
`GP_USER="$GP_USER" GP_PASS="$GP_PASS" .venv/bin/python -c "import os; from predictor import golpredictor_client as C; s=C.login(os.environ['GP_USER'],os.environ['GP_PASS']); act,p1=C.open_predictions(s); pend=C.pending_matches(s,act,p1); print('action', bool(act), '| pendientes:', len(pend)); print(pend[:3])"`
Expected: `action True | pendientes: <n>` y una muestra de partidos con `page/ctl/home/away` (los que aún no tienes llenos; puede ser 0 si ya llenaste todo).

- [ ] **Step 3: Commit.**
```bash
git add predictor/golpredictor_client.py
git commit -m "golpredictor_client: navegar polla + detectar partidos vacios"
```

---

### Task 3: Cliente — enviar marcadores

**Files:** Modify `predictor/golpredictor_client.py`

- [ ] **Step 1: Añadir al final:**

```python
def submit(s, action, page_html, fills, dry=False):
    """Rellena las cajas de los ctl indicados y postea butGuardar, PRESERVANDO
    los demás marcadores de la página. fills: {ctl: (gl, gv)}.
    Si dry=True devuelve el payload (dict) sin enviar. Si no, devuelve True/False."""
    d = _form_fields(page_html)  # incluye TODAS las cajas con su valor actual
    for ctl, (gl, gv) in fills.items():
        for name in list(d):
            if name.endswith(f"${ctl}$txtGolLocal"):
                d[name] = str(gl)
            elif name.endswith(f"${ctl}$txtGolVisitante"):
                d[name] = str(gv)
    d["ctl00$ContentPlaceInner$butGuardar.x"] = "10"
    d["ctl00$ContentPlaceInner$butGuardar.y"] = "10"
    if dry:
        return d
    try:
        r = s.post(BASE + action, data=d, timeout=25)
        return "Oooops" not in r.url
    except Exception:
        return False
```

- [ ] **Step 2: Verificar construcción del payload (DRY, no envía nada).** Run:
`GP_USER="$GP_USER" GP_PASS="$GP_PASS" .venv/bin/python -c "import os; from predictor import golpredictor_client as C; s=C.login(os.environ['GP_USER'],os.environ['GP_PASS']); act,p1=C.open_predictions(s); pend=C.pending_matches(s,act,p1); import sys;\nif not pend: print('sin pendientes para probar payload'); sys.exit(0)\nm=pend[0]; pg=C.page(s,act,p1,m['page']); pl=C.submit(s,act,pg,{m['ctl']:(1,0)},dry=True); k=[x for x in pl if m['ctl'] in x and 'txtGol' in x]; print('payload OK · cajas del ctl:', {x:pl[x] for x in k}, '· butGuardar' , any('butGuardar' in x for x in pl))"`
Expected: imprime las cajas `txtGolLocal=1`/`txtGolVisitante=0` del ctl y `butGuardar True`. (Si no hay pendientes, dice eso y pasa.)

- [ ] **Step 3: Commit.**
```bash
git add predictor/golpredictor_client.py
git commit -m "golpredictor_client: enviar marcadores (butGuardar) + modo dry"
```

---

### Task 4: Orquestador `submit_golpredictor.py`

**Files:** Create `scripts/submit_golpredictor.py`

**Contexto reutilizable (ya existe):**
- `check_window.upcoming_fixtures()` → `[{home, away, kickoff(datetime UTC), date_utc}]` (nombres en inglés de football-data).
- `lineups.marker_read/marker_write(date_utc, home, away, tipo, payload)` → dedupe en `data/notified/`.
- `notify_telegram.send(token, chat_id, texto_html)`.
- `notify_telegram.find_fixture_row(con, h, a, ko)` → fixture dict para `predict_match`.
- `predictor.predict.predict_match(con, fit, fixture)` → dict con `gp_score` (el 🎯).
- `predictor.cli.ensure_fit(con)`, `predictor.store.connect()`, `predictor.names.canonical(name, known)`.

- [ ] **Step 1: Crear `scripts/submit_golpredictor.py` con:**

```python
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
from predictor import store                                     # noqa: E402
from predictor.cli import ensure_fit                            # noqa: E402
from predictor.names import canonical                           # noqa: E402

WIN_MIN, WIN_MAX = 150, 240   # ventana de envío: 2.5–4h antes
MANUAL = {"Curazao": "Curaçao"}


def _canon(name, known):
    return MANUAL.get(name) or canonical(name, known) or name


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
    fit, _ = ensure_fit(con)
    known = {x[0] for x in con.execute("SELECT DISTINCT home FROM matches")} | \
            {x[0] for x in con.execute("SELECT DISTINCT away FROM matches")}
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
        # orientación golpredictor: su 'local' es m['home']
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


def html_esc(x):
    import html as _h
    return _h.escape(str(x))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verificar en DRY_RUN (no escribe nada).** Run:
`DRY_RUN=1 FORCE_SUBMIT=1 GP_USER="$GP_USER" GP_PASS="$GP_PASS" FOOTBALL_DATA_TOKEN="$FOOTBALL_DATA_TOKEN" .venv/bin/python scripts/submit_golpredictor.py`
Expected: hace login, y O BIEN imprime `[DRY] página N: enviaría {...}` con marcadores 🎯 y el aviso, O BIEN `Nada que enviar (todo lleno).` si ya tienes todo lleno. Sin excepción y sin escribir en golpredictor.

- [ ] **Step 3: Commit.**
```bash
git add scripts/submit_golpredictor.py
git commit -m "submit_golpredictor: orquestador auto-envio (ventana T-3h, solo vacios, DRY)"
```

---

### Task 5: Workflow de GitHub Actions

**Files:** Create `.github/workflows/golpredictor-submit.yml`

- [ ] **Step 1: Crear `.github/workflows/golpredictor-submit.yml` con:**

```yaml
name: Auto-envío golpredictor (T-3h, solo vacíos)
on:
  workflow_dispatch:
  schedule:
    - cron: "9,29,49 12-23 * * *"   # respaldo; el marcapasos lo dispara además
permissions:
  contents: write
concurrency:
  group: golpredictor-submit
  cancel-in-progress: false
jobs:
  enviar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Instalar deps
        run: pip install requests numpy scipy
      - name: Auto-enviar pronósticos
        env:
          GP_USER: ${{ secrets.GP_USER }}
          GP_PASS: ${{ secrets.GP_PASS }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
          FOOTBALL_DATA_TOKEN: ${{ secrets.FOOTBALL_DATA_TOKEN }}
        run: python scripts/submit_golpredictor.py
      - name: Persistir marcadores de envío
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/notified || true
          if ! git diff --cached --quiet; then
            git commit -m "envio: $(date -u +%FT%TZ)"
            for i in 1 2 3; do git push && break; git pull --rebase; done
          fi
```

- [ ] **Step 2: Verificar que el YAML es válido.** Run:
`.venv/bin/python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/golpredictor-submit.yml')); assert d['jobs']['enviar']['steps'][-2]['run']=='python scripts/submit_golpredictor.py'; print('YAML OK', list(d['jobs']))"`
(Si falta pyyaml: `pip install pyyaml` en la venv, o validar con `.venv/bin/python -c "import json,subprocess"` alternativo. El YAML no lleva secretos literales.)
Expected: `YAML OK ['enviar']`

- [ ] **Step 3: Commit.**
```bash
git add .github/workflows/golpredictor-submit.yml
git commit -m "workflow: auto-envio golpredictor en la nube (secrets GP_USER/GP_PASS)"
```

---

## Self-Review

**Spec coverage:**
- Cliente reutilizable (login/navegar/pendientes/enviar) → Tasks 1–3. ✓
- Orquestador (ventana T-3h, 🎯, orientación, solo vacíos, aviso, marcadores, DRY) → Task 4. ✓
- Workflow nube + secrets → Task 5. ✓
- Solo rellena vacíos (nunca sobrescribe): `pending_matches` filtra `empty`; `submit` preserva las demás cajas. ✓
- Ventana ancha idempotente + dedupe (marcador `enviado`). ✓
- Aviso Telegram + DRY_RUN + fallo aislado (login None → alerta, return). ✓

**Placeholder scan:** sin TBD/TODO; código completo. Los comandos usan `$GP_USER`/`$GP_PASS` (env), nunca la contraseña literal (el plan se committea).

**Type consistency:** `login()->Session|None`; `open_predictions()->(action,page1)`; `page(s,action,page1,n)->html`; `pending_matches()->[{page,ctl,home,away}]`; `submit(s,action,page_html,fills,dry)->dict|bool`. El orquestador (Task 4) usa esas firmas exactas: agrupa `fills_by_page[page][ctl]=(gl,gv)` y llama `submit` con el html fresco de `page(...)`. `marker_write(...,"enviado",...)` casa con `marker_read(...,"enviado")`. ✓

**Nota de ejecución:** el usuario debe crear los Secrets `GP_USER` y `GP_PASS` en GitHub (Settings → Secrets → Actions) antes de que el workflow funcione en la nube; la validación local se hace con env vars.
