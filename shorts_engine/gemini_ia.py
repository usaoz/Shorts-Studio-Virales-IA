# -*- coding: utf-8 -*-
import os
import sys
import cv2
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw
from .video_render import obtener_info_video
from .youtube_manager import ULTIMA_INFO_YTDLP
from .config import (
    BASE_DIR, TEMP_DIR, DEFAULT_GUION_TXT, PROMPT_IA_PATH, PROMPT_COMPACTO_PATH,
    WIN_NO_WINDOW, WIN_STARTUPINFO
)


GEMINI_KEY_FILE = BASE_DIR / "gemini_api_key.txt"


def obtener_gemini_api_key() -> str:
    env_k = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_k:
        return env_k
    if GEMINI_KEY_FILE.exists():
        try:
            return GEMINI_KEY_FILE.read_text(encoding="utf-8-sig").strip()
        except Exception:
            pass
    return ""


def guardar_gemini_api_key(api_key: str) -> None:
    GEMINI_KEY_FILE.write_text(api_key.strip(), encoding="utf-8")


def generar_mosaico_video(ruta_video: Path, cols: int = 4, rows: int = 2) -> Tuple[bytes, float]:
    """
    Extrae 8 fotogramas clave espaciados a lo largo de todo el video y los une en
    UN SOLO MOSAICO compacto (1080x960 JPEG) con el segundo exacto y las zonas (IZQ | CENTRO | DER)
    impresas en cada cuadro. Ahorra más del 80% de tokens visuales y permite análisis instantáneo.
    """
    import io
    dur_seg, w_src, h_src, fps_src = obtener_info_video(ruta_video)
    num_tiles = cols * rows
    tile_w, tile_h = 270, 480
    mosaico = Image.new("RGB", (cols * tile_w, rows * tile_h), (15, 17, 23))

    cap = None
    try:
        cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap = cv2.VideoCapture(str(ruta_video))
    except (Exception, SystemError, BaseException):
        cap = None

    for i in range(num_tiles):
        t_sec = min(max(0.15, (i + 0.5) * (dur_seg / num_tiles)), max(0.2, dur_seg - 0.15))
        img_tile = None

        if cap is not None and cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000.0)
                ok, frame_bgr = cap.read()
                if ok and frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    img_tile = Image.fromarray(frame_rgb).resize((tile_w, tile_h), Image.Resampling.LANCZOS)
            except (Exception, SystemError, BaseException):
                img_tile = None

        if img_tile is None:
            try:
                cmd_ff = [
                    "ffmpeg", "-v", "error",
                    "-ss", f"{max(0.0, t_sec):.3f}",
                    "-i", str(ruta_video),
                    "-frames:v", "1",
                    "-vf", f"scale={tile_w}:{tile_h}:force_original_aspect_ratio=increase:flags=lanczos,crop={tile_w}:{tile_h}",
                    "-f", "image2pipe",
                    "-vcodec", "png",
                    "-",
                ]
                proc_ff = subprocess.run(
                    cmd_ff,
                    capture_output=True,
                    check=False,
                    creationflags=WIN_NO_WINDOW,
                    startupinfo=WIN_STARTUPINFO,
                )
                if proc_ff.returncode == 0 and proc_ff.stdout:
                    img_tile = Image.open(io.BytesIO(proc_ff.stdout)).convert("RGB")
            except Exception:
                img_tile = None

        if img_tile is None:
            img_tile = Image.new("RGB", (tile_w, tile_h), (15, 17, 23))

        draw = ImageDraw.Draw(img_tile)
        draw.rectangle([0, 0, tile_w, 34], fill=(0, 0, 0))
        mm = int(t_sec) // 60
        ss = int(t_sec) % 60
        etiqueta = f"#{i + 1} | {mm:02d}:{ss:02d} ({t_sec:.1f}s)"
        draw.text((8, 6), etiqueta, fill=(250, 204, 21))

        draw.rectangle([0, tile_h - 22, tile_w, tile_h], fill=(0, 0, 0))
        draw.text((10, tile_h - 19), "IZQ        |        CENTRO        |        DER", fill=(180, 190, 210))

        c = i % cols
        r = i // cols
        mosaico.paste(img_tile, (c * tile_w, r * tile_h))

    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = TEMP_DIR / "mosaico_analisis.jpg"
    buf = io.BytesIO()
    mosaico.save(buf, format="JPEG", quality=82, optimize=True)
    jpeg_bytes = buf.getvalue()
    try:
        ruta_mosaico.write_bytes(jpeg_bytes)
    except Exception:
        pass

    print(f"[*] Mosaico de {num_tiles} cuadros generado ({len(jpeg_bytes) / 1024:.1f} KB) -> {ruta_mosaico.name}")
    return jpeg_bytes, dur_seg


