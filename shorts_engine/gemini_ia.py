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
5. FLECHA (`flecha.png` con seguimiento inteligente por visión artificial):
   - Apunta a la acción, sujeto o reacción CLAVE de ese momento del video (ej. la persona que hace la broma, el gesto gracioso, el objeto que se mueve).
   - DIRECTIVA DE LOCALIZACIÓN REAL: Observa en qué parte de la pantalla (de 0 a 100) ocurre la acción en ese segundo y escribe la coordenada porcentual `X,Y` (ej: `68,55` para algo a la derecha, `30,40` a la izquierda, `50,65` abajo) o la zona (`derecha`, `izquierda`, `abajo`, `arriba`, `auto`).
   - Usa la flecha solo en 1 o 2 momentos de mayor impacto del video. En los demás escribe `ninguna`. NUNCA en el último bloque.
6. CIRCULO (`circulo_rojo.png` con Grounding Espacial de Alta Precisión):
   - REGLAS DE APARICIÓN (CERO HUMO): Solo activa un círculo rojo si en ese bloque hay un OBJETO FÍSICO CONCRETO, PEQUEÑO/MEDIANO Y RELEVANTE que el espectador debe mirar (ej: lo que sostiene la mano, una herramienta, comida, juguete, dinero, detalle oculto, suciedad o falla en piso/mesa).
   - ESTRICTAMENTE PROHIBIDO:
     * NUNCA enmarques el pecho, ropa, remera, torso o fondo vacío.
     * NUNCA pongas círculos sobre personas enteras ni zonas genéricas ('auto', 'centro', 'derecha').
     * Si no hay un objeto físico clave puntual, el campo CIRCULO DEBE SER exactamente `ninguno`. (Máximo 1 círculo en todo el video).
   - REGLA DE PUNTO DE CONTACTO (NO ENMARCAR HERRAMIENTAS NI BRAZOS):
     * Si una mano, cuchillo, cúter, pinza o herramienta está tocando o cortando un objeto (ej. un pastel, una fruta, una pieza), el `box:[ymin,xmin,ymax,xmax]` debe enmarcar EXCLUSIVAMENTE EL OBJETO QUE RECIBE LA ACCIÓN (el pastel/pieza), NUNCA el mango de la herramienta ni la mano/brazo que entra en escena.
     * Prohibido redondear coordenadas a múltiplos de 50 (como [100,50,450,400]). Calcula los bordes ajustados al objeto real.
   - COORDENADAS NATIVAS (ESCALA 0 A 1000):
     Localiza la caja delimitadora (bounding box) exacta del objeto en el segundo clave (`t_ancla`) donde mejor se aprecia:
     Formato obligatorio: `box:[ymin,xmin,ymax,xmax]@t_ancla:etiqueta`
     Ejemplos reales: `box:[450,560,590,720]@02.4:herramienta`, `box:[510,320,680,540]@03.1:taza_cafe`, `65,58:chico`, o `ninguno`.
7. TEXTO (Narración de Voz IA Rápida y Enérgica estilo Shorts):
   - Entre **15 y 17 palabras por cada bloque de 5 segundos** (~3.1 a 3.3 palabras/segundo) con máxima emoción (`¡!`). Esta cadencia es rápida, enérgica y atrapante (estilo viral de YouTube Shorts), manteniendo una dicción fluida y continua sin silencios muertos. Narra siempre lo que pasa en el video sin pedir likes ni suscripciones.

