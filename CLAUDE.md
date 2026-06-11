# Score Predictor — Mundial 2026

Sistema personal de predicción de marcadores de fútbol (Mundial 2026) con
"conocimiento continuo": cada consulta usa los datos más recientes, recalcula
y muestra qué cambió desde la consulta anterior. **Solo fuentes gratuitas.**

## Convenciones del proyecto

- **Simple a propósito**: sin tests formales, sin frameworks, sin capas de
  abstracción extra. Es una herramienta personal; el esfuerzo va al núcleo
  estadístico y a la ingesta de datos. (Decisión explícita del usuario.)
- Python 3.12 en `.venv` (creado con `/opt/homebrew/bin/python3.12`; el
  python3 por defecto del sistema es un 3.8 alfa inservible).
- Salida de la CLI y comentarios del código en **español**; nombres de equipo
  canónicos en inglés (los de martj42), con alias español→inglés en `names.py`.
- Claves en `.env` (ver `.env.example`), nunca hardcodeadas.
- SQLite en `data/predictor.db`; descargas crudas cacheadas en `data/cache/`
  con TTL por fuente ("¿pudo haber cambiado esto?").

## Cómo ejecutar

```bash
.venv/bin/python -m predictor sync                # actualizar todo ahora
.venv/bin/python -m predictor predecir "Mexico vs South Africa"
.venv/bin/python -m predictor predecir "España vs Brasil"   # acepta español
.venv/bin/python -m predictor jornada 2026-06-11 [--detalle]
.venv/bin/python -m predictor proximos 10
.venv/bin/python -m predictor panel [N]           # panel HTML local (abre navegador)
.venv/bin/python -m predictor estado              # frescura + consumo de APIs
.venv/bin/python -m predictor precision           # Brier/RPS de lo ya resuelto
.venv/bin/python -m predictor refit [--xi 0.0005]
.venv/bin/python scripts/backtest.py              # validación WC2022
```

## Arquitectura (módulos en `predictor/`)

| Módulo | Qué hace |
|---|---|
| `sources.py` | Clientes de todas las APIs: caché TTL, cascada de respaldo, contadores de peticiones contra los límites free, degradación elegante si falta una clave o cae una fuente |
| `store.py` | SQLite: partidos, snapshots de cuotas (histórico propio apertura/cierre), fits, predicciones versionadas, log de peticiones |
| `names.py` | Resolución de nombres entre fuentes (martj42 es el canónico) + alias en español |
| `venues.py` | Las 16 sedes WC2026 hardcodeadas: estadio, altitud, coordenadas, zona horaria |
| `ratings.py` | **Núcleo**: Dixon-Coles ponderado (ataque/defensa por selección, decaimiento temporal, peso por torneo, corrección rho de marcadores bajos, ridge, prior Elo para equipos con poca muestra). Ajuste en 2 pasos: Poisson penalizado con gradiente analítico (L-BFGS) + rho por verosimilitud perfilada 1-D |
| `market.py` | De-vigging: proporcional y **método de Shin** (preferido); consenso mediana entre casas. Comprobaciones inline: `python -m predictor.market` |
| `predict.py` | Matriz de goles 0-10 con tau DC → marcador exacto + 1X2 + confianza + factores en español. Ajustes de contexto: altitud (≥1500 m, -7% no aclimatados), descanso (-3%/día de déficit, tope 9%), ventaja local vía flag `neutral` del dataset |
| `cli.py` | Comandos; auto-sync ligero (respeta TTLs) y auto-refit si llegaron resultados nuevos |
| `panel.py` | Panel HTML estático (`data/panel.html`): tarjetas con marcador, barras 1X2 modelo-vs-mercado, factores. Sin servidor |

## Decisiones de modelado y por qué

- **xi = 0.0005** (vida media ~3.8 años), validado por backtest en WC2018 y
  WC2022: RPS 0.217/0.216, acierto 1X2 56%/48%, marcador exacto 9.4% en ambos.
  Referencia: modelos publicados ~0.19–0.21 RPS; casas de apuestas ~0.18–0.19.
- Ventaja local estimada de los datos: +0.272 en log-goles (~+31%); se aplica
  solo cuando `neutral=0` (anfitriones USA/México/Canadá en sus sedes).
- rho ≈ −0.034 (corrección DC de marcadores bajos), signo esperado.
- El peso por torneo (Mundial 2.0 … amistoso 0.6) está en
  `ratings.TOURNAMENT_W`, heurístico, no validado exhaustivamente.