PROMPT_COMPACTO_INTERNO = """Actúa como un Director de Edición y Guionista experto en retención viral para YouTube Shorts (estilo MrBeast / Reacciones / Bromas / Gaming / Curiosidades).

Tu tarea es **ANALIZAR el mosaico del video** y redactar un guion altamente dinámico basado exactamente en lo que ocurre en el video, con gancho explosivo en los primeros segundos y ritmo constante, narrando lo que sucede DE CORRIDO SIN SILENCIOS hasta el último segundo.

PROHIBIDO INCLUIR LLAMADAS A LA ACCIÓN (CTA): la voz NUNCA debe pedir "like", "me gusta", "suscríbete", "comenta", "comparte", "sígueme", "activa la campanita" ni nada parecido. El último bloque también debe ser pura narración de lo que ocurre en pantalla (el desenlace o la reacción final), sin despedidas ni pedidos al espectador.
PROHIBIDO PONER `[SIGUE_SONIDO_ORIGINAL]` O DEJAR BLOQUES SIN NARRACIÓN: La voz en español debe hablar SIEMPRE en TODOS los bloques de principio a fin (para tapar cualquier idioma extranjero o silencio del video original).

Debes entregarme el resultado EXCLUSIVAMENTE en el formato exacto de bloque de texto que se muestra al final, sin explicaciones adicionales ni bloques ```.

================================================================================
REGLA CRÍTICA DE TIEMPOS (1x) Y LÍMITE DE PALABRAS POR BLOQUE
================================================================================
El editor reproduce el video de fondo a su **velocidad real original (1x)** y el Short final dura **EXACTAMENTE lo mismo que el video original**.

1. **Tiempos exactos (`TIEMPO`)**:
   - Los bloques `MM:SS - MM:SS` deben empezar en `00:00` y terminar exactamente en el **segundo final real del video**, divididos en tramos de 4 o 5 segundos.

2. **Cantidad EXACTA de palabras por bloque (`TEXTO`)**:
   - La voz IA habla a un ritmo ágil de **3.7 palabras por segundo** y debe sonar **de corrido, sin silencios**: cada bloque tiene que quedar lleno de narración expresiva de principio a fin.
   - Cumple **ESTRICTAMENTE** este rango de palabras en cada línea según la duración de ese bloque:
     * Bloque de **3 segundos** -> Entre **11 y 12 palabras** (máximo 13 palabras).
     * Bloque de **4 segundos** -> Entre **14 y 16 palabras** (máximo 16 palabras).
     * Bloque de **5 segundos** -> Entre **18 y 20 palabras** (**MÁXIMO ESTRICTO: 20 palabras**).
     * Bloque de **6 segundos** -> Entre **21 y 23 palabras** (máximo 24 palabras).
   - **PROHIBIDO escribir más de 20 palabras en un bloque de 5 segundos**, y tampoco menos de 17. Redacta **2 oraciones fluidas, enérgicas y muy expresivas** (con signos `¡!` o `¿?`) por línea que cuenten exactamente lo que está pasando en pantalla en ese instante.

================================================================================
REGLAS DE LAS 7 COLUMNAS DEL GUION (SEPARADAS POR '|'):
================================================================================
Formato obligatorio de cada línea debajo de `[GUION]`:
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO

1. TIEMPO: `MM:SS - MM:SS` cubriendo desde `00:00` hasta el segundo final exacto del video.
2. EFECTO (Elige UNO por línea):
   - `zoom_impacto` (golpe de zoom rápido + vibración, ideal para el gancho inicial)
   - `zoom_in` (acercamiento progresivo hacia el objetivo)
   - `zoom_out` (alejamiento suave de cámara)
   - `flash` (destello luminoso de cámara)
   - `temblor` (sacudida intensa de pantalla + impacto)
   - `alerta_roja` (viñeta roja pulsante de peligro, trampa o error)
   - `brillo_epico` (resplandor vibrante para victorias o desenlaces épicos)
   - `blanco_negro` (desaturación dramática para fails)
   - `ninguno`
3. SFX (Elige UNO o combina dos con `+`, ej. `whoosh+xp_Error`):
   - `crowd_shocked`, `whoosh`, `riser_suction`, `ding`, `good_idea`, `cash_ting`, `punch`, `boxing_bell`, `camera_flash`, `camera_shooter`, `cartoon_laugh`, `kids_yeyy`, `party_horn`, `awww`, `error`, `xp_Error`, `fart`, `click`, `pop`, `ninguno`.
4. EMOJI (Elige UNO con posición opcional `:derecha` o `:izquierda`):
   - `sorprendido`, `risa`, `fiesta`, `diablo`, `enojo`, `lloro`, `sueno`, o `ninguno`.
5. FLECHA (`flecha.png` con seguimiento por visión artificial):
   - Apunta y persigue automáticamente al objeto, persona o acción clave en esa zona del video.
   - Opciones: `auto` (para que la visión artificial detecte y siga el sujeto/objeto principal en movimiento), `izquierda`, `derecha`, `centro`, `arriba`, `abajo`, o bien la coordenada porcentual exacta `X,Y` (ej: `28,45` si el sujeto está a la izquierda, `72,50` a la derecha), o `ninguna`.
   - **FRECUENCIA MODERADA**: usa la flecha solo en **1 o 2 bloques clave del guion como máximo**, dejando el resto en `ninguna`. No pongas flechas en bloques seguidos.
   - **NUNCA uses flecha en el último bloque**: El editor añade automáticamente al final un outro freeze-frame de 0.7 segundos con la flecha animada apuntando al botón de Like y sonido de campana.
6. CIRCULO (`circulo_rojo.png`):
   - Rodea el objeto o revelación más impactante del video: usa `auto`, `izquierda`, `derecha`, `centro` (opcional `:grande`), coordenada `X,Y`, o `ninguno`.
   - **LÍMITE ESTRICTO**: usa el círculo en **1 bloque COMO MÁXIMO** en todo el guion. En todos los demás escribe `ninguno`.
7. TEXTO (Narración de Voz IA continua + Subtítulos Luminosos):
   - Entre **18 y 20 palabras por cada bloque de 5 segundos** con máxima emoción (`¡!`). Narra siempre lo que pasa en el video sin pedir likes ni suscripciones.

================================================================================
PLANTILLA DE ENTREGA OBLIGATORIA:
================================================================================
TITULO_SUPERIOR: [Nombre corto de 4-5 palabras para el archivo MP4, ej: Abuela Venganza Epica Troleo]
TITULO_YOUTUBE: [Título viral llamativo y #shorts, ej: ¡La mejor venganza de la abuela! #shorts]
DESCRIPCION_YOUTUBE: [Descripción atrapante de 2 oraciones + pregunta a la audiencia + hashtags #shorts #humor #fail #viral]
ESTADO_PUBLICACION: privado
SCHEDULE: auto
PARA_NINOS: no
MODO_ENCUADRE: full
TONO_VIDEO: fondo
ARCHIVO_SALIDA: auto

[GUION]
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
00:00 - 00:05 | zoom_impacto | crowd_shocked | sorprendido:derecha | izquierda | ninguno | ¡Mira cómo esta nieta traviesa engaña a su abuela escondiendo la pelota de tenis! ¡La pobre no entiende absolutamente nada!
00:05 - 00:10 | zoom_in | whoosh+xp_Error | enojo:izquierda | ninguna | ninguno | ¡La broma sigue cuando hace desaparecer otro objeto frente a su cara! ¡Su abuela busca confundida por toda la mesa!
00:10 - 00:15 | alerta_roja | riser_suction | diablo:derecha | ninguna | izquierda:grande | ¡Pero cuidado porque la abuela ya tenía preparada una trampa secreta! ¡Prepárate para ver la venganza más épica de todas!
00:15 - 00:20 | temblor | punch+cartoon_laugh | risa:izquierda | derecha | ninguno | ¡Toma esto por tramposa! ¡La nieta termina con toda la cara completamente llena de harina blanca en un segundo!
00:20 - 00:25 | brillo_epico | cash_ting+party_horn | fiesta:derecha | ninguna | ninguno | ¡La abuela celebra su victoria mientras la nieta no puede creer lo que acaba de pasar! ¡Una venganza perfecta!"""


