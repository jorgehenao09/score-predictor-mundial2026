# Auto-envío de pronósticos a golpredictor — Diseño (2026-06-30)

## Propósito
Subir automáticamente el marcador 🎯 (óptimo-EV del modelo) a la polla de
golpredictor **~3 horas antes de cada partido**, solo en los partidos que el
usuario aún no ha llenado, desde la nube (sin laptop encendida). El usuario
verifica por Telegram y aún puede cambiarlo manualmente antes del cierre (T-10).

**Motivación (datos):** el análisis mostró que cuando el usuario cambia los 🎯
por corazón, pierde puntos (−28 netos). El auto-envío garantiza que **no se le
pase ningún partido** con el pick del modelo, sin quitarle la decisión manual.

## Decisiones cerradas (brainstorming)
- **Dónde corre:** nube (GitHub Actions). Credenciales como GitHub Secrets
  (`GP_USER`, `GP_PASS`). El repo es público → secrets cifrados, nunca en logs.
- **Comportamiento:** rellena el 🎯 **solo en partidos vacíos**; **nunca
  sobrescribe** un marcador puesto por el usuario.
- **Timing:** ventana ancha **T-240 a T-150 min** (2.5–4h antes), idempotente.
- **Aviso:** confirmación por Telegram de lo enviado.
- **Fuera de alcance:** GitHub Pages del panel (feature aparte), sobrescritura,
  editar partidos ya cerrados (no se hace — es trampa).

## Arquitectura
```
predictor/golpredictor_client.py   (NUEVO) sesión reutilizable con golpredictor
scripts/submit_golpredictor.py     (NUEVO) orquestador del auto-envío
.github/workflows/golpredictor-submit.yml  (NUEVO) disparo en la nube
```

### `predictor/golpredictor_client.py`
Encapsula el scraping ASP.NET ya reverse-engineered. Interfaz:
- `login(user, pwd) -> Session | None` — login con viewstate; None si falla.
- `open_predictions(session) -> str` — navega a la polla (postback
  `lnkUrlPronostico`) y devuelve la URL de acción (`pooldetail.aspx?pid=...`).
- `pending_matches(session, action) -> [ {ctl, page, home, away, kickoff,
  gl_empty, gv_empty} ]` — recorre las 4 páginas de `gvPartidos`; identifica los
  partidos con cajas `txtGolLocal`/`txtGolVisitante` **vacías** (aún editables).
- `submit(session, action, page, fills) -> bool` — rellena las cajas
  `ctlNN$txtGolLocal/Visitante` de la página con los marcadores dados y postea
  `butGuardar` (con todos los campos del form + viewstate). Devuelve éxito.

Detalles ASP.NET: reusar el patrón `form_fields()` (todos los inputs del form),
override de `__EVENTTARGET`/`__EVENTARGUMENT`, y para el guardado incluir los
valores de TODAS las cajas de la página (las que no toca van con su valor
actual) + `butGuardar.x/.y` (botón imagen).

### `scripts/submit_golpredictor.py`
1. Determina qué partidos entran en la ventana **[T-240, T-150] min** (hora de
   kickoff desde football-data, igual que `notify_telegram`/`check_window`).
2. Login (`golpredictor_client.login`); si falla → avisa por Telegram y sale 0.
3. `pending_matches`; intersecta con los de la ventana **y vacíos**.
4. Para cada uno: calcula el 🎯 con `predict.predict_match` (mismo fit/estado que
   los informes) → `fills[(page, ctl)] = (gl, gv)`. Resuelve orientación
   local/visita entre golpredictor (español) y el modelo (inglés) con
   `names.canonical` (+ manual `Curazao→Curaçao`), volteando el marcador si la
   orientación difiere.
5. `submit` por página; si ok, marca dedupe y acumula para el aviso.
6. **Aviso Telegram:** "✅ Subí tus pronósticos: Francia 2-0 · Inglaterra 2-0…
   (verifica y cambia antes del cierre si quieres)".
7. **Dedupe:** marcador `data/notified/<fecha>_<home>_<away>.enviado.json`
   (commiteado, como los otros) para no reenviar/reavisar. Además el chequeo de
   "vacío" en golpredictor es dedupe intrínseco.
8. **`DRY_RUN`**: si está seteado, hace todo menos el `butGuardar` real y el
   marcador; imprime lo que enviaría (para validar sin escribir).

### Workflow `golpredictor-submit.yml`
- Disparado por `workflow_dispatch` (lo enciende el marcapasos, como
  `telegram.yml`) + un cron de respaldo en horario de partidos.
- Compuerta ligera reutilizando `scripts/check_window.py` (o su lógica) para la
  ventana de envío; si no hay nada, sale rápido.
- Corre `submit_golpredictor.py`; commitea los marcadores `*.enviado.json`
  (permisos `contents:write`, push con rebase-retry, como los otros).
- Secrets: `GP_USER`, `GP_PASS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `ODDS_API_KEY`, `FOOTBALL_DATA_TOKEN`.

## Datos / reutilización
- `predict.predict_match` para el 🎯 (ya con el uplift 1.30 vigente).
- `names.canonical` para el mapeo de nombres ES↔EN.
- `notify_telegram.send()` (o su equivalente) para el aviso.
- Ventana/kickoff: misma fuente que `check_window`/`notify_telegram`.

## Riesgos y mitigaciones
- **Cron de GitHub no fiable:** ventana ancha + idempotencia (rellena solo
  vacíos + marcador) → tolera saltos.
- **Orientación local/visita distinta entre fuentes:** voltear el marcador según
  `home_c` del modelo vs el orden de golpredictor (ya resuelto en el análisis).
- **Cambio del HTML de golpredictor:** el cliente falla de forma limpia (login o
  parseo) → avisa, no rompe otros workflows.
- **Credenciales:** solo Secrets; el script las lee de env; nunca se imprimen.

## Verificación
Sin tests formales (convención). Validar con **`DRY_RUN=1`**: correr el
orquestador y comprobar que (a) hace login, (b) detecta los partidos vacíos de
la ventana, (c) imprime los 🎯 que enviaría con la orientación correcta, sin
escribir nada. Luego una corrida real controlada en un partido próximo y
verificar en golpredictor que quedó el marcador + llegó el aviso.