- Prior Elo: para selecciones con poca muestra efectiva (eff < ~10) la fuerza
  se mezcla con la implícita en su Elo (regresión sobre equipos con datos).
- Sin xG: no existe fuente gratuita fiable de xG internacional (ver abajo).
  El filtrado de suerte recae en el decaimiento temporal + peso por rival
  implícito en el modelo.
- **Mezcla modelo+mercado (2026-06-10)**: el marcador final sale de
  `M = (1-w)·M_modelo + w·M_mercado`. **El peso w se AUTOAJUSTA**
  (`predictor/learning.py`, 2026-06-11): los marcadores de cierre guardan las
  probs del modelo y del mercado por partido; con ≥6 partidos resueltos se
  busca en grilla el w que minimiza el RPS y se encoge hacia 0.5 con 10
  pseudo-partidos. La memoria son los marcadores commiteados (misma en local
  y nube). Override manual: env `PREDICTOR_BLEND`. Validado con sintéticos:
  mercado superior en 8 partidos → w 0.722.
  La matriz del mercado se resuelve con `predict.implied_lambdas`: las λ que
  reproducen el 1X2 Shin + P(over) del mercado de totales (The Odds API pide
  `markets=h2h,totals` = 2 créditos/llamada; línea modal, normalmente 2.5).
  Solver validado: recupera λ conocidas con error <0.001. `precision` compara
  los tres motores (puro/mercado/mezcla) sobre partidos resueltos
  (columnas model_p_* en predictions, migración idempotente en store.connect).
- **Calibración por marcador: medida y DESCARTADA** (resultado negativo
  honesto): con 15.505 partidos out-of-sample 2010-2025, los ratios
  observado/esperado por marcador quedaron cerca de 1 (1-1 crudo 0.92,
  0-0 1.05) y al validar en WC2018+22 el exacto empeoraba (9.4%→8.6%).
  `scripts/calibrate_scores.py` solo escribe la tabla si mejora; no mejoró.
  `predictor/calibration.py` queda como identidad (hook listo si algún día
  se regenera con más datos).
- **Clima (2026-06-10)**: Open-Meteo (gratis, sin clave) con lat/lon de
  `venues.py`; hora del kickoff desde football-data (martj42 no trae horas) o
  pasada por el notificador. Penalización: ≥32°C −3%, ≥35°C −5% a ambos;
  nota informativa desde 28°C. `predictor/weather.py`.

## Fuentes gratuitas (verificadas el 2026-06-09)

| Fuente | Datos | Límite real | Clave | Rol |
|---|---|---|---|---|
| martj42/international_results (GitHub) | Historial completo desde 1872 + fixtures WC2026, actualizado a diario | ninguno | no | **Primaria**: entrenamiento + fixtures |
| eloratings.net (`World.tsv`) | Elo de 240 selecciones | ser educado; caché 24 h | no | Prior de fuerza |
| FIFA ranking (JSON no oficial `inside.fifa.com/api/ranking-overview?dateId=id14870`) | 211 selecciones | no oficial, puede romperse | no | Secundaria |
| The Odds API | Cuotas 1X2 multi-casa del Mundial (`soccer_fifa_world_cup`) | **500 créditos/mes** (~1-2 snapshots/día, región `eu`) | `ODDS_API_KEY` | **Primaria cuotas**; cada snapshot se persiste → histórico propio apertura/cierre |
| football-data.org | Fixtures/resultados WC (validación cruzada) | 10 req/min | `FOOTBALL_DATA_TOKEN` | Respaldo/validación |
| TheSportsDB (clave pública `123`, liga 4429) | Fixtures, escudos, sedes | ~30 req/min | no | Respaldo |
| Wikipedia | Altitud/datos de las 16 sedes | estático | no | Hardcodeado en `venues.py` |
| BSD API (sports.bzzoiro.com) | **AUDITADO 2026-06-10 con token**: bajas estructuradas (name/status/reason) ✓, XI confirmadas con `lineup_status` ✓, cuotas 16 casas que cruzan con nuestro consenso ✓, clima ✓, stats (big_chances) ✓. **xG NO disponible** (solo en LiveScore en vivo). Filtros con quirks (`team_name` en squads se ignora; usar `date_from/to`, `league_id=27`=WC2026) | 429 documentado, límite no especificado | `BSD_TOKEN` | Capa 5 (bajas) + 3ª fuente XI + respaldo de cuotas. Sigue siendo proveedor joven: siempre detrás de FIFA/ESPN/OddsAPI, nunca único |
| ~~API-Football free~~ | — | temporadas actuales bloqueadas en el tier gratis (devuelve 200 vacíos) | — | **Descartada** |
| ~~Understat / FotMob~~ | xG solo clubes / scraping bloqueado | — | — | **Descartadas** |

