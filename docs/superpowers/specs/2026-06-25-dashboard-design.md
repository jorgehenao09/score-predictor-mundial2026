# Dashboard "Score Predictor" — Diseño (2026-06-25)

## Propósito
Dashboard HTML estático local que reúne, en tres pestañas, (1) los análisis
previos de los partidos que vienen, (2) un informe de aciertos a la fecha, y
(3) una explicación del modelo base + su calibración por competición, pensado
para escalar a futuras competiciones sin reescribir nada.

**Para quién:** uso personal del autor (herramienta, no producto comercial).
**Filosofía:** coherente con el proyecto — simple, sin frameworks, sin servidor.

## Decisiones (cerradas en brainstorming)
- **Entrega:** un único HTML autocontenido (`data/panel.html`), CSS embebido +
  JS mínimo para cambiar de pestaña. Cero servidor, cero dependencias externas
  (las fuentes Google se enlazan; degradan a system-ui sin red).
- **Navegación:** 3 pestañas (Próximos · Aciertos · Modelo).
- **Pestaña Modelo:** tabla comparativa BASE vs competición (columnas
  escalables).
- **Fuera de alcance:** posición en la polla (no escalable), cualquier métrica
  atada a una polla concreta, hosting/servidor, interactividad más allá de tabs.

## Arquitectura
```
predictor/panel.py        orquestador: arma el HTML de las 3 pestañas
predictor/panel_data.py   (NUEVO) cálculo de datos, sin HTML:
                            - upcoming(con, fit, n)      -> predicciones próximas
                            - accuracy(con)              -> métricas + historial
                            - calibration(con)           -> snapshot de params
predictor/panel_style.py  (NUEVO) los design tokens como string CSS (:root)
```
- `panel.py` deja de ser "generador de tarjetas" y pasa a orquestador. Cada
  pestaña en su función de render (`_tab_proximos`, `_tab_aciertos`,
  `_tab_modelo`). Archivos pequeños y enfocados.
- Comando sin cambios: `python -m predictor panel [N]` (genera y abre).
- Los cálculos de aciertos reutilizan la lógica del comando `precision`.

## Sistema de diseño
Fuente de verdad: `design-system/score-predictor/MASTER.md`. Tema **claro**
(fondo gris claro, tarjetas blancas), estilo *data-dense dashboard*.

**Tokens de color (CSS `:root`):**
```
--bg #F8FAFC · --surface #FFFFFF · --surface-2 #F1F5F9 · --border #E2E8F0
--text #0F172A · --text-muted #475569 · --text-faint #94A3B8
--model #2563EB · --market #B45309 · --final #15803D · --value #CA8A04
--hit #16A34A · --miss #DC2626
--conf-alta #16A34A · --conf-media #D97706 · --conf-baja #DC2626 · --draw #64748B
Rellenos/barras (no texto): --model-fill #3B82F6 · --market-fill #F59E0B
```
**Tipografía:** `Fira Code` (números/marcadores/parámetros) + `Fira Sans`
(texto). **Espaciado** base 4px (4/8/12/16/24/32/48). **Radios** 6/10/14.
**Transiciones** 200ms. Respetar `prefers-reduced-motion`.

**Identidad de datos:** azul = nuestro modelo, ámbar = mercado. La divergencia
modelo↔mercado se lee por el contraste de color (= dónde hay valor).

**Componentes reutilizables:** `tab-bar`, `kpi-tile`, `match-card`, `bar-1x2`
(modelo/mercado/final), `data-table` (zebra + hover de fila), `compare-table`
(parámetros × competiciones), `badge` (confianza / ✓✗ / valor).

**Emojis:** 🎯 (golpredictor) y 🎲 (remontada) se mantienen como marcadores
semánticos del producto (coherencia con CLI y Telegram). El resto del chrome es
CSS/SVG, sin emojis decorativos.

## Pestaña 1 — Próximos
Una `match-card` por partido próximo (de `panel_data.upcoming`):
- Equipos · sede · día/hora (si hay kickoff).
- **🎯 golpredictor** (óptimo-EV) + "más probable" (modal) + alternativas.
- **🎲 remontada** (contrarian) cuando hay divergencia ≥5 pts; muestra costo-EV.
- `bar-1x2`: tres barras **modelo / mercado / final**; resalta la divergencia.
- Badge de **confianza** (alta/media/baja) y lista de **factores** (incluye la
  localía por sede ya corregida).

## Pestaña 2 — Aciertos
- Fila de `kpi-tile` (de `panel_data.accuracy`, solo partidos resueltos):
  **1X2 acertado %**, **marcador exacto %**, **puntos golpredictor**,
  **RPS** (calidad), **ROI ilustrativo** (apostar al veredicto — etiquetado
  como ilustrativo, no es consejo de apuesta).
- `data-table` historial: fecha · partido · veredicto · real · ✓/✗ · pts.
- Encuadre honesto: separar "quién gana" (fuerte) de "marcador exacto" (difícil).
- Sin posición de polla (decisión del usuario).

## Pestaña 3 — Modelo y calibración
- **Modelo base (universal):** explicación en lenguaje claro — Dixon-Coles
  ponderado, prior Elo, de-vig Shin del mercado, marcador óptimo-EV, mezcla
  modelo↔mercado autoaprendida. Esto NO cambia entre competiciones.
- **`compare-table`** parámetros × competiciones:

  | Parámetro | BASE | Mundial 2026 | (futuras→) |
  |---|---|---|---|
  | xi (decaimiento) | 0.0005 | live | |
  | rho (marcadores bajos) | — | live | |
  | ventaja local | — | +31% (por sede) | |
  | mezcla mercado | 0.50 | live (aprendido) | |
  | goal uplift | 1.00 | live | |
  | ¿auto-ajusta? | — | mezcla sí · resto vigilado | |

  Valores "live" desde `panel_data.calibration` (lee `fit`, `learning`,
  `tuned_params.json`). Cada fila con un microtexto "qué es".

## Escalar a nuevas competiciones (documentación clave)
El objetivo del usuario: ver la base y, por cada competición que indique, cómo
queda calibrada. Mecanismo de extensión:

1. **Datos de calibración por competición.** `panel_data.calibration(con)`
   devuelve hoy una columna (Mundial 2026) calculada del estado vivo. Para
   añadir una competición se agrega una entrada a un registro
   `COMPETITIONS = [{id, nombre, fit/learning/params}]` — una **columna nueva**
   en la `compare-table`, sin tocar el render.
2. **La fila BASE** son los defaults universales del modelo (constantes), no se
   recalcula.
3. **Localía ya es venue-driven** (`venues.host_side`) — sin hosts quemados, así
   que otras competiciones funcionan registrando sus sedes en `VENUES`.
4. **Sistema de diseño reutilizable:** tokens y componentes en
   `design-system/score-predictor/`. Una página nueva crea su override en
   `design-system/score-predictor/pages/`.

## Accesibilidad / calidad (checklist ui-ux-pro-max)
- Contraste texto ≥ 4.5:1 (paleta clara ya cumple con slate-900/600).
- `cursor: pointer` en tabs y filas clicables; foco visible (teclado).
- Transiciones 150–300ms; `prefers-reduced-motion` respetado.
- Responsive 375 / 768 / 1024 / 1440; sin scroll horizontal en móvil.
- Tabla con encabezados y semántica correcta.

## Verificación
Herramienta personal, sin tests formales (convención del proyecto). Validación:
generar `panel.html`, abrir en navegador, revisar las 3 pestañas con datos
reales, y comprobar el checklist de accesibilidad arriba.