def generar_video_compacto_ia(ruta_video: Path) -> Tuple[Optional[bytes], float]:
    """
    Comprime el video original a 360p (4 FPS, ~350 KB) para enviárselo COMPLETO
    en movimiento + con audio a la IA (Argon 4 / Gemini 3.8 / Gemini 3.5), de modo
    que vea la acción real segundo a segundo y no adivine por fotos sueltas.
    """
    dur_seg, _, _, _ = obtener_info_video(ruta_video)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_low = TEMP_DIR / "video_analisis_ia.mp4"
    if ruta_low.exists():
        try:
            ruta_low.unlink()
        except OSError:
            pass
    res = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(ruta_video),
            "-vf", "scale=-2:360,fps=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
            "-c:a", "aac", "-b:a", "48k",
            str(ruta_low),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=WIN_NO_WINDOW,
        startupinfo=WIN_STARTUPINFO,
    )
    if res.returncode == 0 and ruta_low.exists() and 1000 < ruta_low.stat().st_size < 6_000_000:
        return ruta_low.read_bytes(), dur_seg
    return None, dur_seg


def generar_guion_con_gemini_flash(
    ruta_video: Path,
    api_key: str,
    schedule_str: str = "auto",
    modo_privacidad: str = "privado",
    contexto_titulo_orig: str = "",
    modelo_preferido: str = "gemini-3.5-flash-lite",
    progreso_cb: Optional[object] = None,
) -> str:
    """
    Sistema de Triple Pasada (Ensemble Refinement) con IA:
    1. Pasada 1 (Gancho y Ritmo Viral): Explora el hook más adictivo e intrigante para retención.
    2. Pasada 2 (Precisión Visual y Objetos): Analiza al detalle las acciones reales sin inventar nada.
    3. Pasada 3 (Fusión Maestra y Perfeccionamiento): Combina lo mejor de ambas pasadas, colocando
       las flechas, círculos, emojis y efectos sonoros (SFX) en los momentos de mayor clímax.
    """
    import concurrent.futures
    from google import genai
    from google.genai import types

    key_limpia = api_key.strip()
    if not key_limpia:
        raise ValueError("No ingresaste tu GEMINI_API_KEY gratuita de Google AI Studio.")

    jpeg_bytes, dur_seg = generar_mosaico_video(ruta_video)
    video_bytes, _ = generar_video_compacto_ia(ruta_video)
    dur_redondeada = max(5, int(round(dur_seg)))

    # Recuperar siempre el título y descripción originales reales (de memoria yt-dlp o archivo .info.json en disco)
    if not ULTIMA_INFO_YTDLP.get("titulo") or not ULTIMA_INFO_YTDLP.get("descripcion"):
        candidatos_info = [
            ruta_video.with_suffix(".info.json"),
            BASE_DIR / "video_input.info.json",
        ]
        for c_path in candidatos_info:
            if c_path.exists():
                try:
                    d_json = json.loads(c_path.read_text(encoding="utf-8", errors="replace"))
                    if not ULTIMA_INFO_YTDLP.get("titulo"):
                        ULTIMA_INFO_YTDLP["titulo"] = str(d_json.get("title") or "").strip()
                    if not ULTIMA_INFO_YTDLP.get("descripcion"):
                        ULTIMA_INFO_YTDLP["descripcion"] = str(d_json.get("description") or "").strip()[:800]
                    break
                except Exception:
                    pass

    tit_ytdlp = (ULTIMA_INFO_YTDLP.get("titulo") or "").strip()
    desc_ytdlp = (ULTIMA_INFO_YTDLP.get("descripcion") or "").strip()

    tit_ctx = tit_ytdlp
    if contexto_titulo_orig and not contexto_titulo_orig.lower().startswith("video link"):
        tit_ctx = contexto_titulo_orig.strip() or tit_ytdlp

    desc_ctx = desc_ytdlp

    bloque_contexto_real = ""
    if tit_ctx or desc_ctx:
        bloque_contexto_real = (
            f"\nCONTEXTO REAL DEL VIDEO ORIGINAL (TÍTULO Y DESCRIPCIÓN OFICIALES):\n"
            + (f"- TÍTULO ORIGINAL: {tit_ctx}\n" if tit_ctx else "")
            + (f"- DESCRIPCIÓN ORIGINAL: {desc_ctx}\n" if desc_ctx else "")
            + "- DIRECTIVA DE FIDELIDAD TOTAL: Usa este título y descripción para conocer exactamente qué sucede, quiénes son y qué objetos o acciones reales aparecen. No inventes elementos contrarios a la descripción ni confundas juguetes/objetos.\n"
        )

    instruccion_extra_base = (
        f"{bloque_contexto_real}\n"
        f"DATOS EXACTOS DEL VIDEO ANALIZADO:\n"
        f"- Duración total exacta del video: {dur_redondeada} segundos (de 00:00 a 00:{dur_redondeada:02d}).\n"
        f"- Divide los bloques de 00:00 hasta 00:{dur_redondeada:02d} en tramos de 5 segundos (18 a 20 palabras por bloque, hablando de corrido sin silencios de principio a fin).\n"
        f"- En ESTADO_PUBLICACION escribe: {modo_privacidad}\n"
        f"- En SCHEDULE escribe: {schedule_str.strip() if schedule_str.strip() else 'no'}\n"
        f"- En PARA_NINOS escribe: no\n"
        f"- En TONO_VIDEO escribe 'triste' si el video es triste o dramático, 'inspiracional' si es emotivo, heroico o de superación, o 'fondo' para humor, curiosidad, acción y entretenimiento general.\n"
        f"- Recuerda usar FLECHA como máximo en 2 bloques clave de todo el guion y CIRCULO como máximo en 1 bloque.\n"
    )

    def _consultar_ia_robusta(texto_prompt: str, timeout_max: float = 40.0) -> str:
        partes_v: List[object] = []
        if video_bytes:
            partes_v.append(types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"))
        partes_v.append(types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"))
        partes_v.append(texto_prompt)

        partes_m: List[object] = [
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            texto_prompt,
        ]

        candidatos_base: List[Tuple[str, List[object], float]] = [
            (modelo_preferido, partes_v, timeout_max),
            ("gemini-3.5-flash-lite", partes_v, timeout_max),
            ("gemini-flash-lite-latest", partes_v, timeout_max),
            ("gemini-3.6-flash", partes_v, timeout_max),
            ("gemini-3.8-flash", partes_v, timeout_max),
            ("gemini-3.5-flash-lite", partes_m, min(30.0, timeout_max)),
            ("gemini-flash-lite-latest", partes_m, min(30.0, timeout_max)),
            ("gemini-3.6-flash", partes_m, min(30.0, timeout_max)),
        ]
        plan_intentos: List[Tuple[str, List[object], float]] = []
        vistos: Set[Tuple[str, int]] = set()
        for m, c, t in candidatos_base:
            k_id = (m, len(c))
            if k_id not in vistos:
                vistos.add(k_id)
                plan_intentos.append((m, c, t))

        ultimo_err: Optional[Exception] = None
        for mod, cont_env, t_lim in plan_intentos:
            def _call(m=mod, cnt=cont_env, tl=t_lim):
                cli = genai.Client(
                    api_key=key_limpia,
                    http_options=types.HttpOptions(
                        timeout=max(20000, int(tl * 1000)),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
                r = cli.models.generate_content(model=m, contents=cnt)
                return (r.text or "").strip()

            ex_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            fut = ex_pool.submit(_call)
            try:
                res_txt = fut.result(timeout=t_lim + 1.5)
                ex_pool.shutdown(wait=False, cancel_futures=True)
                if res_txt and len(res_txt) > 80:
                    return res_txt
            except Exception as e:
                ultimo_err = e
                ex_pool.shutdown(wait=False, cancel_futures=True)
                err_msg_corto = str(e) or repr(e)
                if "429" in err_msg_corto or "RESOURCE_EXHAUSTED" in err_msg_corto:
                    print(f"[!] {mod} sin cuota disponible en Free Tier, pasando al siguiente...")
                else:
                    print(f"[!] {mod} con demora ({err_msg_corto[:70]}), pasando al siguiente...")

        if ultimo_err:
            det = str(ultimo_err) if str(ultimo_err).strip() else f"Tiempo límite agotado ({repr(ultimo_err)})"
            raise RuntimeError(f"No se pudo obtener respuesta de Gemini: {det}")
        return ""

    def _limpiar_bloque(texto_raw: str) -> str:
        t = texto_raw.strip()
        if t.startswith("```"):
            lineas = t.splitlines()
            if lineas and lineas[0].startswith("```"):
                lineas = lineas[1:]
            if lineas and lineas[-1].strip().startswith("```"):
                lineas = lineas[:-1]
            t = "\n".join(lineas).strip()
        return t

    # --- PASADA 1: Enfoque en Gancho Viral y Ritmo ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.15, "IA Pasada 1/3: Creando gancho viral y ritmo...")
        except Exception:
            pass
    print("[*] IA Pasada 1/3: Creando guión con enfoque en Gancho Viral y Ritmo...")
    prompt_p1 = (
        PROMPT_COMPACTO_INTERNO + instruccion_extra_base +
        "\n[DIRECTIVA DE ENFOQUE 1 - RITMO Y GANCHO VIRAL]:\n"
        "Concéntrate en generar un hook inicial explosivo en los primeros 3 segundos con preguntas o misterio, "
        "con ritmo dinámico continuo que atrape la atención sin soltar al espectador.\n"
        "Entrega ÚNICAMENTE el bloque de guion:"
    )
    guion_1_raw = _consultar_ia_robusta(prompt_p1, timeout_max=40.0)
    guion_1 = _limpiar_bloque(guion_1_raw)

    # --- PASADA 2: Enfoque en Observación Visual y Precisión de Hechos ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.50, "IA Pasada 2/3: Analizando precisión visual de objetos y acciones...")
        except Exception:
            pass
    print("[*] IA Pasada 2/3: Creando guión con enfoque en Precisión Visual y Hechos...")
    prompt_p2 = (
        PROMPT_COMPACTO_INTERNO + instruccion_extra_base +
        "\n[DIRECTIVA DE ENFOQUE 2 - PRECISIÓN VISUAL Y HECHOS]:\n"
        "Concéntrate en observar con lupa cada segundo del video, qué objetos reales se tocan, qué hace la persona "
        "con sus manos y qué sucede realmente sin confundir ningún elemento ni inventar cosas.\n"
        "Entrega ÚNICAMENTE el bloque de guion:"
    )
    guion_2_raw = _consultar_ia_robusta(prompt_p2, timeout_max=40.0)
    guion_2 = _limpiar_bloque(guion_2_raw)

    # --- PASADA 3: Fusión Crítica y Perfeccionamiento Maestro ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.80, "IA Pasada 3/3: Fusionando y perfeccionando el guión maestro...")
        except Exception:
            pass
    print("[*] IA Pasada 3/3: Fusionando lo mejor de ambos guiones en la versión maestra definitiva...")
    prompt_p3 = (
        f"ACTÚA COMO EL DIRECTOR Y EDITOR JEFE DE CONTENIDO VIRAL DE YOUTUBE SHORTS.\n"
        f"Tienes dos borradores generados para el mismo video:\n\n"
        f"--- [BORRADOR A - GANCHO VIRAL Y RITMO] ---\n{guion_1}\n\n"
        f"--- [BORRADOR B - PRECISIÓN VISUAL Y DETALLES REALES] ---\n{guion_2}\n\n"
        f"CONTEXTO ORIGINAL DEL VIDEO:\n{bloque_contexto_real}\n\n"
        f"TU MISIÓN DE FUSIÓN CRÍTICA:\n"
        f"1. Combina el gancho más atrapante y adictivo del Borrador A con la exactitud de objetos y giros reales del Borrador B.\n"
        f"2. Asegúrate de que no haya ninguna confusión sobre los objetos ni acciones.\n"
        f"3. Coloca las FLECHAS (máximo 2 bloques clave: 'auto', 'izquierda', 'derecha', 'centro' o coordenada X,Y apuntando al objeto o sujeto principal en movimiento) y CÍRCULOS (máximo 1 bloque clave: 'auto', 'izquierda', 'derecha', 'centro:grande'), EMOJIS y SFX en los momentos de mayor impacto, sorpresa o revelación del video.\n"
        f"4. Mantén exactamente los tiempos (de 00:00 a 00:{dur_redondeada:02d}), cada bloque de 5 segundos, y el encabezado de metadatos exacto.\n"
        f"Entrega ÚNICAMENTE el bloque de guion final estructurado:\n\n"
        f"TITULO_SUPERIOR: ...\nTITULO_YOUTUBE: ...\nDESCRIPCION_YOUTUBE: ...\n"
        f"ESTADO_PUBLICACION: {modo_privacidad}\nSCHEDULE: {schedule_str.strip() if schedule_str.strip() else 'no'}\n"
        f"PARA_NINOS: no\nMODO_ENCUADRE: full\nTONO_VIDEO: fondo\nARCHIVO_SALIDA: auto\n\n"
        f"[GUION]\nTIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO\n"
    )

    try:
        guion_final_raw = _consultar_ia_robusta(prompt_p3, timeout_max=35.0)
        guion_final = _limpiar_bloque(guion_final_raw)
        if guion_final and "[GUION]" in guion_final and len(guion_final) > 150:
            texto_respuesta = guion_final
            print("[+] ¡Pasada 3 completada con éxito! Guión maestro sintetizado.")
        else:
            texto_respuesta = guion_1 if "[GUION]" in guion_1 else guion_2
    except Exception as err_p3:
        print(f"[!] Fusión de pasada 3 tuvo un problema ({err_p3}), usando el mejor borrador disponible.")
        texto_respuesta = guion_1 if "[GUION]" in guion_1 else guion_2

    if not texto_respuesta or "[GUION]" not in texto_respuesta:
        texto_respuesta = guion_1 or guion_2

    DEFAULT_GUION_TXT.write_text(texto_respuesta + "\n", encoding="utf-8")
    print(f"[+] ¡Guión final perfeccionado y guardado en {DEFAULT_GUION_TXT.name}!")
    if callable(progreso_cb):
        try:
            progreso_cb(1.0, "Guión viral de triple pasada completado.")
        except Exception:
            pass
    return texto_respuesta