## Capas del modelo: cobertura real con datos gratis

**FUERTES**: L1 ratings (DC + Elo + FIFA), L3 forma con decaimiento,
L4 contexto (altitud/descanso/local), L6 H2H (implícito en datos),
L7 mercado (Shin + histórico propio de snapshots).

**MEDIA**: L5 lesiones/plantillas — el BSD (auditado) da bajas estructuradas
con motivo; se muestran en el informe de cierre como información (no ajustan
el modelo: sin valor de mercado por jugador, el ajuste cuantitativo lo da el
movimiento del mercado post-alineaciones).

**DÉBILES**: L2 xG (sin fuente gratuita internacional — el BSD solo lo tiene
en vivo, no pre/post partido), L8 intangibles (solo heurísticas de descanso
y calor; falta rotación esperada).

## Informes Telegram en la nube (sin laptop encendida)

- Repo **público** (decisión del usuario, 2026-06-10: minutos ilimitados de
  Actions): `jorgehenao09/score-predictor-mundial2026`. Canal privado
  "Predicciones mundial 2026"; secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
  ODDS_API_KEY, FOOTBALL_DATA_TOKEN (todos configurados).
- **DOS informes por partido** (`scripts/notify_telegram.py`):
  - **PREVIA** — ventana [T-230, T-150) min: predicción + mercado + factores +
    recordatorio de registrar marcador preliminar en golpredictor.
  - **CIERRE** — ventana [T-85, T-10): se dispara apenas FIFA publique las XI
    confirmadas; red de seguridad: a T-40 sale sí o sí aunque no haya XI.
    Contiene XI de ambos equipos, movimiento del mercado desde la previa
    (umbral: ≥4 pts "reaccionó FUERTE", ≥2 "moderado") y hora de bloqueo de
    golpredictor.
- Hechos verificados que fijan los tiempos (2026-06-10):
  - Reglamento FIFA WC26 Art. 32: planillas se entregan a T-90; se publican
    cuando ambos equipos entregan; en la práctica T-75..T-60.
  - golpredictor.com bloquea ingreso/edición a **T-10** (regulation.aspx/faq).
  - Kickoffs del torneo: todos entre 16:00 y 04:00 UTC; solo 5 partidos a :30.
- **Alineaciones** (`scripts/lineups.py`, solo stdlib): api.fifa.com primaria
  (calendar → IdMatch/IdStage; live endpoint: 11 jugadores Status==1 por
  equipo = confirmadas; competición 17, temporada 285023) → ESPN summary
  (rosters con starter:true) de respaldo. FotMob documentado como 3ª opción
  pero no implementado (riesgo de bloqueo).
- **Cron cada 10 min** (minutos 4,14,…) horas UTC 12-23 y 0-3. Compuerta
  stdlib `scripts/check_window.py` (~5-10 s si no toca nada). Dedupe por
  **marcadores** en `data/notified/` (JSON por partido+tipo, commiteados por
  el workflow con permissions contents:write y push con rebase-retry). El
  marcador de la previa guarda las probs del mercado → el cierre calcula el
  delta. FORCE_TYPE=previa|cierre fuerza tests SIN escribir marcador.
- Consumo The Odds API: 1 crédito por informe enviado (~208 en el torneo) +
  snapshots locales; el contador local (`estado`) no ve el consumo de la nube.
- Test manual: Actions → Run workflow → force_type=previa|cierre.

## Estado y pendientes

- [x] Núcleo completo y validado (ratings, de-vig, CLI, persistencia, backtest)
- [x] Claves de football-data.org y The Odds API configuradas (2026-06-10);
  primer snapshot de cuotas = líneas de apertura del torneo guardadas
- [x] Panel HTML local (`panel`)
- [ ] Probar BSD API con token (calidad de xG/lesiones) durante la fase de grupos
- [ ] Entrada manual de bajas (`--ausencias` o archivo local) ponderada por importancia
- [ ] Revisar `precision` cuando haya partidos resueltos del Mundial
