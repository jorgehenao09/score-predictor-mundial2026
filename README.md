# Score Predictor — Mundial 2026 ⚽

Predictor personal de marcadores para el Mundial 2026. En cada consulta
descarga los datos más recientes (solo fuentes gratuitas), recalcula el modelo
si hay resultados nuevos y muestra: marcador más probable, probabilidades 1X2,
confianza, comparación modelo-vs-mercado y qué cambió desde tu última consulta.

## Instalación

```bash
cd "Score predictor"
/opt/homebrew/bin/python3.12 -m venv .venv     # ya creado en esta máquina
.venv/bin/pip install -r requirements.txt
cp .env.example .env                            # y pega tus claves
```

### Claves (gratis, solo email, sin tarjeta)

1. **football-data.org** → <https://www.football-data.org/client/register>
   → pega el token en `.env` como `FOOTBALL_DATA_TOKEN` (respaldo de fixtures).
2. **The Odds API** → <https://the-odds-api.com/> → `ODDS_API_KEY`
   (cuotas multi-casa; sin esto la capa de mercado queda inactiva).
3. *(Opcional, experimental)* **BSD API** → <https://sports.bzzoiro.com/>
   → `BSD_TOKEN`.

El sistema funciona sin ninguna clave (modelo + fixtures + Elo + FIFA);
las claves activan la capa de mercado y la validación cruzada.

## Uso

```bash
.venv/bin/python -m predictor predecir "Mexico vs South Africa"
.venv/bin/python -m predictor predecir "España vs Brasil"     # nombres en español OK
.venv/bin/python -m predictor jornada 2026-06-11 --detalle
.venv/bin/python -m predictor proximos 10
.venv/bin/python -m predictor sync          # fuerza actualización de fuentes
.venv/bin/python -m predictor sync --cuotas # además snapshot de cuotas (1 crédito)
.venv/bin/python -m predictor estado        # frescura de datos y consumo de APIs
.venv/bin/python -m predictor precision     # Brier/RPS de predicciones resueltas
```

Consejo: ejecuta `sync --cuotas` una o dos veces al día durante el Mundial.
Cada snapshot se guarda con timestamp y construye tu propio histórico de
líneas de apertura/cierre, algo por lo que las APIs de pago cobran.

## El modelo en una frase

Dixon-Coles ponderado en el tiempo (ataque y defensa por selección, ajustado
sobre 32.000+ partidos internacionales desde 1990, con prior Elo para equipos
con poca muestra), ajustes de contexto (localía real, altitud, descanso) y
comparación contra las probabilidades del mercado de-vigueadas con el método
de Shin. Validado por backtest en WC2018/WC2022 (RPS ≈ 0.217/0.216, ~50-56%
de acierto 1X2, 9.4% de marcador exacto).

Detalles de arquitectura y decisiones: ver `CLAUDE.md`.