================================================================================
PLANTILLA DE ENTREGA OBLIGATORIA:
================================================================================
TITULO_SUPERIOR: [Nombre corto de 4-5 palabras para el archivo MP4, ej: Abuela Venganza Epica Troleo]
TITULO_YOUTUBE: [Título viral llamativo con 1 o 2 emojis llamativos obligatorios y #shorts, ej: ¡La mejor venganza de la abuela! 🤣💥 #shorts]
DESCRIPCION_YOUTUBE: [Descripción atrapante de 2 oraciones + pregunta a la audiencia + 4 o 5 hashtags hiper-específicos del nicho real del video (ej: si es de perros #shorts #perros #mascotas #viral; si es de autos #shorts #autos #carreras #viral; etc.)]
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
00:10 - 00:15 | alerta_roja | riser_suction | diablo:derecha | ninguna | box:[490,280,680,480]@12.4:trampa_secreta | ¡Pero cuidado porque la abuela ya tenía preparada una trampa secreta! ¡Prepárate para ver la venganza más épica de todas!
00:15 - 00:20 | temblor | punch+cartoon_laugh | risa:izquierda | derecha | ninguno | ¡Toma esto por tramposa! ¡La nieta termina con toda la cara completamente llena de harina blanca en un segundo!
00:20 - 00:25 | brillo_epico | cash_ting+party_horn | fiesta:derecha | ninguna | ninguno | ¡La abuela celebra su victoria mientras la nieta no puede creer lo que acaba de pasar! ¡Una venganza perfecta!"""


def generar_video_compacto_ia(ruta_video: Path) -> Tuple[Optional[bytes], float]:
    """
    Comprime el video original a 360p (4 FPS, ~350 KB) para enviárselo COMPLETO
    en movimiento + con audio a la IA (Argon 4 / Gemini 3.8 / Gemini 3.5), de modo
    que vea la acción real segundo a segundo y no adivine por fotos sueltas.
    """
    dur_seg, w_v, h_v, _ = obtener_info_video(ruta_video)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_low = TEMP_DIR / "video_analisis_ia.mp4"
    if ruta_low.exists():
        try:
            ruta_low.unlink()
        except OSError:
            pass
    # Mantener aspecto nativo 9:16 vertical (360x640) o 16:9 horizontal (640x360) para eliminar distorsión de aspecto
    filtro_escala = "scale=360:640:flags=fast_bilinear,fps=4" if (h_v >= w_v) else "scale=640:360:flags=fast_bilinear,fps=4"
    res = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(ruta_video),
            "-vf", filtro_escala,
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
    modelo_preferido: str = "gemini-3.8-flash",
    progreso_cb: Optional[object] = None,
    contexto_feedback: str = "",
    auto_auditoria_retrospectiva: bool = False,
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

    bloque_feedback = ""
    if contexto_feedback and contexto_feedback.strip():
        bloque_feedback = (
            f"\nCORRECCIONES Y FEEDBACK EXPLÍCITO DEL USUARIO (MÁXIMA PRIORIDAD):\n"
            f"- El usuario revisó una versión anterior y pide expresamente corregir:\n"
            f"  \"{contexto_feedback.strip()}\"\n"
            f"- DIRECTIVA OBLIGATORIA: Aplica estas indicaciones de forma prioritaria en la interpretación y en el guion.\n"
        )

    n_bloques_optimo = max(1, round(dur_redondeada / 5.0))
    limites_sugeridos = [int(round(i * (dur_redondeada / n_bloques_optimo))) for i in range(n_bloques_optimo + 1)]
    ejemplo_tramos = " | ".join(f"00:{limites_sugeridos[i]:02d} - 00:{limites_sugeridos[i+1]:02d}" for i in range(n_bloques_optimo))

    instruccion_extra_base = (
        f"{bloque_contexto_real}\n"
        f"{bloque_feedback}\n"
        f"DATOS EXACTOS DEL VIDEO ANALIZADO:\n"
        f"- Duración total exacta del video: {dur_redondeada} segundos (de 00:00 a 00:{dur_redondeada:02d}).\n"
        f"- Divide la narración en exactamente {n_bloques_optimo} bloques equilibrados (cada uno de ~{dur_redondeada/n_bloques_optimo:.1f} segundos, MÍNIMO 4.0s por bloque, NUNCA bloques cortos al final):\n"
        f"  Tramos sugeridos: {ejemplo_tramos}\n"
        f"- En cada bloque usa entre 2.8 y 3.2 palabras por segundo según la duración del tramo (ej. en 5s usa 14-16 palabras; en 6s usa 17-19 palabras).\n"
        f"- En ESTADO_PUBLICACION escribe: {modo_privacidad}\n"
        f"- En SCHEDULE escribe: {schedule_str.strip() if schedule_str.strip() else 'no'}\n"
        f"- En PARA_NINOS escribe: no\n"
        f"- En TONO_VIDEO escribe 'triste' si el video es triste o dramático, 'inspiracional' si es emotivo, heroico o de superación, o 'fondo' para humor, curiosidad, acción y entretenimiento general.\n"
        f"- FLECHA y CIRCULO: úsalos para destacar elementos IMPORTANTES del video (ej. el objeto en la mano, la reacción, el detalle clave). Especifica su coordenada X,Y o zona (ej. '65,55' o 'auto:chico') para que el encuadre caiga exactamente sobre el objeto real.\n"
    )

    modelos_saturados_sesion: Set[str] = set()

    def _consultar_ia_robusta(
        texto_prompt: str,
        timeout_max: float = 30.0,
        priorizar_mejor_ia: bool = True,
    ) -> str:
        partes_v: List[object] = []
        if video_bytes:
            partes_v.append(types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"))
        partes_v.append(types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"))
        partes_v.append(texto_prompt)

        partes_m: List[object] = [
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            texto_prompt,
        ]

        # Jerarquía estricta de mayor a menor potencia:
        # Siempre intenta usar la IA más poderosa primero (3.8 -> 3.6 -> 3.5 -> latest -> 2.5)
        # El segundo que recibe error o no responde pasa de inmediato al modelo inferior.
        jerarquia_modelos = [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
        ]

        # Prioridad 1: Intentar con video comprimido directo, en orden de potencia
        plan_intentos: List[Tuple[str, List[object], float]] = []
        for mod in jerarquia_modelos:
            if mod in modelos_saturados_sesion:
                continue
            plan_intentos.append((mod, partes_v, timeout_max))

        # Prioridad 2: Respaldo con mosaico liviano si falló el video en los modelos disponibles
        for mod in jerarquia_modelos:
            if mod in modelos_saturados_sesion and mod == "gemini-3.8-flash":
                continue
            plan_intentos.append((mod, partes_m, min(22.0, timeout_max)))

        ultimo_err: Optional[Exception] = None
        for mod, cont_env, t_lim in plan_intentos:
            print(f"[*] Consultando modelo IA: {mod}...")
            def _call(m=mod, cnt=cont_env, tl=t_lim):
                cli = genai.Client(
                    api_key=key_limpia,
                    http_options=types.HttpOptions(
                        timeout=max(18000, int(tl * 1000)),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
                r = cli.models.generate_content(model=m, contents=cnt)
                return (r.text or "").strip()

            ex_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            fut = ex_pool.submit(_call)
            try:
                res_txt = fut.result(timeout=t_lim + 1.0)
                ex_pool.shutdown(wait=False, cancel_futures=True)
                if res_txt and len(res_txt) > 80:
                    print(f"[+] Modelo '{mod}' respondió con éxito.")
                    return res_txt
            except Exception as e:
                ultimo_err = e
                ex_pool.shutdown(wait=False, cancel_futures=True)
                err_msg_corto = str(e) or repr(e)
                if "429" in err_msg_corto or "RESOURCE_EXHAUSTED" in err_msg_corto:
                    modelos_saturados_sesion.add(mod)
                    print(f"[!] '{mod}' sin cuota (429/saturado), pasando inmediatamente al modelo inferior...")
                elif "503" in err_msg_corto or "UNAVAILABLE" in err_msg_corto:
                    print(f"[!] '{mod}' ocupado/no disponible (503), pasando inmediatamente al modelo inferior...")
                elif "TimeoutError" in type(e).__name__ or "timeout" in err_msg_corto.lower():
                    print(f"[!] '{mod}' no respondió en {t_lim:.0f}s, pasando inmediatamente al modelo inferior...")
                else:
                    print(f"[!] '{mod}' no respondió ({err_msg_corto[:60]}), pasando inmediatamente al modelo inferior...")

        det_err = str(ultimo_err) if (ultimo_err and str(ultimo_err).strip()) else "Sin respuesta"
        raise RuntimeError(
            f"Todos los modelos de Gemini (3.8, 3.6, 3.5, 2.5) están sin cuota o no responden (429/503/timeout). "
            f"Por favor verifica tu API Key o cuota en Google AI Studio. Detalle: {det_err}"
        )

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

    # --- PASADA 1: Interpretación Real y Contexto Profundo del Video ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.15, "IA Pasada 1/3: Analizando e interpretando el video real...")
        except Exception:
            pass
    print("[*] IA Pasada 1/3: Analizando video y metadatos para interpretación real y certera...")
    prompt_p1 = (
        "ACTÚA COMO UN ANALISTA EXPERTO EN CONTENIDO AUDIOVISUAL Y NARRATIVA DIGITAL.\n"
        f"Tu tarea en esta PASADA 1 es analizar minuciosamente el video adjunto y contrastarlo con su TÍTULO y DESCRIPCIÓN originales.\n"
        f"{bloque_contexto_real}\n"
        f"Duración total del video: {dur_redondeada} segundos.\n\n"
        "Genera un informe conciso y preciso que responda:\n"
        "1. SUJETOS Y OBJETOS REALES: ¿Quiénes o qué aparecen exactamente? (sin inventar ni confundir juguetes, personas o animales).\n"
        "2. CRONOLOGÍA DE ACCIONES: ¿Qué ocurre paso a paso a lo largo del video?\n"
        "3. EL GIRO / CLÍMAX O DESENLACE: ¿Cómo termina la situación o cuál es el momento más gracioso/impactante?\n"
        "4. NICHO REAL: ¿A qué categoría temática pertenece? (ej: mascotas/perros, autos/motos, cocina, bromas familiares, etc.).\n\n"
        "Entrega tu análisis de forma directa, descriptiva y clara:"
    )
    analisis_1_raw = _consultar_ia_robusta(prompt_p1, timeout_max=40.0)
    analisis_1 = _limpiar_bloque(analisis_1_raw)

    # --- PASADA 2: Detección de Momentos Clave para Efectos (SFX, Flechas, Visuales) ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.50, "IA Pasada 2/3: Detectando momentos clave para efectos de sonido y flechas...")
        except Exception:
            pass
    print("[*] IA Pasada 2/3: Detectando momentos clave para SFX, flechas y elementos visuales...")
    prompt_p2 = (
        "ACTÚA COMO UN DIRECTOR DE EDICIÓN Y DISEÑADOR DE SONIDO/EFECTOS PARA YOUTUBE SHORTS.\n"
        f"Analiza minuciosamente el video de {dur_redondeada} segundos para detectar los momentos visuales y sonoros de mayor impacto.\n"
        f"Dividiendo la duración en bloques de 5 segundos (de 00:00 a 00:{dur_redondeada:02d}), indica para cada bloque:\n"
        "- SFX RECOMENDADO: Qué efecto sonoro encaja con lo que pasa en pantalla (elige entre: crowd_shocked, whoosh, riser_suction, ding, good_idea, cash_ting, punch, camera_flash, cartoon_laugh, kids_yeyy, party_horn, error, xp_Error, fart, click, pop, ninguno).\n"
        "- FLECHA ROJA (apuntando al sujeto u objeto principal en movimiento): si corresponde en este bloque (máximo en 2 bloques clave de todo el video, resto 'ninguna'). Opciones: 'auto', 'izquierda', 'derecha', 'centro', 'X,Y' o 'ninguna'.\n"
        "- CÍRCULO ROJO (resaltando la revelación/sorpresa máxima): si corresponde (máximo en 1 bloque de todo el video, resto 'ninguno'). Opciones: 'auto', 'izquierda', 'derecha', 'centro:grande' o 'ninguno'.\n"
        "- EMOJI: 'sorprendido', 'risa', 'fiesta', 'diablo', 'enojo', 'lloro', 'sueno' o 'ninguno'.\n\n"
        "Entrega el desglose temporal sugerido bloque por bloque:"
    )
    analisis_2_raw = _consultar_ia_robusta(prompt_p2, timeout_max=40.0)
    analisis_2 = _limpiar_bloque(analisis_2_raw)

    # --- PASADA 3: Fusión Maestra y Redacción del Guion Viral Definitivo ---
    if callable(progreso_cb):
        try:
            progreso_cb(0.80, "IA Pasada 3/3: Fusionando guion maestro con fluidez y hashtags de nicho...")
        except Exception:
            pass
    print("[*] IA Pasada 3/3: Redactando guion maestro definitivo con fluidez, sentido y hashtags...")
    prompt_p3 = (
        PROMPT_COMPACTO_INTERNO + instruccion_extra_base +
        f"\n\nACTÚA COMO EL GUIONISTA Y DIRECTOR JEFE DE YOUTUBE SHORTS VIRALES.\n"
        f"Tienes a tu disposición dos análisis especializados del mismo video:\n\n"
        f"--- [ANÁLISIS 1: INTERPRETACIÓN REAL Y HECHOS DEL VIDEO] ---\n{analisis_1}\n\n"
        f"--- [ANÁLISIS 2: MAPA DE MOMENTOS CLAVE PARA SFX Y FLECHAS] ---\n{analisis_2}\n\n"
        f"TU MISIÓN DE FUSIÓN CRÍTICA:\n"
        f"1. NARRATIVA FLUIDA Y CON SENTIDO: Cuenta exactamente lo que ocurre según el Análisis 1, con máxima intriga, humor o emoción, pero SIN inventar elementos contrarios a la realidad.\n"
        f"2. CADENCIA DE VOZ VIRAL (¡RÁPIDA Y ENÉRGICA!): Escribe EXACTAMENTE entre 15 y 17 palabras por cada bloque de 5 segundos (~3.2 palabras/segundo) para que la narración fluya con ritmo acelerado y atrapante, sin silencios muertos ni arrastrar las palabras.\n"
        f"3. EFECTOS Y FLECHAS CON SENTIDO: Usa FLECHA únicamente si hay un detalle crucial o acción oculta que señalar (máx 1 o 2 bloques en todo el video, NUNCA en el último bloque). Si no hay un objeto clave en movimiento o detalle sutil, pon 'ninguna'. Cero flechas es mucho mejor que una flecha apuntando a un lugar irrelevante.\n"
        f"4. REMATE VIRAL POTENTE: El remate final del guion debe ser memorable, ingenioso o hilarante. Aunque el video original sea simple o modesto, la narración debe elevarlo dándole un remate épico, irónico o cómico que cierre con máxima fuerza.\n"
        f"5. HASHTAGS DE NICHO REAL: En DESCRIPCION_YOUTUBE, escribe una descripción atractiva de 2 oraciones, pregunta para debate en comentarios, y 4 o 5 hashtags hiper-específicos del nicho (ej: #shorts #perros #mascotas #viral; #shorts #autos #carreras #viral; etc.).\n"
        f"6. TÍTULO CON EMOJIS OBLIGATORIOS: En TITULO_YOUTUBE incluye SIEMPRE 1 o 2 emojis llamativos acordes a la temática (ej: 😱, 🔥, 🤣, 💥, 🤯) y el hashtag #shorts al final.\n"
        f"7. COBERTURA TOTAL HASTA EL ÚLTIMO SEGUNDO: El último bloque temporal DEBE terminar en el segundo exacto 00:{dur_redondeada:02d}, cerrando con el remate del video sin dejar segundos finales sin narrar.\n\n"
        f"Entrega ÚNICAMENTE el bloque de guion final estructurado con la plantilla obligatoria:"
    )

    try:
        guion_final_raw = _consultar_ia_robusta(prompt_p3, timeout_max=45.0)
        guion_final = _limpiar_bloque(guion_final_raw)
        if guion_final and "[GUION]" in guion_final and len(guion_final) > 150:
            texto_respuesta = guion_final
            print("[+] ¡Pasada 3 completada con éxito! Guión maestro sintetizado.")
        else:
            # Fallback de emergencia si la pasada 3 falló
            print("[!] Pasada 3 no entregó estructura completa, generando síntesis directa...")
            prompt_fallback = PROMPT_COMPACTO_INTERNO + instruccion_extra_base + f"\n\n[INFORME PREVIO]:\n{analisis_1}\n\nEntrega ÚNICAMENTE el guion:"
            fb_raw = _consultar_ia_robusta(prompt_fallback, timeout_max=35.0)
            texto_respuesta = _limpiar_bloque(fb_raw)
    except Exception as err_p3:
        print(f"[!] Fusión de pasada 3 tuvo un problema ({err_p3}), intentando síntesis de respaldo...")
        prompt_fallback = PROMPT_COMPACTO_INTERNO + instruccion_extra_base + f"\n\n[INFORME PREVIO]:\n{analisis_1}\n\nEntrega ÚNICAMENTE el guion:"
        fb_raw = _consultar_ia_robusta(prompt_fallback, timeout_max=35.0)
        texto_respuesta = _limpiar_bloque(fb_raw)

    if not texto_respuesta or "[GUION]" not in texto_respuesta:
        texto_respuesta = guion_final or fb_raw or ""

    # Asegurar que el título siempre tenga al menos un emoji viral
    if texto_respuesta and "TITULO_YOUTUBE:" in texto_respuesta:
        lineas_corregidas = []
        for ln in texto_respuesta.splitlines():
            if ln.strip().upper().startswith("TITULO_YOUTUBE:"):
                partes_t = ln.split(":", 1)
                t_val = partes_t[1].strip() if len(partes_t) > 1 else ""
                tiene_emo = any(ord(c) > 0x1F300 for c in t_val)
                if not tiene_emo and t_val:
                    if "#shorts" in t_val.lower():
                        t_val = re.sub(r"(?i)#shorts", "😱🔥 #shorts", t_val).strip()
                    else:
                        t_val = f"{t_val} 😱🔥"
                lineas_corregidas.append(f"TITULO_YOUTUBE: {t_val}")
            else:
                lineas_corregidas.append(ln)
        texto_respuesta = "\n".join(lineas_corregidas)

    # --- PASADA 4: AUTO-AUDITORÍA Y RE-EDICIÓN EN RETROSPECTIVA (Hasta 3 Rondas con la Mejor IA) ---
    if auto_auditoria_retrospectiva and texto_respuesta and "[GUION]" in texto_respuesta:
        max_rondas_auditoria = 3
        guion_actual_auditar = texto_respuesta

        for ronda in range(1, max_rondas_auditoria + 1):
            if callable(progreso_cb):
                try:
                    p_val = 0.86 + (ronda / max_rondas_auditoria) * 0.12
                    progreso_cb(p_val, f"IA Auto-Auditoría (Ronda {ronda}/{max_rondas_auditoria}): Verificando coherencia y desenlace...")
                except Exception:
                    pass
            print(f"[*] IA Auto-Auditoría (Ronda {ronda}/{max_rondas_auditoria}): Evaluando video completo, flechas y desenlace en retrospectiva con la mejor IA...")

            prompt_auditoria = (
                PROMPT_COMPACTO_INTERNO + instruccion_extra_base +
                f"\n\nACTÚA COMO EL AUDITOR JEFE DE CALIDAD, VIRALIDAD Y RETROSPECTIVA DE YOUTUBE SHORTS.\n"
                f"Estás auditando y re-editando el guion para este video (Ronda de Control {ronda} de {max_rondas_auditoria}):\n\n"
                f"--- [GUION ACTUAL A AUDITAR] ---\n{guion_actual_auditar}\n\n"
                f"DIRECTIVAS ESTRICTAS DE CONTROL DE VIRALIDAD Y AUTO-CORRECCIÓN:\n"
                f"1. AUDITORÍA DE FLECHAS (TOLERANCIA CERO A FLECHAS INÚTILES O CONFUSAS):\n"
                f"   - Revisa cada línea donde figure [FLECHA:...]. ¿Apunta a un detalle real, crucial y en movimiento que la audiencia no vería sin la flecha?\n"
                f"   - Si la flecha apunta a la nada, a un objeto estático, a una pared o en un momento aburrido: ¡ELIMÍNALA INMEDIATAMENTE cambiándola a 'ninguna'!\n"
                f"   - Es preferible CERO flechas en el cuerpo del video antes que una sola flecha mal ubicada (el editor ya añade automáticamente al final un freeze-frame con flecha animada y campana de like).\n"
                f"   - Si de verdad se justifica una flecha, calibra su zona exacta: 'izquierda', 'derecha', 'centro' o coordenada X,Y donde ocurre la acción clave.\n"
                f"2. REMATE FINAL VIRAL (PUNCHLINE OBLIGATORIO Y ELEVACIÓN DEL VIDEO):\n"
                f"   - Revisa el último bloque del guion. ¿Tiene un remate gracioso, irónico, sorprendente o emocionante? ¿O termina de manera tibia, descriptiva o desinflada?\n"
                f"   - Aunque el video en sí sea simple o modesto, tu tarea como redactor de élite es ELEVARLO con un remate ingenioso, divertido o con remate de comedia/ironía que cierre con máxima fuerza y deje al espectador con ganas de comentar o volver a verlo.\n"
                f"   - El remate debe condicir fielmente con el desenlace real del video al terminar (en retrospectiva), pero con máxima chispa y energía narrativa.\n"
                f"3. GANCHO Y RETENCIÓN ADICTIVA (00:00 - 00:05):\n"
                f"   - La primera frase debe sembrar curiosidad o expectativa explosiva sin rodeos ni saludos aburridos.\n"
                f"4. FIDELIDAD TOTAL A LOS HECHOS:\n"
                f"   - No confundas objetos reales (bolígrafos, herramientas, juguetes, celulares, etc.).\n"
                f"5. CADENCIA VIRAL:\n"
                f"   - Mantén estrictamente entre 15 y 17 palabras por bloque de 5s para que la voz fluya con dinamismo y ritmo acelerado.\n\n"
                f"REGLA DE DECISIÓN OBLIGATORIA:\n"
                f"- Si el guion actual ya es un 10/10 en viralidad, el remate es brillante y las flechas están 100% justificadas o en 'ninguna': responde en la primera línea 'ESTADO_AUDITORIA: APROBADO' y nada más.\n"
                f"- Si el remate es flojo, hay alguna flecha mal puesta o falta gancho: responde en la primera línea 'ESTADO_AUDITORIA: REQUIERE_AJUSTES', explica brevemente en 'MOTIVO_AJUSTE: ...', y entrega INMEDIATAMENTE a continuación el GUION RE-EDITADO Y PERFECCIONADO completo con la plantilla obligatoria."
            )

            try:
                res_aud_raw = _consultar_ia_robusta(
                    prompt_auditoria,
                    timeout_max=42.0,
                    priorizar_mejor_ia=True,
                )
                res_aud = _limpiar_bloque(res_aud_raw)

                if "ESTADO_AUDITORIA: APROBADO" in res_aud or res_aud.startswith("APROBADO"):
                    print(f"[+] ¡Auto-auditoría superada con éxito en Ronda {ronda}! El guion es 100% coherente con el video.")
                    break

                if "[GUION]" in res_aud:
                    idx_inicio = res_aud.find("TITULO_SUPERIOR:")
                    if idx_inicio == -1:
                        idx_inicio = res_aud.find("[GUION]")
                    guion_corregido = res_aud[idx_inicio:].strip() if idx_inicio != -1 else res_aud
                    if len(guion_corregido) > 150:
                        guion_actual_auditar = guion_corregido
                        texto_respuesta = guion_corregido
                        print(f"[+] [Ronda {ronda}] Inconsistencia detectada y corregida. Guion re-editado por la mejor IA.")
                        if ronda == max_rondas_auditoria:
                            print(f"[+] Se completó el máximo de {max_rondas_auditoria} rondas de re-edición y ajuste.")
                else:
                    print(f"[*] Ronda {ronda}: No se requirieron cambios estructurales adicionales.")
                    break
            except Exception as e_aud:
                print(f"[!] Aviso en ronda {ronda} de auto-auditoría ({e_aud}), finalizando auditoría.")
                break

    DEFAULT_GUION_TXT.write_text(texto_respuesta + "\n", encoding="utf-8")
    print(f"[+] ¡Guión final perfeccionado y guardado en {DEFAULT_GUION_TXT.name}!")
    if callable(progreso_cb):
        try:
            progreso_cb(1.0, "Guión viral de triple pasada completado.")
        except Exception:
            pass
    return texto_respuesta
