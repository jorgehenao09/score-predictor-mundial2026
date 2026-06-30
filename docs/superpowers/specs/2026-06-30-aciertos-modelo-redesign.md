# Rediseño de Aciertos y Modelo (línea v2) — Diseño (2026-06-30)

## Propósito
Llevar las pestañas **Aciertos** y **Modelo** a la misma línea visual rica del
v2 (cards/chips/tokens del `design-system/score-predictor/`), y añadir en
Aciertos el **feedback veredicto vs resultado** por partido (marcador predicho →
real, ✓/✗, puntos). No toca el modelo ni las otras pestañas.

## Decisiones cerradas en brainstorming
- **Feedback en Aciertos:** versión simple — por partido: `predicho → real`,
  chip ✓/✗, puntos. Sin desglose por componente (resultado/goles/dif).
- **Misma línea visual v2:** reutiliza tokens y componentes existentes
  (`kpi`, `chip`, `badge`, `data-table`); cambios de CSS mínimos.
- **Sin servidor, sin frameworks.** HTML estático generado por `panel.py`.

## Datos
`panel_data.accuracy` ya devuelve `history[]` con `{date, home, away, verdict,
real, ok, pts}`. **Se añade `pred`** = el marcador que reportamos (el `gp_score`
del marcador de cierre; fallback `top_score`). En `accuracy()`, dentro del loop,
`pick` ya se calcula (`gps if gps else ts`); guardar también
`"pred": gps if gps else ts` en cada item del historial.

## Pestaña Aciertos (rediseño)
1. **KPI tiles con acento de color** (reusa `.kpi`): borde/ізquierda o número
   con color — 1X2 `--model` (azul), Marcador exacto `--final` (verde), Puntos
   `--value` (oro), RPS neutro, ROI `--final`/`--miss` según signo. Una línea de
   contexto breve bajo cada número (la que ya existe se mantiene).
2. **Historial enriquecido** (reusa `data-table`): columnas
   `Fecha · Partido · Predicho → Real · ✓/✗ · Pts`. "Predicho → Real" muestra
   `{pred} → {real}` en mono; ✓/✗ como `badge hit`/`badge miss`; Pts en mono.
   Mantener la nota honesta "quién gana (fuerte) vs marcador exacto (difícil)".

## Pestaña Modelo (rediseño)
1. **Capas del modelo como chips** (reusa `.chip`): `Dixon-Coles · prior Elo ·
   Shin de-vig · óptimo-EV · mezcla auto`, sobre el bloque `.explain` con el
   texto explicativo actual.
2. **Tabla comparativa v2**: columna `BASE` diferenciada visualmente (fondo
   sutil `--surface-2`), y **microcopy "qué es"** por parámetro (una línea
   tenue bajo o junto a la etiqueta). Para esto, `PARAMS` en `panel.py` pasa de
   `(key, label)` a `(key, label, descripcion)`; el render usa la descripción.

## CSS nuevo (mínimo, en `panel_style.py`)
- `.kpi.accent-model .v{color:var(--model)}` etc. (variantes de color para los
  KPI), o una clase utilitaria por color.
- Ajuste opcional `td .arrow{color:var(--text-faint)}` para el "→".
- `compare-table` columna BASE con `background:var(--surface-2)`.
Todo deriva de tokens existentes; sin colores nuevos.

## Accesibilidad / calidad
- Contraste ≥4.5:1 (paleta clara ya cumple; los acentos de color van en números
  grandes o como borde, el texto base permanece oscuro).
- Chips ✓/✗ llevan símbolo + color (color no es único indicador).
- Tabla con encabezados; responsive (sin scroll horizontal en móvil — la tabla
  ya colapsa). `prefers-reduced-motion` respetado por el CSS base.

## Fuera de alcance
- Lógica del modelo, pestaña Próximos/modal, panel de patrones (el usuario eligió
  feedback simple), desglose por componente de puntos.

## Verificación
Sin tests formales. Generar `panel.html`, abrir, comprobar: Aciertos con KPIs de
color + historial `predicho → real` con ✓/✗ y puntos; Modelo con capas en chips
y tabla con BASE diferenciada + microcopy. Checklist de accesibilidad arriba.
