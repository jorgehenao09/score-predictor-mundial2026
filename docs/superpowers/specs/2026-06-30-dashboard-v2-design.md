# Dashboard v2 — cards ricas + modal de detalle (2026-06-30)

## Propósito
Mejorar la pestaña **Próximos** del dashboard: cards menos planas (#3) y un
**modal de detalle al hacer clic** (#2) que explique cómo se llegó al marcador
—matriz de goles, peso de cada factor, mezcla modelo↔mercado—. Reutiliza el
sistema de diseño existente (tema claro, `design-system/score-predictor/`).

## Decisiones cerradas en brainstorming
- **#1 (ponderar casas por acierto): DESCARTADO.** Feasibility medida con datos
  reales (24 casas, 66 partidos): el consenso de todas da RPS 0.1426; ponderar
  hacia el TOP-8 (in-sample, optimista) da 0.1422 (~0 out-of-sample). La "mejor
  casa" (coolbet 0.1382) es suerte de superviviente que no persiste. No vale la
  complejidad; el peso modelo↔mercado ya se autoajusta.
- **#2 detalle:** factores con peso + matriz de goles (heatmap) + barras 1X2,
  en **modal superpuesto** (clic en card → overlay; cierra con ✕ o Esc).
- **#3 cards:** barra 1X2 **apilada** (3 vías), picks 🎯/🎲 como chips, chip de
  confianza con color, indicador de valor/divergencia, hover con elevación,
  card clicable.
- **Sin servidor, sin frameworks.** Todo embebido; el modal se arma en el HTML
  y se muestra con JS mínimo (mismo patrón que las tabs).

## Arquitectura / datos
El detalle necesita la **descomposición de las λ**, que `predict_match` calcula
pero no devuelve. Se añade un `breakdown` al dict de la predicción.

**`predict.predict_match` → nueva clave `breakdown`:**
```python
breakdown = {
  "lh": float, "la": float,            # λ finales (modelo) local/visita
  "terms": [                            # contribuciones aditivas al log-λ
     {"label": "Ataque {home}", "value": +0.55},
     {"label": "Defensa {away}", "value": +0.31},
     {"label": "Ventaja local (sede)", "value": +0.27},  # 0 si neutral
     {"label": "Uplift de goles", "value": +0.05},
     {"label": "Descanso/altitud/clima", "value": ...},  # 0 si no aplica
     ...
  ],
  "matrix": [[p,...],...],              # 6x6 (marcadores 0-5) de M_modelo·mezcla
  "model_probs": (ph,pd,pa),
  "market_probs": (ph,pd,pa) | None,
  "final_probs": (ph,pd,pa),
  "blend_w": float,                     # peso mercado (0..1)
  "gp_cell": (i,j), "modal_cell": (i,j) # para resaltar en el heatmap
}
```
Los términos salen de la cuenta ya existente: `log λh = mu + ah − da + ha_home
+ log(uplift) + log(ctx)`. Se construye en el punto donde se calculan `lh/la`.
El panel solo lee `breakdown`; cero dependencias nuevas.

`panel.py` embebe, por cada partido próximo, un `<div class="modal" id="d-N">`
oculto con el detalle; la card lleva `data-detail="d-N"`. JS: clic en card →
muestra el modal; ✕/Esc/clic-fuera → oculta.

## Componentes nuevos (design tokens existentes)
- `card` (rediseño): barra 1X2 **stacked** (`bar-stacked` con 3 segmentos
  local/empate/visita usando `--model-fill`/`--draw`/`--market-fill` o colores
  por resultado), chips (`chip` para 🎯/🎲/valor), `badge` de confianza con
  color, hover `transform: translateY(-2px)` + sombra, `cursor:pointer`.
- `modal` + `modal-backdrop`: overlay centrado, scroll interno, foco atrapado
  básico, cierre accesible (botón con `aria-label`, Esc).
- `heatmap`: grid CSS 6×6; opacidad de celda ∝ probabilidad; celda óptimo-EV con
  borde `--final`, modal con borde `--model`. Encabezados 0–5 local/visita.
- `factor-bars`: barras divergentes (positivo/negativo desde un centro) con la
  etiqueta y el valor de cada término; color `--model` (+) / `--miss` (−).

## Pantalla 1 — Card rediseñada (Próximos)
Resumen rico y clicable: equipos, sede/hora, **barra 1X2 apilada con las 3
etiquetas**, chips 🎯 (golpredictor) y 🎲 (remontada, si hay), chip ⚡ de valor
cuando el modelo discrepa del mercado ≥5 pts, λ esperadas, % de mezcla, y
"ver detalle →". Confianza como chip de color (alta/media/baja).

## Pantalla 2 — Modal de detalle
Encabezado "{home} vs {away} · cómo se llegó al {gp_score}". Contenido:
1. **Barras 1X2 grandes** (modelo / mercado / final).
2. **Matriz de goles (heatmap 6×6)** con óptimo-EV y modal resaltados + leyenda.
3. **Peso de cada factor** (barras divergentes desde `breakdown.terms`).
4. **Mezcla** modelo↔mercado: "{w:.0%} mercado / {1−w:.0%} modelo" + las tres
   1X2 (puro/mercado/final).

## Accesibilidad / calidad (checklist ui-ux-pro-max)
- Contraste ≥4.5:1 (paleta clara ya cumple). `cursor:pointer` en cards.
- Modal: `role="dialog"`, `aria-modal`, cierre con Esc y botón con `aria-label`,
  foco al abrir. Heatmap con `title`/`aria-label` por celda (marcador + %).
- Hover/transiciones 150–300ms; `prefers-reduced-motion` respetado.
- Responsive 375/768/1024/1440; el modal se adapta (ancho máx, scroll).
- Color nunca único indicador (chips llevan texto).

## Fuera de alcance
- #1 (ponderación por casa).
- Crests/banderas por red (se mantiene texto; emojis de bandera opcionales si
  triviales).
- Cambios a las pestañas Aciertos y Modelo.

## Verificación
Herramienta personal, sin tests formales. Validación: generar `panel.html`,
abrir, comprobar que las cards se ven ricas, que el clic abre el modal con
matriz + factores correctos, y el checklist de accesibilidad arriba.
