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
