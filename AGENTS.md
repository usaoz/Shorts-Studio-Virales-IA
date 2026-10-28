# Guia rapida para IAs que editan Shorts Studio

Leer esto ANTES de tocar codigo. Objetivo: aplicar cambios en pocos pasos y sin romper la app.

## 1. Flujo estandar (4 pasos)
1. **Ubicar**: `python tools/mapa.py` (indice de funciones/widgets con linea) o
   `python tools/mapa.py buscar "texto visible en la UI"` / `python tools/mapa.py widget btn_auto_1clic`.
   NO leer `Editor_Shorts_Studio.py` entero (4600+ lineas): leer solo el rango (+-40 lineas).
2. **Editar**: con la herramienta de edicion directa. Si falla por espacios/CRLF, usar
   `python tools/reemplazar.py cambios.py` (ver docstring; aborta sin escribir si algo no coincide).
3. **Verificar**: `python tools/verificar.py` (compila todo + arranca la GUI oculta, ~4s). Debe imprimir 2 `[OK]`.
4. **Guardar**: `git add -A; git commit -m "ui: ..."; git push origin main`
   (PowerShell: separar con `;`, NUNCA `&&`).

## 2. Arquitectura
| Archivo | Contenido |
|---|---|
| `Editor_Shorts_Studio.py` | TODA la GUI. Una sola funcion gigante `iniciar_aplicacion_gui()` con funciones anidadas (closures). |
| `shorts_engine/gemini_ia.py` | Prompt + llamada a Gemini (`generar_guion_con_gemini_flash`, plan de modelos con fallback). |
| `shorts_engine/video_render.py` | Render 60 FPS (`editar_video_con_guion`, acepta `cancelar_check`). |
| `shorts_engine/youtube_manager.py` | Descarga yt-dlp, busqueda de virales, `calcular_horarios_inteligentes`. |
| `shorts_engine/config.py` | Constantes, rutas, dataclasses. |
| `subir_a_youtube.py` | OAuth multi-cuenta, pool de APIs, `subir_video` (acepta `callback_cancelar`). |
| `memoria_app.json` | Preferencias persistidas (`_cargar_memoria` / `_guardar_memoria`). |

Orden de la GUI (de arriba a abajo): header (cuota, cuenta, ajustes) -> `card_canales` / `card_link` /
`card_video_editado` (segun `modo_fuente_var`) -> `card_pub` (Plan de Subida) -> `row_botones_accion`
(80% `btn_auto_1clic` subir / 20% `btn_guardar_carpeta`) -> `row_pildoras_inferiores` (Ver cola / Ver metricas)
-> `progress_card` (barra + `btn_frenar_proceso`, solo durante el proceso).

## 3. Trampas conocidas (causaron errores antes)
- **Closures y orden**: una funcion anidada que usa un widget creado MAS ABAJO falla con
  `NameError: free variable ... not associated` si se ejecuta antes. Solucion: pre-declarar
  `mi_widget = None` cerca de `cache_avatares_ctk` (~linea 405) y chequear `if mi_widget is not None`.
  En `command=` usar `lambda: funcion()` si la funcion se define despues.
- **Variable de otro scope**: no copiar logica de `ejecutar_flujo_1_clic` (tiene `solo_guardar_override`)
  a `refrescar_plan_ui`; ahi no existe.
- Al agregar una opcion persistida: sumarla en `def_data`, en la lectura de `_cargar_memoria` y en `_guardar_memoria`.
- Texto del boton principal: SOLO en `refrescar_texto_boton_accion()`.
- Mostrar/ocultar tarjetas por modo: `actualizar_modo_vista()`. Plan de subida: `refrescar_plan_ui()`.
- Operaciones largas: correr en `threading.Thread`, y tocar la UI solo via `root.after(0, ...)`.

## 4. Estilo de UI (mantener unicidad)
- Colores: `BG_DARK`, `CARD_BG`, `CARD_BORDER`, `INPUT_BG`, `PURPLE_MAIN/PURPLE_HOVER`, `CYAN_ACCENT`, `GREEN_ACCENT`, `TEXT_MAIN/MUTED/DIM`.
- Botones secundarios: `fg_color=INPUT_BG`, `border_color="#2a3147"`, `hover_color="#1e2538"`, texto `#ffffff`.
- Fuente: `ctk.CTkFont(family="Segoe UI", size=12-15, weight="bold")`.
- Fechas visibles: `DD/MM` (o `DD/MM/AA HH:MM` en listas). Nunca "Hoy"/"Manana".
- Sin emojis en textos de la UI. Textos en espanol rioplatense neutro.
- Ventanas nuevas: `ctk.CTkToplevel(root)` + `aplicar_icono_ventana(win)` + `win.transient(root)`.

## 5. Modelos Gemini
Opciones del usuario en `MAPA_MODELOS_IA` (Editor_Shorts_Studio.py ~linea 284). El modelo elegido se
intenta PRIMERO en `plan_intentos` de `gemini_ia.py`; despues hay fallback automatico. Benchmark:
`python tools/bench_modelos.py gemini-3.8-flash gemini-3.6-flash` (usa `video_input.mp4`).
