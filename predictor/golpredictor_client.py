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
