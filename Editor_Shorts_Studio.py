#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
EDITOR SHORTS STUDIO v1.0 - Automatización de YouTube Shorts con IA
================================================================================
- Descarga automática de videos/Shorts de YouTube con yt-dlp (o archivo MP4 local).
- Narración con Voz IA expresiva + Masterización de estudio con FFmpeg.
- Subtítulos dinámicos ultra llamativos con efectos luminosos (Resplandor Neón
  multicapa, brillo especular y pulso reactivo a la voz).
- Seguimiento inteligente de objetivos (Optical Flow + Saliencia en movimiento)
  para Flechas Rojas (flecha.png) y Círculos Rojos (circulo_rojo.png).
- Efectos de cámara y color sincronizados con los 19 SFX y 7 Emojis animados.
================================================================================
"""

import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


# ==============================================================================
# 1. CONFIGURACIÓN GENERAL Y RUTAS DE ASSETS
# ==============================================================================
WIDTH = 1080
HEIGHT = 1920
FPS = 60
CPU_THREADS = max(4, (os.cpu_count() or 8))

MODO_ENCUADRE_DEFAULT = "full"  # "full" (9:16 crop-fill) o "blur" (fondo borroso para horizontales)
VOLUMEN_VOZ_NARRADOR = 1.48
VOLUMEN_AUDIO_VIDEO_ORIGINAL = 0.16
SUBTITLE_OFFSET_SEC = -0.02
DURACION_CALLOUTS_DEFAULT = 1.8  # Segundos que permanecen visibles las flechas y círculos (Shorts ágiles)

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

VOCES_DISPONIBLES: Dict[str, str] = {
    "Giuseppe (YouTuber Hype - Recomendada)": "it-IT-GiuseppeMultilingualNeural",
    "Tomás (Argentina Dinámico)": "es-AR-TomasNeural",
    "Jorge (México Dinámico)": "es-MX-JorgeNeural",
    "Álvaro (España Intenso)": "es-ES-AlvaroNeural",
    "Dalia (Femenina Expresiva)": "es-MX-DaliaNeural",
}
EDGE_VOICE_DEFAULT = "it-IT-GiuseppeMultilingualNeural"
EDGE_PITCH_DEFAULT = "+0Hz"

BASE_DIR = Path(__file__).resolve().parent


def _resolver_carpeta_asset(nombre: str) -> Path:
    directa = BASE_DIR / nombre
    if directa.exists():
        return directa
    en_assets = BASE_DIR / "assets" / nombre
    if en_assets.exists():
        return en_assets
    directa.mkdir(parents=True, exist_ok=True)
    return directa


EMOJIS_DIR = _resolver_carpeta_asset("emojis")
FONTS_DIR = _resolver_carpeta_asset("fonts")
FOTOS_DIR = _resolver_carpeta_asset("fotos")
SFX_DIR = _resolver_carpeta_asset("sfx")
TEMP_DIR = BASE_DIR / "temp_build"
OUTPUT_DIR = BASE_DIR / "output_shorts"

DEFAULT_VIDEO_INPUT = BASE_DIR / "video_input.mp4"
DEFAULT_GUION_TXT = BASE_DIR / "guion_video.txt"
PROMPT_IA_PATH = BASE_DIR / "PROMPT_PARA_IA_GUIONES.txt"
PROMPT_COMPACTO_PATH = BASE_DIR / "PROMPT_ARGON_COMPACTO.txt"


# ==============================================================================
# 2. ESTRUCTURAS DE DATOS
# ==============================================================================
@dataclass
class SegmentoVideoGuion:
    id_segmento: str
    texto_voz: str
    efecto_visual: str = "ninguno"          # "zoom_impacto", "zoom_in", "zoom_out", "flash", "temblor", "alerta_roja", "brillo_epico", "blanco_negro", "ninguno"
    t_inicio_video: Optional[float] = None  # Segundos en el video original (None = reparto automático)
    t_fin_video: Optional[float] = None     # Segundos en el video original (None = reparto automático)
    pausa_final_seg: float = 0.16
    sfx_lista: List[str] = field(default_factory=list)
    emoji: Optional[str] = None             # "diablo", "enojo", "fiesta", "lloro", "risa", "sorprendido", "sueno"
    posicion_emoji: str = "auto"            # "auto", "derecha", "izquierda", "arriba_der", "arriba_izq", "centro"
    flecha: Optional[str] = None            # "centro", "izquierda", "derecha", "arriba", "abajo", "auto", "x,y", "x1,y1->x2,y2", None
    circulo: Optional[str] = None           # "centro", "izquierda", "derecha", "arriba", "abajo", "auto", "x,y", "si", None
    tamano_circulo: str = "medio"           # "chico", "medio", "grande"


@dataclass
class ConfigGuion:
    titulo_superior: str = ""
    titulo_youtube: str = ""
    descripcion_youtube: str = ""
    estado_publicacion: str = "privado"
    schedule: Optional[str] = None
    para_ninos: bool = False
    tags_youtube: List[str] = field(default_factory=list)
    modo_encuadre: str = MODO_ENCUADRE_DEFAULT
    voz_narrador: str = EDGE_VOICE_DEFAULT
    archivo_salida: Optional[str] = None
    volumen_video_original: float = VOLUMEN_AUDIO_VIDEO_ORIGINAL
    duracion_callouts: float = DURACION_CALLOUTS_DEFAULT
    palabras_verdes_extra: Set[str] = field(default_factory=set)
    palabras_rojas_extra: Set[str] = field(default_factory=set)
    palabras_cian_extra: Set[str] = field(default_factory=set)
    segmentos: List[SegmentoVideoGuion] = field(default_factory=list)


@dataclass
class PalabraSubtitulo:
    texto: str
    inicio_seg: float
    fin_seg: float
    forzar_destaque: bool = False


# ==============================================================================
# 3. PARSER INTELIGENTE DE GUIONES Y NORMALIZACIÓN DE ASSETS
# ==============================================================================
PLANTILLA_GUION_DEFAULT = """TITULO_SUPERIOR: Abuela Venganza Epica Troleo
MODO_ENCUADRE: full
VOLUMEN_VIDEO_ORIGINAL: 0
ARCHIVO_SALIDA: auto

[GUION]
TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
00:00 - 00:05 | zoom_impacto | crowd_shocked | sorprendido:derecha | izquierda | ninguno | ¡Mira cómo esta nieta traviesa engaña a su abuela escondiendo la pelota de tenis! ¡La pobre no entiende absolutamente nada!
00:05 - 00:10 | zoom_in | whoosh+xp_Error | enojo:izquierda | centro | ninguno | ¡La broma sigue cuando hace desaparecer otro objeto frente a su cara! ¡Su abuela busca confundida por toda la mesa!
00:10 - 00:15 | alerta_roja | riser_suction | diablo:derecha | izquierda | izquierda:grande | ¡Pero cuidado porque la abuela ya tenía preparada una trampa secreta! ¡Prepárate para ver la venganza más épica de todas!
00:15 - 00:20 | temblor | punch+cartoon_laugh | risa:izquierda | derecha | ninguno | ¡Toma esto por tramposa! ¡La nieta termina con toda la cara completamente llena de harina blanca en un segundo!
00:20 - 00:25 | brillo_epico | cash_ting+party_horn | fiesta:derecha | ninguna | ninguno | ¡La abuela celebra su victoria mientras la nieta no puede creer lo que acaba de pasar! ¡Una venganza perfecta!
"""


def _quitar_acentos(texto: str) -> str:
    norm = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def _parsear_tiempo_a_segundos(t_str: str) -> Optional[float]:
    t_str = str(t_str).strip()
    if not t_str or t_str.lower() in ("auto", "-", "none", "null"):
        return None
    if ":" in t_str:
        partes = t_str.split(":")
        try:
            if len(partes) == 2:
                return int(partes[0]) * 60.0 + float(partes[1].replace(",", "."))
            elif len(partes) == 3:
                return int(partes[0]) * 3600.0 + int(partes[1]) * 60.0 + float(partes[2].replace(",", "."))
        except ValueError:
            return None
    try:
        return float(t_str.replace(",", "."))
    except ValueError:
        return None


def _normalizar_efecto(efecto_raw: Optional[str]) -> str:
    if not efecto_raw:
        return "ninguno"
    e = _quitar_acentos(str(efecto_raw).strip().lower()).replace(" ", "_")
    if not e or e in ("ninguno", "ninguna", "none", "no", "-", "normal"):
        return "ninguno"

    mapa_efectos = {
        "zoom_impacto": "zoom_impacto",
        "impacto": "zoom_impacto",
        "punch": "zoom_impacto",
        "golpe": "zoom_impacto",
        "choque": "zoom_impacto",
        "shock": "zoom_impacto",
        "saludo": "zoom_impacto",
        "zoom_in": "zoom_in",
        "zoom": "zoom_in",
        "acercar": "zoom_in",
        "hablando": "zoom_in",
        "zoom_out": "zoom_out",
        "alejar": "zoom_out",
        "hablando2": "zoom_out",
        "flash": "flash",
        "destello": "flash",
        "camara": "flash",
        "foto": "flash",
        "temblor": "temblor",
        "shake": "temblor",
        "terremoto": "temblor",
        "vibracion": "temblor",
        "alerta_roja": "alerta_roja",
        "alerta": "alerta_roja",
        "peligro": "alerta_roja",
        "rojo": "alerta_roja",
        "error": "alerta_roja",
        "brillo_epico": "brillo_epico",
        "epico": "brillo_epico",
        "glow": "brillo_epico",
        "dorado": "brillo_epico",
        "victoria": "brillo_epico",
        "fiesta": "brillo_epico",
        "like": "brillo_epico",
        "blanco_negro": "blanco_negro",
        "gris": "blanco_negro",
        "triste": "blanco_negro",
        "sad": "blanco_negro",
        "fail": "blanco_negro",
        "bn": "blanco_negro",
    }
    return mapa_efectos.get(e, "zoom_in")


def _normalizar_sfx_lista(sfx_raw: Optional[str]) -> List[str]:
    if not sfx_raw:
        return []
    raw_clean = _quitar_acentos(str(sfx_raw).strip().lower())
    raw_clean = raw_clean.replace(".mp3", "").replace(".wav", "").replace(".ogg", "")
    if not raw_clean or raw_clean in ("ninguno", "ninguna", "none", "no", "false", "-", "sin_sfx"):
        return []

    sinonimos_sfx = {
        "shock": "crowd_shocked",
        "sorpresa": "crowd_shocked",
        "asombro": "crowd_shocked",
        "multitud": "crowd_shocked",
        "campana": "boxing_bell",
        "bell": "boxing_bell",
        "boxeo": "boxing_bell",
        "round": "boxing_bell",
        "flash": "camera_flash",
        "destello": "camera_flash",
        "foto": "camera_shooter",
        "camara": "camera_shooter",
        "screenshot": "camera_shooter",
        "risa": "cartoon_laugh",
        "risas": "cartoon_laugh",
        "laugh": "cartoon_laugh",
        "dinero": "cash_ting",
        "caja": "cash_ting",
        "cash": "cash_ting",
        "moneda": "cash_ting",
        "robux": "cash_ting",
        "idea": "good_idea",
        "brillante": "good_idea",
        "correcto": "ding",
        "acierto": "ding",
        "festejo": "kids_yeyy",
        "celebracion": "kids_yeyy",
        "yey": "kids_yeyy",
        "ninos": "kids_yeyy",
        "corneta": "party_horn",
        "fiesta": "party_horn",
        "party": "party_horn",
        "golpe": "punch",
        "impacto": "punch",
        "pelea": "punch",
        "subida": "riser_suction",
        "riser": "riser_suction",
        "suction": "riser_suction",
        "tension": "riser_suction",
        "tictac": "riser_suction",
        "timer": "riser_suction",
        "transicion": "whoosh",
        "viento": "whoosh",
        "windows": "xp_error",
        "xp": "xp_error",
        "bug": "xp_error",
        "fallo": "error",
        "fail": "xp_error",
        "pedo": "fart",
        "broma": "fart",
        "tierno": "awww",
        "triste": "awww",
        "aww": "awww",
    }

    partes = re.split(r"[+,;/]", raw_clean)
    resultado: List[str] = []
    for p in partes:
        item = p.strip().replace(" ", "_")
        if not item or item in ("ninguno", "no", "-"):
            continue
        item_norm = sinonimos_sfx.get(item, item)
        if item_norm not in resultado:
            resultado.append(item_norm)
    return resultado


def _normalizar_emoji(emoji_raw: Optional[str]) -> Tuple[Optional[str], str]:
    if not emoji_raw:
        return None, "auto"
    raw = str(emoji_raw).strip()
    posicion = "auto"
    if ":" in raw:
        raw, pos_part = raw.split(":", 1)
        pos_clean = _quitar_acentos(pos_part.strip().lower())
        if pos_clean in ("izquierda", "derecha", "centro", "arriba", "abajo", "arriba_izq", "arriba_der"):
            posicion = pos_clean

    e = _quitar_acentos(raw.strip().lower())
    e = e.replace(".png", "").replace(".webp", "").replace(".jpg", "")
    if e.startswith("emoji_"):
        e = e[len("emoji_"):]

    if not e or e in ("ninguno", "ninguna", "none", "no", "false", "-", "flecha", "circulo"):
        return None, posicion

    sinonimos_emoji = {
        "diablito": "diablo",
        "malvado": "diablo",
        "enojado": "enojo",
        "furia": "enojo",
        "rabia": "enojo",
        "festejo": "fiesta",
        "celebracion": "fiesta",
        "llorando": "lloro",
        "triste": "lloro",
        "tristeza": "lloro",
        "risas": "risa",
        "riendo": "risa",
        "gracioso": "risa",
        "lol": "risa",
        "sorpresa": "sorprendido",
        "shock": "sorprendido",
        "impactado": "sorprendido",
        "dormido": "sueno",
        "aburrido": "sueno",
        "zzz": "sueno",
    }
    return sinonimos_emoji.get(e, e), posicion


def _normalizar_objetivo(obj_raw: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Normaliza la especificación de FLECHA o CIRCULO.
    Devuelve (objetivo_normalizado, tamano_modificador).
    Ejemplo: 'centro:grande' -> ('centro', 'grande')
             'izquierda'     -> ('izquierda', 'medio')
             'ninguno'       -> (None, 'medio')
    """
    if not obj_raw:
        return None, "medio"
    raw = _quitar_acentos(str(obj_raw).strip().lower())
    raw = raw.replace(".png", "").replace("circulo_rojo", "si").replace("flecha", "si")

    tamano = "medio"
    if ":" in raw:
        base_part, mod_part = raw.split(":", 1)
        mod_clean = mod_part.strip()
        if mod_clean in ("chico", "pequeno", "small", "min"):
            tamano = "chico"
            raw = base_part.strip()
        elif mod_clean in ("grande", "big", "large", "max"):
            tamano = "grande"
            raw = base_part.strip()
        elif mod_clean in ("medio", "normal", "med"):
            tamano = "medio"
            raw = base_part.strip()
        else:
            raw = mod_clean

    if not raw or raw in ("ninguno", "ninguna", "none", "no", "false", "-", "0"):
        return None, tamano

    if raw in ("si", "yes", "true", "1", "activo", "activar", "mismo", "igual"):
        return "si", tamano

    sinonimos_zona = {
        "izq": "izquierda",
        "left": "izquierda",
        "der": "derecha",
        "right": "derecha",
        "center": "centro",
        "medio": "centro",
        "top": "arriba",
        "bottom": "abajo",
        "movimiento": "auto",
        "automatico": "auto",
        "objetivo": "auto",
    }
    return sinonimos_zona.get(raw, raw), tamano


def cargar_guion_video(ruta_guion: Path) -> ConfigGuion:
    if not ruta_guion.exists():
        DEFAULT_GUION_TXT.write_text(PLANTILLA_GUION_DEFAULT.strip() + "\n", encoding="utf-8")
        ruta_guion = DEFAULT_GUION_TXT

    contenido = ruta_guion.read_text(encoding="utf-8-sig").strip()
    if contenido.startswith("```"):
        lineas_md = contenido.splitlines()
        if lineas_md and lineas_md[0].startswith("```"):
            lineas_md = lineas_md[1:]
        if lineas_md and lineas_md[-1].strip().startswith("```"):
            lineas_md = lineas_md[:-1]
        contenido = "\n".join(lineas_md).strip()

    config = ConfigGuion()

    # Soporte para JSON si el usuario pega un bloque JSON
    if contenido.startswith("{"):
        datos = json.loads(contenido)
        config.titulo_superior = str(datos.get("titulo_superior", "") or "").strip()
        config.modo_encuadre = str(datos.get("modo_encuadre", datos.get("modo_pantalla", MODO_ENCUADRE_DEFAULT))).strip().lower()
        salida_raw = str(datos.get("archivo_salida", "") or "").strip()
        config.archivo_salida = None if salida_raw.lower() in ("", "auto", "none", "null") else salida_raw
        if "volumen_video_original" in datos:
            try:
                config.volumen_video_original = float(datos["volumen_video_original"])
            except (ValueError, TypeError):
                pass
        if "duracion_callouts" in datos:
            try:
                config.duracion_callouts = max(0.5, float(datos["duracion_callouts"]))
            except (ValueError, TypeError):
                pass
        for idx, seg in enumerate(datos.get("segmentos", [])):
            t_ini, t_fin = None, None
            if "tiempo" in seg and "-" in str(seg["tiempo"]):
                p1, p2 = str(seg["tiempo"]).split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(p1)
                t_fin = _parsear_tiempo_a_segundos(p2)
            efecto = _normalizar_efecto(seg.get("efecto", seg.get("gesto", "ninguno")))
            sfx_lista = _normalizar_sfx_lista(seg.get("sfx", None))
            emoji, pos_emoji = _normalizar_emoji(seg.get("emoji", None))
            flecha, _ = _normalizar_objetivo(seg.get("flecha", None))
            circulo, tam_c = _normalizar_objetivo(seg.get("circulo", None))
            texto = str(seg.get("texto", seg.get("texto_voz", ""))).strip()
            if flecha == "si" and circulo and circulo != "si":
                flecha = circulo
            elif circulo == "si" and flecha and flecha != "si":
                circulo = flecha
            elif flecha == "si":
                flecha = "auto"
            elif circulo == "si":
                circulo = "auto"

            if texto:
                config.segmentos.append(
                    SegmentoVideoGuion(
                        id_segmento=f"{len(config.segmentos) + 1:02d}_seg",
                        texto_voz=texto,
                        efecto_visual=efecto,
                        t_inicio_video=t_ini,
                        t_fin_video=t_fin,
                        sfx_lista=sfx_lista,
                        emoji=emoji,
                        posicion_emoji=pos_emoji,
                        flecha=flecha,
                        circulo=circulo,
                        tamano_circulo=tam_c,
                    )
                )
        return config

    # Formato de texto estructurado separado por '|'
    en_guion = False
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or limpia.startswith("//"):
            continue
        if limpia.upper() in ("[GUION]", "[GUIÓN]", "[SCRIPT]", "[SEGMENTOS]"):
            en_guion = True
            continue

        if not en_guion:
            if ":" in limpia and "|" not in limpia:
                k, v = limpia.split(":", 1)
                k_up = _quitar_acentos(k.strip().upper())
                v_str = v.strip()
                if k_up in ("TITULO_SUPERIOR", "TITULO"):
                    config.titulo_superior = "" if v_str.lower() in ("ninguno", "none", "-", "vacio") else v_str
                elif k_up in ("TITULO_YOUTUBE", "YOUTUBE_TITULO"):
                    config.titulo_youtube = v_str
                elif k_up in ("DESCRIPCION_YOUTUBE", "YOUTUBE_DESCRIPCION", "DESCRIPCION"):
                    config.descripcion_youtube = v_str
                elif k_up in ("ESTADO_PUBLICACION", "MODO_PUBLICACION", "PRIVACIDAD"):
                    config.estado_publicacion = v_str.lower()
                elif k_up in ("SCHEDULE", "PROGRAMAR", "PUBLICAR_EN"):
                    config.schedule = v_str
                elif k_up in ("PARA_NINOS", "KIDS", "MADE_FOR_KIDS", "ES_PARA_NINOS"):
                    v_clean = _quitar_acentos(v_str.lower())
                    config.para_ninos = v_clean in ("si", "true", "yes", "1", "kids")
                elif k_up in ("TAGS", "ETIQUETAS", "YOUTUBE_TAGS"):
                    config.tags_youtube = [t.strip().lstrip("#") for t in v_str.split(",") if t.strip()]
                elif k_up in ("MODO_ENCUADRE", "MODO_PANTALLA", "ENCUADRE"):
                    config.modo_encuadre = "blur" if "blur" in v_str.lower() or "borroso" in v_str.lower() else "full"
                elif k_up in ("VOZ", "VOZ_NARRADOR"):
                    for label_v, id_v in VOCES_DISPONIBLES.items():
                        if v_str.lower() in label_v.lower() or v_str.lower() == id_v.lower():
                            config.voz_narrador = id_v
                            break
                elif k_up in ("ARCHIVO_SALIDA", "SALIDA", "OUTPUT"):
                    config.archivo_salida = None if v_str.lower() in ("", "auto", "none", "-") else v_str
                elif k_up == "VOLUMEN_VIDEO_ORIGINAL":
                    try:
                        config.volumen_video_original = float(v_str.replace(",", "."))
                    except ValueError:
                        pass
                elif k_up in ("DURACION_CALLOUTS", "DURACION_FLECHAS", "DURACION_CIRCULOS", "DURACION_FLECHAS_CIRCULOS"):
                    try:
                        config.duracion_callouts = max(0.5, float(v_str.replace(",", ".")))
                    except ValueError:
                        pass
                elif k_up == "PALABRAS_VERDES":
                    for w in v_str.split(","):
                        if w.strip():
                            config.palabras_verdes_extra.add(w.strip().upper())
                elif k_up == "PALABRAS_ROJAS":
                    for w in v_str.split(","):
                        if w.strip():
                            config.palabras_rojas_extra.add(w.strip().upper())
            continue

        partes = [p.strip() for p in limpia.split("|")]
        if len(partes) >= 2 and _quitar_acentos(partes[0].upper()) in ("TIEMPO", "TIEMPOS", "TIME"):
            continue

        t_ini, t_fin = None, None
        efecto = "ninguno"
        sfx_lista: List[str] = []
        emoji: Optional[str] = None
        pos_emoji = "auto"
        flecha: Optional[str] = None
        circulo: Optional[str] = None
        tam_circulo = "medio"
        texto_voz = ""

        if len(partes) >= 8 and _quitar_acentos(partes[5].lower()) in ("si", "no", "true", "false") and _quitar_acentos(partes[6].lower()) in ("si", "no", "true", "false"):
            # Compatibilidad con guiones antiguos de 8 columnas:
            # TIEMPO | GESTO | SFX | EMOJI | FLECHA | LIKE_SUB | TIMER | TEXTO
            rango_t, gesto_str, sfx_str, emoji_str, flecha_str, likesub_str, timer_str = partes[:7]
            texto_voz = " | ".join(partes[7:]).strip()
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(gesto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
        elif len(partes) >= 7:
            # FORMATO OFICIAL DE 7 COLUMNAS:
            # TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO
            rango_t, efecto_str, sfx_str, emoji_str, flecha_str, circulo_str = partes[:6]
            texto_voz = " | ".join(partes[6:]).strip()
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(efecto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
            circulo, tam_circulo = _normalizar_objetivo(circulo_str)
            # Compatibilidad si en la columna 6 pusieron "si/no" de un guion viejo de 7 columnas sin querer
            if circulo == "si" and not flecha:
                circulo = None
        elif len(partes) == 6:
            # TIEMPO | EFECTO | SFX | EMOJI | FLECHA | TEXTO
            rango_t, efecto_str, sfx_str, emoji_str, flecha_str, texto_voz = partes
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            efecto = _normalizar_efecto(efecto_str)
            sfx_lista = _normalizar_sfx_lista(sfx_str)
            emoji, pos_emoji = _normalizar_emoji(emoji_str)
            flecha, _ = _normalizar_objetivo(flecha_str)
        elif len(partes) >= 2:
            rango_t = partes[0]
            if "-" in rango_t and rango_t.lower() != "-":
                t1, t2 = rango_t.split("-", 1)
                t_ini = _parsear_tiempo_a_segundos(t1)
                t_fin = _parsear_tiempo_a_segundos(t2)
            texto_voz = partes[-1]
        else:
            texto_voz = limpia

        # Sincronizar cuando uno dice "si" y el otro tiene la ubicación del objetivo
        if flecha == "si" and circulo and circulo != "si":
            flecha = circulo
        elif circulo == "si" and flecha and flecha != "si":
            circulo = flecha
        elif flecha == "si":
            flecha = "auto"
        elif circulo == "si":
            circulo = "auto"

        if texto_voz:
            config.segmentos.append(
                SegmentoVideoGuion(
                    id_segmento=f"{len(config.segmentos) + 1:02d}_seg",
                    texto_voz=texto_voz,
                    efecto_visual=efecto,
                    t_inicio_video=t_ini,
                    t_fin_video=t_fin,
                    sfx_lista=sfx_lista,
                    emoji=emoji,
                    posicion_emoji=pos_emoji,
                    flecha=flecha,
                    circulo=circulo,
                    tamano_circulo=tam_circulo,
                )
            )

    return config


# ==============================================================================
# 4. TIPOGRAFÍA Y MOTOR DE SUBTÍTULOS LUMINOSOS (RESPLANDOR NEÓN MULTICAPA)
# ==============================================================================
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}
_RUTA_FUENTE_ACTIVA: Optional[str] = None
_WORD_SPRITE_CACHE: Dict[Tuple[str, int, Tuple[int, int, int], Tuple[int, int, int], bool], Image.Image] = {}

PALABRAS_VERDES_BASE = {
    "CARO", "DÓLARES", "DOLARES", "MILLONES", "MIL", "DINERO", "PRECIO",
    "VALE", "PRO", "PROS", "VICTORIA", "GANAR", "GANÉ", "GRATIS", "ORO",
    "ROBUX", "MUCHÍSIMO", "MUCHISIMO", "MEJOR", "FAVORITA", "FAVORITO",
    "PREMIO", "SORTEO", "100", "99", "NOVENTA", "NUEVE",
}
PALABRAS_ROJAS_BASE = {
    "IMPOSIBLE", "LOCURA", "DIFÍCIL", "DIFICIL", "NUNCA", "SECRETO",
    "SUSCRÍBETE", "SUSCRIBETE", "SUSCRIBITE", "LIKE", "PELIGRO", "PROHIBIDO",
    "MUERTE", "ERROR", "ESTAFA", "POCO", "NADA", "PEOR", "OCULTO", "FALLA",
    "CORTA", "CUIDADO", "JAMÁS", "JAMAS",
}
PALABRAS_CIAN_BASE = {
    "2050", "2026", "2000", "CINCUENTA", "VEINTISÉIS", "VEINTISEIS",
    "CÓMO", "COMO", "QUÉ", "QUE", "CUÁL", "CUAL", "FUTURO", "TIEMPO",
    "AÑO", "ANO", "NIVEL", "MIRA", "MIRÁ", "ATENCIÓN", "ATENCION",
}


def asegurar_fuente_mrbeast() -> Optional[str]:
    global _RUTA_FUENTE_ACTIVA
    if _RUTA_FUENTE_ACTIVA and os.path.exists(_RUTA_FUENTE_ACTIVA):
        return _RUTA_FUENTE_ACTIVA

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    preferidas = [
        "MrBeast_Gaming_Font.ttf",
        "KomikaAxis.ttf",
        "KOMIKAX_.ttf",
        "MrBeast.ttf",
        "Burbank.ttf",
        "ObelixPro.ttf",
    ]
    for nombre in preferidas:
        candidata = FONTS_DIR / nombre
        if candidata.exists():
            _RUTA_FUENTE_ACTIVA = str(candidata)
            return _RUTA_FUENTE_ACTIVA

    for archivo in sorted(FONTS_DIR.glob("*.[to]tf")):
        if archivo.stat().st_size > 10_000:
            _RUTA_FUENTE_ACTIVA = str(archivo)
            return _RUTA_FUENTE_ACTIVA

    sistema = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/ariblk.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for s in sistema:
        if os.path.exists(s):
            _RUTA_FUENTE_ACTIVA = s
            return _RUTA_FUENTE_ACTIVA
    return None


def cargar_fuente(tamano: int) -> ImageFont.FreeTypeFont:
    if tamano in _FONT_CACHE:
        return _FONT_CACHE[tamano]
    ruta = asegurar_fuente_mrbeast()
    if ruta:
        try:
            _FONT_CACHE[tamano] = ImageFont.truetype(ruta, tamano)
            return _FONT_CACHE[tamano]
        except Exception:
            pass
    _FONT_CACHE[tamano] = ImageFont.load_default()
    return _FONT_CACHE[tamano]


def _obtener_sprite_palabra_luminosa(
    texto_up: str,
    tam_fuente: int,
    color_relleno: Tuple[int, int, int],
    color_glow: Tuple[int, int, int],
    es_activa: bool,
) -> Image.Image:
    """
    Construye y cachea un sprite RGBA para una palabra con:
    1) Sombra 3D profunda en la capa inferior (para no tapar la luz neón)
    2) Resplandor Neón Exterior amplio (GaussianBlur radio 22, trazo ancho)
    3) Halo Neón Incandescente intenso por fuera del borde negro (GaussianBlur radio 7)
    4) Contorno exterior luminoso + Borde negro nítido
    5) Relleno vibrante + Brillo especular superior cristalino
    """
    clave = (texto_up, tam_fuente, color_relleno, color_glow, es_activa)
    if clave in _WORD_SPRITE_CACHE:
        return _WORD_SPRITE_CACHE[clave]

    fuente = cargar_fuente(tam_fuente)
    grosor_borde_negro = 9 if es_activa else 8
    pad = 58 if es_activa else 42

    dummy = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d_dummy = ImageDraw.Draw(dummy)
    bbox = d_dummy.textbbox((0, 0), texto_up, font=fuente, stroke_width=grosor_borde_negro + 16)
    w_txt = max(1, bbox[2] - bbox[0])
    h_txt = max(1, bbox[3] - bbox[1])

    w_canvas = w_txt + pad * 2
    h_canvas = h_txt + pad * 2
    cx = w_canvas // 2
    cy = h_canvas // 2

    lienzo_palabra = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))

    # 1. Sombra 3D profunda al fondo (detrás del resplandor neón)
    capa_sombra = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_sombra = ImageDraw.Draw(capa_sombra)
    sx, sy = (6, 10) if es_activa else (5, 8)
    d_sombra.text(
        (cx + sx, cy + sy),
        texto_up,
        font=fuente,
        fill=(0, 0, 0, 220),
        anchor="mm",
        stroke_width=grosor_borde_negro + 4,
        stroke_fill=(0, 0, 0, 220),
    )
    capa_sombra = capa_sombra.filter(ImageFilter.GaussianBlur(radius=3.5))
    lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_sombra)

    # 2. Resplandor Neón Exterior Amplio (Aura luminosa que sobresale del borde negro)
    capa_aura = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_aura = ImageDraw.Draw(capa_aura)
    alpha_aura = 250 if es_activa else 135
    d_aura.text(
        (cx, cy),
        texto_up,
        font=fuente,
        fill=(*color_glow, alpha_aura),
        anchor="mm",
        stroke_width=grosor_borde_negro + (18 if es_activa else 10),
        stroke_fill=(*color_glow, alpha_aura),
    )
    capa_aura = capa_aura.filter(ImageFilter.GaussianBlur(radius=20 if es_activa else 12))
    lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_aura)

    # 3. Halo Neón Interior Incandescente (Luz concentrada pegada al exterior del trazo)
    if es_activa:
        capa_halo = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
        d_halo = ImageDraw.Draw(capa_halo)
        color_halo_claro = (
            min(255, color_glow[0] + 75),
            min(255, color_glow[1] + 75),
            min(255, color_glow[2] + 75),
            255,
        )
        d_halo.text(
            (cx, cy),
            texto_up,
            font=fuente,
            fill=color_halo_claro,
            anchor="mm",
            stroke_width=grosor_borde_negro + 9,
            stroke_fill=color_halo_claro,
        )
        capa_halo = capa_halo.filter(ImageFilter.GaussianBlur(radius=6.0))
        lienzo_palabra = Image.alpha_composite(lienzo_palabra, capa_halo)

    # 4. Contorno luminoso fino + Borde negro nítido + Relleno vibrante
    capa_texto = Image.new("RGBA", (w_canvas, h_canvas), (0, 0, 0, 0))
    d_txt = ImageDraw.Draw(capa_texto)

    if es_activa:
        color_rim = (
            min(255, color_glow[0] + 95),
            min(255, color_glow[1] + 95),
            min(255, color_glow[2] + 95),
            235,
        )
        d_txt.text(
            (cx, cy),
            texto_up,
            font=fuente,
            fill=color_rim,
            anchor="mm",
            stroke_width=grosor_borde_negro + 3,
            stroke_fill=color_rim,
        )

    d_txt.text(
        (cx, cy),
        texto_up,
        font=fuente,
        fill=(*color_relleno, 255),
        anchor="mm",
        stroke_width=grosor_borde_negro,
        stroke_fill=(8, 8, 14, 255),
    )

    # 5. Brillo especular superior en letras activas (efecto luminoso cristalino)
    if es_activa:
        mascara_interior = Image.new("L", (w_canvas, h_canvas), 0)
        d_mask = ImageDraw.Draw(mascara_interior)
        d_mask.text((cx, cy), texto_up, font=fuente, fill=255, anchor="mm", stroke_width=0)
        grad_np = np.zeros((h_canvas, w_canvas), dtype=np.uint8)
        y_top = max(0, cy - h_txt // 2)
        y_mid = min(h_canvas, cy + 4)
        if y_mid > y_top:
            rampa = np.linspace(155, 0, y_mid - y_top, dtype=np.float32)
            grad_np[y_top:y_mid, :] = rampa[:, None].astype(np.uint8)
        grad_img = Image.fromarray(grad_np, mode="L")
        brillo_alpha = ImageChops.multiply(mascara_interior, grad_img)
        capa_brillo = Image.new("RGBA", (w_canvas, h_canvas), (255, 255, 255, 0))
        capa_brillo.putalpha(brillo_alpha)
        capa_texto = Image.alpha_composite(capa_texto, capa_brillo)

    sprite_final = Image.alpha_composite(lienzo_palabra, capa_texto)
    if len(_WORD_SPRITE_CACHE) > 600:
        _WORD_SPRITE_CACHE.clear()
    _WORD_SPRITE_CACHE[clave] = sprite_final
    return sprite_final


def _clasificar_color_palabra(
    palabra_limpia: str,
    texto_original: str,
    forzar_destaque: bool,
    verdes: Set[str],
    rojas: Set[str],
    cianes: Set[str],
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Devuelve (color_relleno_rgb, color_glow_neon_rgb) para la palabra activa.
    """
    if palabra_limpia in verdes:
        # Verde Esmeralda Luminoso
        return (65, 255, 120), (0, 240, 85)
    if palabra_limpia in rojas:
        # Rojo / Magenta Neón Intenso
        return (255, 72, 88), (255, 15, 55)
    if palabra_limpia in cianes or "?" in texto_original or "¿" in texto_original or palabra_limpia.isdigit():
        # Cian Eléctrico Luminoso
        return (75, 242, 255), (0, 185, 255)
    if forzar_destaque:
        # Dorado Solar Brillante
        return (255, 248, 90), (255, 165, 0)
    # Amarillo Ciber / Dorado Luminoso por defecto para la palabra activa
    return (255, 238, 25), (255, 175, 0)


def _agrupar_palabras_subtitulos(palabras: List[PalabraSubtitulo]) -> List[List[Tuple[int, PalabraSubtitulo]]]:
    """
    Agrupa las palabras en bloques de 2 a 3 palabras (o 1 si es muy larga)
    para que nunca se desborden del ancho de 1080px y mantengan un ritmo rápido.
    """
    grupos: List[List[Tuple[int, PalabraSubtitulo]]] = []
    grupo_actual: List[Tuple[int, PalabraSubtitulo]] = []
    chars_actual = 0

    for idx, p in enumerate(palabras):
        largo = len(p.texto)
        max_palabras = 2 if largo >= 9 or any(len(x[1].texto) >= 9 for x in grupo_actual) else 3
        if grupo_actual and (len(grupo_actual) >= max_palabras or chars_actual + largo > 18):
            grupos.append(grupo_actual)
            grupo_actual = []
            chars_actual = 0

        grupo_actual.append((idx, p))
        chars_actual += largo + 1

        if p.texto.endswith(("!", "?", ".", ":", ";")) and len(grupo_actual) >= 1:
            grupos.append(grupo_actual)
            grupo_actual = []
            chars_actual = 0

    if grupo_actual:
        grupos.append(grupo_actual)
    return grupos


_BACKDROP_PILL_CACHE: Dict[Tuple[int, int], Image.Image] = {}


def _obtener_backdrop_subtitulo(ancho_bloque: int, alto_bloque: int = 160) -> Image.Image:
    w_q = min(WIDTH, max(320, ((ancho_bloque + 140) // 40) * 40))
    clave = (w_q, alto_bloque)
    if clave in _BACKDROP_PILL_CACHE:
        return _BACKDROP_PILL_CACHE[clave]
    img = Image.new("RGBA", (w_q, alto_bloque), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [28, 28, w_q - 28, alto_bloque - 28],
        radius=50,
        fill=(4, 6, 14, 118),
    )
    img = img.filter(ImageFilter.GaussianBlur(radius=20))
    _BACKDROP_PILL_CACHE[clave] = img
    return img


def renderizar_subtitulos_luminosos(
    lienzo: Image.Image,
    palabras: List[PalabraSubtitulo],
    t_actual: float,
    nivel_voz_rms: float = 0.0,
    y_centro: int = 1340,
    palabras_verdes_extra: Optional[Set[str]] = None,
    palabras_rojas_extra: Optional[Set[str]] = None,
    palabras_cian_extra: Optional[Set[str]] = None,
) -> None:
    if not palabras:
        return
    if t_actual < (palabras[0].inicio_seg - 0.06) or t_actual > (palabras[-1].fin_seg + 0.20):
        return

    idx_activa = 0
    for i, p in enumerate(palabras):
        if p.inicio_seg <= t_actual <= p.fin_seg:
            idx_activa = i
            break
        if t_actual > p.fin_seg:
            idx_activa = i

    grupos = _agrupar_palabras_subtitulos(palabras)
    grupo_mostrar = grupos[0]
    for g in grupos:
        indices_g = [item[0] for item in g]
        if idx_activa in indices_g:
            grupo_mostrar = g
            break

    verdes = PALABRAS_VERDES_BASE | (palabras_verdes_extra or set())
    rojas = PALABRAS_ROJAS_BASE | (palabras_rojas_extra or set())
    cianes = PALABRAS_CIAN_BASE | (palabras_cian_extra or set())

    tam_base_activa = 86
    tam_base_inactiva = 70
    espaciado_base = 20

    sprites_info = []
    for idx_global, p in grupo_mostrar:
        es_activa = (idx_global == idx_activa)
        txt_up = p.texto.upper().replace("*", "")
        limpia = re.sub(r"[^A-ZÁÉÍÓÚÜÑ0-9]", "", txt_up)

        if es_activa:
            color_fill, color_glow = _clasificar_color_palabra(
                limpia, txt_up, p.forzar_destaque, verdes, rojas, cianes
            )
            sprite_base = _obtener_sprite_palabra_luminosa(
                txt_up, tam_base_activa, color_fill, color_glow, True
            )
            edad = max(0.0, t_actual - p.inicio_seg)
            # Rebote elástico + pulso reactivo a la energía de la voz
            pulso_voz = min(0.09, nivel_voz_rms * 0.45)
            factor_pop = 1.0 + 0.18 * math.exp(-edad * 13.0) * math.cos(edad * 16.0) + pulso_voz
            pad_sprite = 58
        else:
            # Palabras acompañantes en blanco brillante con sutil aura azul hielo
            sprite_base = _obtener_sprite_palabra_luminosa(
                txt_up, tam_base_inactiva, (255, 255, 255), (120, 195, 255), False
            )
            factor_pop = 1.0
            pad_sprite = 42

        ancho_logico = max(20, sprite_base.width - pad_sprite * 2)
        sprites_info.append((idx_global, p, sprite_base, factor_pop, ancho_logico, pad_sprite, es_activa))

    ancho_total_logico = (
        sum(int(round(x[4] * x[3])) for x in sprites_info)
        + espaciado_base * max(0, len(sprites_info) - 1)
    )

    # Auto-ajuste para que jamás se corte una palabra en los bordes de los 1080px
    max_ancho_permitido = WIDTH - 84
    escala_ajuste = min(1.0, max_ancho_permitido / float(max(1, ancho_total_logico)))

    espaciado_final = int(round(espaciado_base * escala_ajuste))
    anchos_finales = [int(round(x[4] * x[3] * escala_ajuste)) for x in sprites_info]
    ancho_grupo_final = sum(anchos_finales) + espaciado_final * max(0, len(anchos_finales) - 1)

    # Fondo suave semitransparente detrás del subtítulo para contraste total
    backdrop = _obtener_backdrop_subtitulo(ancho_grupo_final, 165)
    bx = (WIDTH - backdrop.width) // 2
    by = y_centro - backdrop.height // 2
    lienzo.alpha_composite(backdrop, dest=(max(0, bx), max(0, min(HEIGHT - backdrop.height, by))))

    x_cursor = (WIDTH - ancho_grupo_final) // 2

    for (idx_global, p, sprite_base, factor_pop, ancho_logico, pad_sprite, es_activa), ancho_f in zip(
        sprites_info, anchos_finales
    ):
        escala_total = factor_pop * escala_ajuste
        if abs(escala_total - 1.0) > 0.015:
            nw = max(16, int(round(sprite_base.width * escala_total)))
            nh = max(16, int(round(sprite_base.height * escala_total)))
            sprite_render = sprite_base.resize((nw, nh), Image.Resampling.LANCZOS)
        else:
            sprite_render = sprite_base

        if es_activa:
            # Ligera inclinación dinámica en la primera fracción de segundo de la palabra activa
            edad = max(0.0, t_actual - p.inicio_seg)
            signo_ang = 1.0 if (idx_global % 2 == 0) else -1.0
            angulo_pop = signo_ang * 2.8 * math.exp(-edad * 10.0)
            if abs(angulo_pop) > 0.35:
                sprite_render = sprite_render.rotate(angulo_pop, resample=Image.Resampling.BICUBIC, expand=True)

        cx_palabra = x_cursor + ancho_f // 2
        cy_palabra = (y_centro - 10) if es_activa else y_centro

        dest_x = cx_palabra - sprite_render.width // 2
        dest_y = cy_palabra - sprite_render.height // 2
        dest_x = max(-30, min(WIDTH - sprite_render.width + 30, dest_x))
        dest_y = max(0, min(HEIGHT - sprite_render.height, dest_y))

        # Si dest_x es ligeramente negativo por el pad del resplandor, recortamos limpiamente
        if dest_x < 0:
            sprite_render = sprite_render.crop((-dest_x, 0, sprite_render.width, sprite_render.height))
            dest_x = 0
        if dest_x + sprite_render.width > WIDTH:
            sprite_render = sprite_render.crop((0, 0, WIDTH - dest_x, sprite_render.height))

        lienzo.alpha_composite(sprite_render, dest=(dest_x, dest_y))
        x_cursor += ancho_f + espaciado_final


# ==============================================================================
# 5. MOTOR DE VOZ NEURONAL Y ALINEACIÓN ACÚSTICA EXACTA
# ==============================================================================
def _peso_silabico_palabra(palabra: str) -> float:
    limpia = re.sub(r"[^a-záéíóúüñA-ZÁÉÍÓÚÜÑ0-9]", "", palabra)
    vocales = len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]+", limpia))
    peso = max(1.0, float(vocales) * 0.9 + len(limpia) * 0.12)
    if palabra.endswith((",", "...", ":", ";")):
        peso += 0.85
    elif palabra.endswith(("!", "?", ".")):
        peso += 1.10
    return peso


def detectar_limites_voz_real_wav(ruta_wav: Path) -> Tuple[float, float, float]:
    with wave.open(str(ruta_wav), "r") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        dur_total = n / float(sr)
        audio = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0

    if len(audio) == 0:
        return 0.0, dur_total, dur_total

    win = max(1, int(sr * 0.01))
    n_wins = len(audio) // win
    if n_wins < 2:
        return 0.0, dur_total, dur_total

    recorte = audio[: n_wins * win].reshape(n_wins, win)
    rms = np.sqrt(np.mean(recorte ** 2, axis=1))
    umbral = max(0.012, float(np.max(rms)) * 0.06)

    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        return 0.0, dur_total, dur_total

    ini_seg = max(0.0, float(activos[0]) * 0.01 - 0.02)
    fin_seg = min(dur_total, float(activos[-1] + 1) * 0.01 + 0.03)
    return ini_seg, fin_seg, dur_total


def alinear_palabras_con_onda_real(
    texto: str,
    ruta_wav: Path,
    palabras_edge: List[PalabraSubtitulo],
) -> List[PalabraSubtitulo]:
    ini_voz, fin_voz, dur_total = detectar_limites_voz_real_wav(ruta_wav)
    dur_hablada = max(0.25, fin_voz - ini_voz)

    if palabras_edge:
        primero = palabras_edge[0].inicio_seg
        ultimo = palabras_edge[-1].fin_seg
        rango_raw = max(0.1, ultimo - primero)
        escala = dur_hablada / rango_raw
        calibradas: List[PalabraSubtitulo] = []
        for p in palabras_edge:
            t0 = ini_voz + (p.inicio_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t1 = ini_voz + (p.fin_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t0 = max(0.0, t0)
            t1 = max(t0 + 0.08, min(dur_total, t1))
            if calibradas and t0 > calibradas[-1].fin_seg and (t0 - calibradas[-1].fin_seg) < 0.18:
                calibradas[-1].fin_seg = t0
            calibradas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
        return calibradas

    tokens = texto.split()
    if not tokens:
        return []
    pesos = [_peso_silabico_palabra(tok) for tok in tokens]
    suma_pesos = sum(pesos)
    cursor = ini_voz
    resultado: List[PalabraSubtitulo] = []
    for tok, peso in zip(tokens, pesos):
        dur_p = (peso / suma_pesos) * dur_hablada
        t0 = max(0.0, cursor + SUBTITLE_OFFSET_SEC)
        t1 = min(dur_total, cursor + dur_p + SUBTITLE_OFFSET_SEC)
        destaque = tok.startswith("*") and tok.endswith("*")
        tok_limpio = tok.strip("*")
        resultado.append(
            PalabraSubtitulo(
                texto=tok_limpio,
                inicio_seg=t0,
                fin_seg=max(t0 + 0.08, t1),
                forzar_destaque=destaque,
            )
        )
        cursor += dur_p
    return resultado


_REEMPLAZOS_FONETICOS_TTS = [
    (r"\*", ""),
    (r"\bPCs\b", "PC"),
    (r"\bpcs\b", "PC"),
    (r"\bRoblox\b", "Róblox"),
    (r"\broblox\b", "Róblox"),
    (r"\bRobux\b", "Róbux"),
    (r"\brobux\b", "Róbux"),
    (r"\bShorts\b", "Shórts"),
    (r"\bshorts\b", "shórts"),
    (r"\bShort\b", "Shórt"),
    (r"\bshort\b", "shórt"),
    (r"\bpros\b", "prós"),
    (r"\bPros\b", "Prós"),
    (r"\bPROS\b", "PRÓS"),
    (r"\bpro\b", "pró"),
    (r"\bPro\b", "Pró"),
    (r"\bPRO\b", "PRÓ"),
    (r"\bsuvs\b", "súbs"),
    (r"\bsubs\b", "súbs"),
]

_PALABRAS_HYPE_YOUTUBER = {
    "mira", "mirá", "miren", "increíble", "imposible", "locura", "pero", "ahora",
    "suscríbete", "suscribite", "comenta", "comentá", "like", "secreto", "nunca",
    "jamás", "épico", "épica", "ganar", "perder", "cuidado", "rápido", "estafa",
}


def _normalizar_fonetica_youtuber(texto: str) -> str:
    res = texto
    for patron, reemplazo in _REEMPLAZOS_FONETICOS_TTS:
        res = re.sub(patron, reemplazo, res)
    return res


def _dividir_clausulas_expresivas(texto: str) -> List[str]:
    partes = re.split(r"(?<=[!?.])\s+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


def _prosodia_dinamica_clausula(
    clausula: str,
    idx: int,
    total: int,
    palabras_por_seg_objetivo: Optional[float] = None,
) -> Tuple[str, str, str, float]:
    es_exclamacion = "!" in clausula or "¡" in clausula
    es_pregunta = "?" in clausula or "¿" in clausula
    palabras_low = set(re.findall(r"[a-záéíóúüñ]+", clausula.lower()))
    tiene_hype = bool(palabras_low & _PALABRAS_HYPE_YOUTUBER)
    pitch = EDGE_PITCH_DEFAULT

    # Adaptamos la velocidad base de síntesis al número de palabras que debe decir en este tramo real del video.
    # Las pausas entre oraciones se mantienen mínimas (narración de corrido, sin huecos de silencio).
    ajuste_vel = 0
    pausa_extra = 0.0
    if palabras_por_seg_objetivo is not None:
        if palabras_por_seg_objetivo < 2.6:
            ajuste_vel = -10
        elif palabras_por_seg_objetivo < 3.2:
            ajuste_vel = -5
        elif palabras_por_seg_objetivo > 3.9:
            # Si la IA escribió una línea larga para este bloque, aumentamos el ritmo proporcionalmente
            ajuste_vel = min(42, int(round((palabras_por_seg_objetivo - 3.5) * 12.0)))
            pausa_extra = -0.01

    if es_exclamacion:
        if idx == 0:
            r_num = max(0, 14 + ajuste_vel)
            return f"+{r_num}%", pitch, "+8%", max(0.015, 0.030 + pausa_extra)
        elif idx == total - 1:
            r_num = max(0, 15 + ajuste_vel)
            return f"+{r_num}%", pitch, "+10%", max(0.015, 0.030 + pausa_extra)
        else:
            r_num = max(0, 16 + ajuste_vel)
            return f"+{r_num}%", pitch, "+6%", max(0.015, 0.030 + pausa_extra)
    elif es_pregunta:
        r_num = max(0, 13 + ajuste_vel)
        return f"+{r_num}%", pitch, "+6%", max(0.015, 0.035 + pausa_extra)
    else:
        base_n = 13 if tiene_hype else 11
        r_num = max(0, base_n + ajuste_vel)
        return f"+{r_num}%", pitch, "+0%", max(0.015, 0.035 + pausa_extra)


def _recortar_silencio_clausula_pcm(
    pcm_float: np.ndarray,
    sr: int = 44100,
) -> Tuple[np.ndarray, float, float]:
    if len(pcm_float) == 0:
        return pcm_float, 0.0, 0.0
    win = max(1, int(sr * 0.005))
    n_wins = len(pcm_float) // win
    if n_wins < 2:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    rms = np.sqrt(np.mean(pcm_float[: n_wins * win].reshape(n_wins, win) ** 2, axis=1))
    umbral = max(0.007, float(np.max(rms)) * 0.03)
    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    pad_ini = int(sr * 0.016)
    pad_fin = int(sr * 0.024)
    i0 = max(0, int(activos[0]) * win - pad_ini)
    i1 = min(len(pcm_float), int(activos[-1] + 1) * win + pad_fin)
    recortado = pcm_float[i0:i1].copy()

    fade_len = min(int(sr * 0.008), len(recortado) // 4)
    if fade_len > 1:
        recortado[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        recortado[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    return recortado, i0 / float(sr), len(recortado) / float(sr)


def _construir_cadena_atempo(factor: float) -> str:
    """
    Construye filtros `atempo` encadenados para FFmpeg manteniendo el tono natural de la voz.
    """
    f = float(np.clip(factor, 0.55, 3.2))
    if abs(f - 1.0) <= 0.012:
        return ""
    partes: List[str] = []
    while f > 2.0:
        partes.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        partes.append("atempo=0.5")
        f /= 0.5
    partes.append(f"atempo={f:.4f}")
    return ",".join(partes) + ","


def masterizar_voz_estudio_ffmpeg(
    ruta_entrada: Path,
    ruta_wav_salida: Path,
    factor_atempo: float = 1.0,
) -> None:
    prefijo_tempo = _construir_cadena_atempo(factor_atempo)
    filtro_audio = (
        f"{prefijo_tempo}"
        "highpass=f=80,"
        "equalizer=f=135:width_type=o:width=1.1:g=2.4,"
        "equalizer=f=320:width_type=o:width=1.2:g=-1.2,"
        "equalizer=f=3150:width_type=o:width=1.3:g=-2.2,"
        "equalizer=f=5200:width_type=o:width=1.5:g=1.6,"
        "treble=g=2.0:f=8200,"
        "acompressor=threshold=-19dB:ratio=2.5:attack=10:release=110:makeup=5.2dB,"
        "alimiter=limit=0.98"
    )
    res = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(ruta_entrada),
            "-af", filtro_audio,
            "-ar", "44100", "-ac", "1",
            str(ruta_wav_salida),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if res.returncode != 0 or not ruta_wav_salida.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(ruta_entrada), "-ar", "44100", "-ac", "1", str(ruta_wav_salida)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def intentar_voz_elevenlabs(texto: str, ruta_mp3: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = json.dumps({
        "text": _normalizar_fonetica_youtuber(texto),
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.32,
            "similarity_boost": 0.82,
            "style": 0.68,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            datos = resp.read()
            if len(datos) > 1000:
                ruta_mp3.write_bytes(datos)
                return True
    except Exception:
        pass
    return False


async def generar_voz_y_timestamps_segmento(
    texto: str,
    ruta_audio_salida: Path,
    voz_edge: str = EDGE_VOICE_DEFAULT,
    dur_objetivo_seg: Optional[float] = None,
) -> Tuple[float, List[PalabraSubtitulo], float, float]:
    palabras_raw: List[PalabraSubtitulo] = []
    genero_audio = False
    ruta_wav = ruta_audio_salida.with_suffix(".wav")
    if ruta_audio_salida.exists():
        ruta_audio_salida.unlink()
    if ruta_wav.exists():
        ruta_wav.unlink()

    if ELEVENLABS_API_KEY:
        genero_audio = intentar_voz_elevenlabs(texto, ruta_audio_salida)
        if genero_audio:
            masterizar_voz_estudio_ffmpeg(ruta_audio_salida, ruta_wav)

    if not genero_audio and HAS_EDGE_TTS:
        try:
            clausulas_orig = _dividir_clausulas_expresivas(texto)
            if not clausulas_orig:
                clausulas_orig = [texto.strip()]

            total_palabras_seg = max(1, len(texto.split()))
            pps_obj = (total_palabras_seg / dur_objetivo_seg) if (dur_objetivo_seg and dur_objetivo_seg > 0.5) else None

            sr = 44100
            bloques_pcm: List[np.ndarray] = []
            cursor_seg = 0.0

            for c_idx, cl_orig in enumerate(clausulas_orig):
                cl_tts = _normalizar_fonetica_youtuber(cl_orig)
                rate_c, pitch_c, vol_c, pausa_post = _prosodia_dinamica_clausula(
                    cl_orig, c_idx, len(clausulas_orig), palabras_por_seg_objetivo=pps_obj
                )
                tmp_mp3 = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.mp3"
                tmp_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.wav"
                palabras_clausula: List[PalabraSubtitulo] = []

                # Nota crítica: En edge_tts >= 7.3 con voces Multilingual (como GiuseppeMultilingualNeural),
                # pasar un rate != "+0%" en SSML junto con boundary="WordBoundary" hace que el servidor de
                # Microsoft cierre el stream con NoAudioReceived (0 bytes). Por eso sintetizamos siempre a
                # rate="+0%" en Edge-TTS y aplicamos toda la aceleración exacta con el filtro `atempo` de
                # FFmpeg en `masterizar_voz_estudio_ffmpeg`, logrando 100% de fiabilidad sin perder ninguna frase.
                intentos_tts = [
                    (voz_edge, "+0%", pitch_c, vol_c, True),
                    (voz_edge, "+0%", "+0Hz", "+0%", False),
                    ("es-AR-TomasNeural", "+0%", "+0Hz", "+0%", True),
                    ("es-MX-JorgeNeural", "+0%", "+0Hz", "+0%", False),
                ]
                for v_try, r_try, p_try, vol_try, usar_wb in intentos_tts:
                    palabras_clausula = []
                    if tmp_mp3.exists():
                        try:
                            tmp_mp3.unlink()
                        except OSError:
                            pass
                    try:
                        if usar_wb:
                            communicate = edge_tts.Communicate(
                                cl_tts,
                                v_try,
                                rate=r_try,
                                pitch=p_try,
                                volume=vol_try,
                                boundary="WordBoundary",
                            )
                        else:
                            communicate = edge_tts.Communicate(
                                cl_tts,
                                v_try,
                                rate=r_try,
                                pitch=p_try,
                                volume=vol_try,
                            )
                        with open(tmp_mp3, "wb") as audio_file:
                            async for chunk in communicate.stream():
                                ctype = chunk.get("type")
                                if ctype == "audio":
                                    audio_file.write(chunk["data"])
                                elif ctype == "WordBoundary":
                                    ini = chunk["offset"] / 10_000_000.0
                                    dur = chunk["duration"] / 10_000_000.0
                                    palabras_clausula.append(
                                        PalabraSubtitulo(
                                            texto=chunk["text"],
                                            inicio_seg=ini,
                                            fin_seg=ini + max(dur, 0.08),
                                        )
                                    )
                        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 200:
                            break
                    except Exception as err_clause:
                        print(f"[!] Reintentando cláusula TTS ({v_try}): {err_clause}")
                        continue

                if tmp_mp3.exists() and tmp_mp3.stat().st_size > 0:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", str(sr), "-ac", "1", str(tmp_wav)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                if tmp_wav.exists() and tmp_wav.stat().st_size > 0:
                    with wave.open(str(tmp_wav), "r") as wf_c:
                        pcm_c = (
                            np.frombuffer(wf_c.readframes(wf_c.getnframes()), dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )
                    pcm_rec, offset_rec, dur_rec = _recortar_silencio_clausula_pcm(pcm_c, sr)

                    if "!" in cl_orig or "¡" in cl_orig:
                        progreso_c = np.linspace(0.0, 1.0, len(pcm_rec), dtype=np.float32)
                        env_punch = 1.0 + 0.09 * np.exp(-progreso_c * 3.2) + 0.05 * np.sin(progreso_c * math.pi)
                        pcm_rec = pcm_rec * env_punch

                    tokens_orig = cl_orig.split()
                    if palabras_clausula:
                        t_first = palabras_clausula[0].inicio_seg
                        t_last = palabras_clausula[-1].fin_seg
                        span_raw = max(0.08, t_last - t_first)
                        escala_c = max(0.10, dur_rec - 0.02) / span_raw
                        for w_i, p_w in enumerate(palabras_clausula):
                            tok_o = tokens_orig[w_i] if w_i < len(tokens_orig) else p_w.texto
                            destaque = tok_o.startswith("*") and tok_o.endswith("*")
                            txt_mostrar = tok_o.strip("*")
                            t0 = cursor_seg + max(0.0, (p_w.inicio_seg - t_first) * escala_c)
                            t1 = cursor_seg + min(dur_rec, max(0.08, (p_w.fin_seg - t_first) * escala_c))
                            palabras_raw.append(
                                PalabraSubtitulo(
                                    texto=txt_mostrar,
                                    inicio_seg=t0,
                                    fin_seg=max(t0 + 0.07, t1),
                                    forzar_destaque=destaque,
                                )
                            )

                    bloques_pcm.append(pcm_rec)
                    cursor_seg += dur_rec

                    if c_idx < len(clausulas_orig) - 1:
                        bloques_pcm.append(np.zeros(int(sr * pausa_post), dtype=np.float32))
                        cursor_seg += pausa_post

                for f_tmp in (tmp_mp3, tmp_wav):
                    if f_tmp.exists():
                        try:
                            f_tmp.unlink()
                        except OSError:
                            pass

            if bloques_pcm:
                audio_crudo = np.clip(np.concatenate(bloques_pcm), -0.98, 0.98)
                dur_cruda = len(audio_crudo) / float(sr)

                # Ajuste exacto de tempo (sin cambiar el tono) para que la voz LLENE su tramo real de video
                # de corrido (sin huecos de silencio al final) y nunca lo exceda.
                factor_atempo = 1.0
                if dur_objetivo_seg and dur_objetivo_seg > 0.5 and dur_cruda > 0.15:
                    dur_ideal_voz = max(0.35, dur_objetivo_seg - 0.06)
                    factor_atempo = float(np.clip(dur_cruda / dur_ideal_voz, 0.80, 2.4))

                if abs(factor_atempo - 1.0) > 0.012 and palabras_raw:
                    for p_w in palabras_raw:
                        p_w.inicio_seg /= factor_atempo
                        p_w.fin_seg /= factor_atempo

                ruta_crudo_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_raw.wav"
                with wave.open(str(ruta_crudo_wav), "w") as wf_raw:
                    wf_raw.setnchannels(1)
                    wf_raw.setsampwidth(2)
                    wf_raw.setframerate(sr)
                    wf_raw.writeframes((audio_crudo * 32767).astype(np.int16).tobytes())
                masterizar_voz_estudio_ffmpeg(ruta_crudo_wav, ruta_wav, factor_atempo=factor_atempo)
                if ruta_crudo_wav.exists():
                    try:
                        ruta_crudo_wav.unlink()
                    except OSError:
                        pass
                genero_audio = ruta_wav.exists() and ruta_wav.stat().st_size > 0
        except Exception as e:
            print(f"[!] Error en Edge-TTS: {e}")

    if not ruta_wav.exists() or ruta_wav.stat().st_size == 0:
        # Silencio limpio de emergencia (NUNCA generar tonos/zumbidos graves de 195Hz)
        tokens = texto.split()
        dur_estimada = dur_objetivo_seg if (dur_objetivo_seg and dur_objetivo_seg > 0.5) else max(1.8, len(tokens) * 0.28)
        sr = 44100
        pcm = np.zeros(int(sr * dur_estimada), dtype=np.int16)
        with wave.open(str(ruta_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())

    with wave.open(str(ruta_wav), "r") as wf:
        duracion_real = wf.getnframes() / float(wf.getframerate())

    ini_voz, fin_voz, _ = detectar_limites_voz_real_wav(ruta_wav)
    if palabras_raw and not ELEVENLABS_API_KEY:
        palabras_alineadas: List[PalabraSubtitulo] = []
        for p in palabras_raw:
            t0 = max(0.0, p.inicio_seg + SUBTITLE_OFFSET_SEC)
            t1 = min(duracion_real, max(t0 + 0.07, p.fin_seg + SUBTITLE_OFFSET_SEC))
            if palabras_alineadas and t0 > palabras_alineadas[-1].fin_seg and (t0 - palabras_alineadas[-1].fin_seg) < 0.16:
                palabras_alineadas[-1].fin_seg = t0
            palabras_alineadas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
    else:
        palabras_alineadas = alinear_palabras_con_onda_real(texto, ruta_wav, palabras_raw)

    return duracion_real, palabras_alineadas, ini_voz, fin_voz


# ==============================================================================
# 6. SEGUIMIENTO INTELIGENTE DE OBJETIVOS (OPTICAL FLOW + SALIENCIA EN MOVIMIENTO)
# ==============================================================================
class RastreadorObjetivosVideo:
    """
    Motor de visión artificial (OpenCV) que permite que las flechas rojas (flecha.png)
    y los círculos rojos (circulo_rojo.png) localicen y sigan suavemente al objetivo
    real dentro del segmento de video:
      1) Adquisición inteligente del objetivo en movimiento/saliencia dentro de la zona
         solicitada ('izquierda', 'derecha', 'centro', 'arriba', 'abajo', 'auto' o 'X,Y').
      2) Seguimiento cuadro a cuadro con Flujo Óptico Piramidal de Lucas-Kanade
         (cv2.calcOpticalFlowPyrLK) con verificación forward-backward y respaldo
         por Template Matching ante desenfoques rápidos.
      3) Suavizado Gaussiano bidireccional sin retardo (zero-lag) a 60 FPS.
    """

    ESC_TRACK = 3.0
    W_TR = int(WIDTH // ESC_TRACK)   # 360
    H_TR = int(HEIGHT // ESC_TRACK)  # 640

    ZONAS_NOMINALES: Dict[str, Tuple[float, float, float]] = {
        # nombre_zona: (x_norm 0..1, y_norm 0..1, radio_busqueda_px_en_360x640)
        "centro": (0.50, 0.45, 78.0),
        "izquierda": (0.28, 0.45, 72.0),
        "derecha": (0.72, 0.45, 72.0),
        "arriba": (0.50, 0.26, 72.0),
        "abajo": (0.50, 0.62, 72.0),
        "arriba_izq": (0.28, 0.27, 68.0),
        "arriba_der": (0.72, 0.27, 68.0),
        "abajo_izq": (0.28, 0.60, 68.0),
        "abajo_der": (0.72, 0.60, 68.0),
        "auto": (0.50, 0.45, 145.0),
    }

    @classmethod
    def _parsear_punto_base(cls, spec: str) -> Tuple[float, float, float, bool]:
        """
        Devuelve (x_360, y_640, radio_busqueda_360, es_coordenada_exacta).
        Si viene una coordenada porcentual `X,Y` de la IA (ej. `45,52`), la usa como centro
        de búsqueda con un radio local de 42px en 360x640 para engancharse al contorno real
        del objeto más cercano a ese punto exacto.
        """
        s = _quitar_acentos(spec.strip().lower())
        if "," in s:
            try:
                px_s, py_s = s.split(",", 1)
                px = float(px_s.strip().replace("%", ""))
                py = float(py_s.strip().replace("%", ""))
                if px <= 100.0 and py <= 100.0:
                    x_tr = (px / 100.0) * cls.W_TR
                    y_tr = (py / 100.0) * cls.H_TR
                else:
                    x_tr = px / cls.ESC_TRACK
                    y_tr = py / cls.ESC_TRACK
                x_tr = float(np.clip(x_tr, 32.0, cls.W_TR - 32.0))
                y_tr = float(np.clip(y_tr, 42.0, cls.H_TR - 135.0))
                return x_tr, y_tr, 42.0, True
            except ValueError:
                pass

        nx, ny, rad = cls.ZONAS_NOMINALES.get(s, cls.ZONAS_NOMINALES["centro"])
        return nx * cls.W_TR, ny * cls.H_TR, rad, False

    @classmethod
    def _adquirir_objetivo_saliente(
        cls,
        grises_iniciales: List[np.ndarray],
        rgb_inicial: Optional[np.ndarray],
        x_nom: float,
        y_nom: float,
        radio_busq: float,
        es_exacta: bool,
    ) -> Tuple[float, float]:
        if not grises_iniciales:
            return x_nom, y_nom

        g0 = grises_iniciales[0].astype(np.float32)
        h, w = g0.shape

        # 1. Mapa de energía de movimiento en los primeros cuadros del segmento
        mov_acum = np.zeros((h, w), dtype=np.float32)
        for i in range(1, len(grises_iniciales)):
            diff = cv2.absdiff(grises_iniciales[i], grises_iniciales[i - 1]).astype(np.float32)
            mov_acum += diff
        if len(grises_iniciales) > 1:
            mov_acum /= float(len(grises_iniciales) - 1)
        mov_norm = mov_acum / (float(np.max(mov_acum)) + 1e-5)

        # 2. Mapa de saturación de color + contraste de objetos (para detectar sujetos/objetos reales)
        if rgb_inicial is not None:
            hsv = cv2.cvtColor(rgb_inicial, cv2.COLOR_RGB2HSV).astype(np.float32)
            sat_norm = hsv[:, :, 1] / 255.0
        else:
            sat_norm = np.zeros((h, w), dtype=np.float32)

        gx = cv2.Sobel(g0, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g0, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.Sobel(g0, cv2.CV_32F, 1, 1, ksize=3)
        grad_mag = cv2.magnitude(gx, gy)
        grad_norm = grad_mag / (float(np.max(grad_mag)) + 1e-5)

        saliencia = cv2.GaussianBlur(mov_norm * 2.10 + sat_norm * 1.15 + grad_norm * 0.55, (17, 17), 0)

        # 3. Ventana Gaussiana centrada en la coordenada o zona pedida
        yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
        peso_zona = np.exp(-(((xx - x_nom) ** 2 + (yy - y_nom) ** 2) / (2.0 * (radio_busq ** 2))))

        limite_y_inf = int(h * 0.69) if y_nom < h * 0.56 else int(h * 0.77)
        mascara_segura = np.zeros((h, w), dtype=np.float32)
        mascara_segura[38:limite_y_inf, 30 : w - 30] = 1.0

        mapa_final = saliencia * peso_zona * mascara_segura
        max_val = float(np.max(mapa_final))
        if max_val < 1e-4:
            return x_nom, y_nom

        umbral = max_val * 0.82
        ys, xs = np.where(mapa_final >= umbral)
        if len(xs) == 0:
            return x_nom, y_nom
        pesos = mapa_final[ys, xs]
        cx_sal = float(np.sum(xs * pesos) / np.sum(pesos))
        cy_sal = float(np.sum(ys * pesos) / np.sum(pesos))

        # Si la IA dio coordenada exacta X,Y, refinamos suavemente hacia el pico de saliencia local;
        # si dio una zona ("izquierda", "derecha", "centro"), vamos directo al objeto más saliente (85%).
        peso_sal = 0.55 if es_exacta else 0.86
        tx = peso_sal * cx_sal + (1.0 - peso_sal) * x_nom
        ty = peso_sal * cy_sal + (1.0 - peso_sal) * y_nom
        return float(np.clip(tx, 36.0, w - 36.0)), float(np.clip(ty, 44.0, limite_y_inf))

    @classmethod
    def _extraer_puntos_locales(cls, gray: np.ndarray, cx: float, cy: float, radio: int = 44) -> Optional[np.ndarray]:
        h, w = gray.shape
        x0 = max(8, int(round(cx - radio)))
        x1 = min(w - 8, int(round(cx + radio)))
        y0 = max(8, int(round(cy - radio)))
        y1 = min(h - 8, int(round(cy + radio)))
        if x1 - x0 < 12 or y1 - y0 < 12:
            return None

        mask = np.zeros_like(gray)
        mask[y0:y1, x0:x1] = 255
        pts = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=28,
            qualityLevel=0.04,
            minDistance=5,
            mask=mask,
            blockSize=5,
        )
        return pts

    @classmethod
    def _suavizar_serie_1d(cls, valores: np.ndarray, sigma: float = 4.2) -> np.ndarray:
        if len(valores) < 5:
            return valores
        rad = max(2, int(math.ceil(sigma * 2.5)))
        k_x = np.arange(-rad, rad + 1, dtype=np.float32)
        kernel = np.exp(-(k_x ** 2) / (2.0 * sigma * sigma))
        kernel /= np.sum(kernel)
        pad_v = np.pad(valores, (rad, rad), mode="edge")
        return np.convolve(pad_v, kernel, mode="valid")

    @classmethod
    def calcular_trayectoria(
        cls,
        frames_rgb: List[np.ndarray],
        especificacion: Optional[str],
    ) -> List[Tuple[float, float]]:
        """
        Devuelve una lista de coordenadas [(vx, vy), ...] en espacio 1080x1920
        para cada fotograma del segmento.
        """
        n_frames = len(frames_rgb)
        if n_frames == 0 or not especificacion:
            return [(WIDTH / 2.0, HEIGHT * 0.44)] * max(1, n_frames)

        spec_clean = _quitar_acentos(especificacion.strip().lower())

        # Submuestreo cada 2 cuadros a resolución 360x640 para máxima velocidad y precisión
        paso = 2 if n_frames > 12 else 1
        indices_muestra = list(range(0, n_frames, paso))
        if indices_muestra[-1] != n_frames - 1:
            indices_muestra.append(n_frames - 1)

        grises: List[np.ndarray] = []
        rgbs_peq: List[np.ndarray] = []
        for idx in indices_muestra:
            peq = cv2.resize(frames_rgb[idx], (cls.W_TR, cls.H_TR), interpolation=cv2.INTER_AREA)
            rgbs_peq.append(peq)
            grises.append(cv2.cvtColor(peq, cv2.COLOR_RGB2GRAY))

        # Caso A: Trayectoria explícita "inicio->fin" (ej. "izquierda->derecha" o "25,50->75,50")
        if "->" in spec_clean:
            p_ini_str, p_fin_str = spec_clean.split("->", 1)
            x0_tr, y0_tr, _, _ = cls._parsear_punto_base(p_ini_str)
            x1_tr, y1_tr, _, _ = cls._parsear_punto_base(p_fin_str)
            xs_full = np.zeros(n_frames, dtype=np.float32)
            ys_full = np.zeros(n_frames, dtype=np.float32)
            for i in range(n_frames):
                u = i / float(max(1, n_frames - 1))
                # Curva ease-in-out suave
                u_s = u * u * (3.0 - 2.0 * u)
                xs_full[i] = (x0_tr + (x1_tr - x0_tr) * u_s) * cls.ESC_TRACK
                ys_full[i] = (y0_tr + (y1_tr - y0_tr) * u_s) * cls.ESC_TRACK
            return list(zip(xs_full.tolist(), ys_full.tolist()))

        # Caso B: Seguimiento real de objetivo con Optical Flow + Saliencia
        x_nom, y_nom, radio_busq, es_exacta = cls._parsear_punto_base(spec_clean)
        tx, ty = cls._adquirir_objetivo_saliente(
            grises[: min(8, len(grises))], rgbs_peq[0], x_nom, y_nom, radio_busq, es_exacta
        )

        limite_y_inf = float(cls.H_TR * 0.68) if y_nom < cls.H_TR * 0.54 else float(cls.H_TR * 0.76)
        pts_activos = cls._extraer_puntos_locales(grises[0], tx, ty, radio=48)

        xs_m: List[float] = [tx]
        ys_m: List[float] = [ty]

        lk_params = dict(
            winSize=(23, 23),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03),
        )

        for k in range(1, len(grises)):
            g_prev = grises[k - 1]
            g_curr = grises[k]

            # Detectar si hubo un corte brusco de escena dentro del segmento
            diff_medio = float(np.mean(cv2.absdiff(g_curr, g_prev)))
            if diff_medio > 26.0:
                tx, ty = cls._adquirir_objetivo_saliente(
                    grises[k : min(len(grises), k + 5)], rgbs_peq[k], x_nom, y_nom, radio_busq, es_exacta
                )
                pts_activos = cls._extraer_puntos_locales(g_curr, tx, ty, radio=48)
                xs_m.append(tx)
                ys_m.append(ty)
                continue

            if pts_activos is None or len(pts_activos) < 6:
                pts_activos = cls._extraer_puntos_locales(g_prev, tx, ty, radio=48)

            desplazado = False
            if pts_activos is not None and len(pts_activos) >= 4:
                pts_next, st_f, _ = cv2.calcOpticalFlowPyrLK(g_prev, g_curr, pts_activos, None, **lk_params)
                if pts_next is not None and st_f is not None:
                    pts_back, st_b, _ = cv2.calcOpticalFlowPyrLK(g_curr, g_prev, pts_next, None, **lk_params)
                    if pts_back is not None and st_b is not None:
                        err_fb = np.linalg.norm(pts_activos - pts_back, axis=2).reshape(-1)
                        validos = (st_f.reshape(-1) == 1) & (st_b.reshape(-1) == 1) & (err_fb < 2.4)
                        if np.count_nonzero(validos) >= 3:
                            p0_v = pts_activos[validos].reshape(-1, 2)
                            p1_v = pts_next[validos].reshape(-1, 2)
                            deltas = p1_v - p0_v
                            mags = np.linalg.norm(deltas, axis=1)
                            buenos = mags < 30.0
                            if np.count_nonzero(buenos) >= 3:
                                dx = float(np.median(deltas[buenos, 0]))
                                dy = float(np.median(deltas[buenos, 1]))
                                # Seguimiento fiel del objetivo en movimiento con mínimo resorte de seguridad
                                tx = tx + dx * 0.96 + (x_nom - tx) * 0.015
                                ty = ty + dy * 0.96 + (y_nom - ty) * 0.015
                                pts_activos = p1_v[buenos].reshape(-1, 1, 2)
                                desplazado = True

            # Respaldo por Template Matching si hay pocos vértices pero existe textura local
            if not desplazado:
                r_tpl = 22
                r_search = 38
                x0_t = max(0, int(round(tx - r_tpl)))
                x1_t = min(cls.W_TR, int(round(tx + r_tpl)))
                y0_t = max(0, int(round(ty - r_tpl)))
                y1_t = min(cls.H_TR, int(round(ty + r_tpl)))

                x0_s = max(0, int(round(tx - r_search)))
                x1_s = min(cls.W_TR, int(round(tx + r_search)))
                y0_s = max(0, int(round(ty - r_search)))
                y1_s = min(cls.H_TR, int(round(ty + r_search)))

                tpl = g_prev[y0_t:y1_t, x0_t:x1_t]
                srch = g_curr[y0_s:y1_s, x0_s:x1_s]
                if tpl.shape[0] >= 12 and tpl.shape[1] >= 12 and srch.shape[0] > tpl.shape[0] and srch.shape[1] > tpl.shape[1]:
                    res_tm = cv2.matchTemplate(srch, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_v, _, max_loc = cv2.minMaxLoc(res_tm)
                    if max_v > 0.62:
                        nuevo_x = x0_s + max_loc[0] + tpl.shape[1] * 0.5
                        nuevo_y = y0_s + max_loc[1] + tpl.shape[0] * 0.5
                        tx = 0.75 * tx + 0.25 * nuevo_x
                        ty = 0.75 * ty + 0.25 * nuevo_y

            tx = float(np.clip(tx, 38.0, cls.W_TR - 38.0))
            ty = float(np.clip(ty, 46.0, limite_y_inf))
            xs_m.append(tx)
            ys_m.append(ty)

            if k % 4 == 0:
                nuevos = cls._extraer_puntos_locales(g_curr, tx, ty, radio=40)
                if nuevos is not None and len(nuevos) >= 6:
                    pts_activos = nuevos

        # Interpolar a todos los fotogramas de 60 FPS y aplicar suavizado Gaussiano sin retardo
        t_todos = np.arange(n_frames, dtype=np.float32)
        t_muestras = np.array(indices_muestra, dtype=np.float32)
        xs_interp = np.interp(t_todos, t_muestras, np.array(xs_m, dtype=np.float32)) * cls.ESC_TRACK
        ys_interp = np.interp(t_todos, t_muestras, np.array(ys_m, dtype=np.float32)) * cls.ESC_TRACK

        xs_suave = cls._suavizar_serie_1d(xs_interp, sigma=4.5)
        ys_suave = cls._suavizar_serie_1d(ys_interp, sigma=4.5)

        return list(zip(xs_suave.tolist(), ys_suave.tolist()))


# ==============================================================================
# 7. MOTOR DE ASSETS VISUALES (FLECHA, CÍRCULO ROJO, EMOJIS) Y EFECTOS DE CÁMARA
# ==============================================================================
class GestorEfectosYAssets:
    """
    Gestiona:
    - Emojis animados de `emojis/` con sombra y rebote elástico (evitando colisión con objetivos).
    - Flecha roja (`fotos/flecha.png`) y Círculo rojo (`fotos/circulo_rojo.png`) mejorados con
      resplandor neón, borde de contraste y seguimiento sincronizado de objetivos.
    - Efectos visuales de cámara y color sobre el video (`zoom_impacto`, `zoom_in`, `zoom_out`,
      `flash`, `temblor`, `alerta_roja`, `brillo_epico`, `blanco_negro`).
    """

    def __init__(self, emojis_dir: Path, fotos_dir: Path, duracion_callouts: float = DURACION_CALLOUTS_DEFAULT):
        self.emojis_cache: Dict[str, Image.Image] = {}
        self.flecha_base: Optional[Image.Image] = None
        self.circulo_base: Optional[Image.Image] = None
        self.vineta_roja_base: Image.Image = self._crear_vineta_color((255, 18, 35), max_alpha=150)
        self.vineta_oscura_base: Image.Image = self._crear_vineta_color((0, 0, 0), max_alpha=145)
        self.duracion_callouts: float = float(duracion_callouts)

        self._cargar_emojis(emojis_dir)
        self._cargar_flecha_y_circulo(fotos_dir, emojis_dir)

    @staticmethod
    def _crear_vineta_color(color_rgb: Tuple[int, int, int], max_alpha: int = 140) -> Image.Image:
        w_peq, h_peq = 270, 480
        yy, xx = np.meshgrid(
            np.linspace(-1.0, 1.0, h_peq, dtype=np.float32),
            np.linspace(-1.0, 1.0, w_peq, dtype=np.float32),
            indexing="ij",
        )
        dist = np.sqrt(xx ** 2 + (yy * 0.92) ** 2)
        alpha = np.clip((dist - 0.58) / 0.65, 0.0, 1.0) ** 1.6 * float(max_alpha)
        rgba = np.zeros((h_peq, w_peq, 4), dtype=np.uint8)
        rgba[:, :, 0] = color_rgb[0]
        rgba[:, :, 1] = color_rgb[1]
        rgba[:, :, 2] = color_rgb[2]
        rgba[:, :, 3] = alpha.astype(np.uint8)
        return Image.fromarray(rgba, mode="RGBA").resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)

    @staticmethod
    def _estilizar_asset_luminoso_rojo(img_orig: Image.Image, tam_lienzo: int = 420) -> Image.Image:
        """
        Realza `flecha.png` o `circulo_rojo.png` con un rojo vibrante, borde blanco/negro
        de alto contraste y resplandor neón rojo + sombra proyectada para que destaque
        sobre cualquier fondo de video.
        """
        img_resized = img_orig.resize((tam_lienzo, tam_lienzo), Image.Resampling.LANCZOS)
        np_im = np.array(img_resized, dtype=np.uint8)
        alpha = np_im[:, :, 3]

        # Asegurar rojo brillante e intenso en todos los píxeles opacos
        mascara = alpha > 20
        np_im[mascara, 0] = 255
        np_im[mascara, 1] = 26
        np_im[mascara, 2] = 36
        nucleo = Image.fromarray(np_im, mode="RGBA")

        # Crear borde blanco/negro y resplandor exterior rojo usando dilatación de máscara
        alpha_img = Image.fromarray(alpha, mode="L")
        borde_ext = alpha_img.filter(ImageFilter.MaxFilter(9))
        sombra_alpha = borde_ext.filter(ImageFilter.GaussianBlur(radius=9))
        glow_alpha = borde_ext.filter(ImageFilter.GaussianBlur(radius=14))

        lienzo = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 0))

        # 1. Sombra oscura desplazada
        capa_sombra = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 0))
        sombra_negra = Image.new("RGBA", (tam_lienzo, tam_lienzo), (0, 0, 0, 210))
        sombra_negra.putalpha(ImageChops.multiply(sombra_alpha, Image.new("L", (tam_lienzo, tam_lienzo), 195)))
        capa_sombra.paste(sombra_negra, (6, 8))
        lienzo = Image.alpha_composite(lienzo, capa_sombra)

        # 2. Resplandor Neón Rojo
        capa_glow = Image.new("RGBA", (tam_lienzo, tam_lienzo), (255, 20, 40, 0))
        capa_glow.putalpha(glow_alpha)
        lienzo = Image.alpha_composite(lienzo, capa_glow)

        # 3. Contorno blanco fino de alto contraste alrededor de la figura roja
        capa_borde = Image.new("RGBA", (tam_lienzo, tam_lienzo), (255, 245, 245, 0))
        capa_borde.putalpha(alpha_img.filter(ImageFilter.MaxFilter(5)))
        lienzo = Image.alpha_composite(lienzo, capa_borde)

        # 4. Núcleo rojo brillante encima
        lienzo = Image.alpha_composite(lienzo, nucleo)
        return lienzo

    @staticmethod
    def _estilizar_emoji_con_sombra(img_orig: Image.Image, tam_base: int = 240) -> Image.Image:
        pad = 24
        esc = tam_base - pad * 2
        nucleo = img_orig.resize((esc, esc), Image.Resampling.LANCZOS)
        lienzo = Image.new("RGBA", (tam_base, tam_base), (0, 0, 0, 0))
        alpha = nucleo.split()[3]
        sombra_a = alpha.filter(ImageFilter.GaussianBlur(radius=8))
        sombra = Image.new("RGBA", (esc, esc), (0, 0, 0, 0))
        sombra.putalpha(sombra_a.point(lambda p: int(p * 0.72)))
        lienzo.alpha_composite(sombra, dest=(pad + 5, pad + 8))
        lienzo.alpha_composite(nucleo, dest=(pad, pad))
        return lienzo

    def _cargar_emojis(self, emojis_dir: Path) -> None:
        if not emojis_dir.exists():
            return
        for ruta_png in sorted(emojis_dir.glob("*.png")):
            stem_norm = _quitar_acentos(ruta_png.stem.strip().lower())
            if stem_norm in ("flecha", "circulo_rojo", "circulo"):
                continue
            try:
                img = Image.open(ruta_png).convert("RGBA")
                img_est = self._estilizar_emoji_con_sombra(img, 240)
            except Exception:
                continue
            clave_corta = stem_norm[len("emoji_"):] if stem_norm.startswith("emoji_") else stem_norm
            self.emojis_cache[clave_corta] = img_est
            self.emojis_cache[stem_norm] = img_est

        nombres_unicos = sorted({k for k in self.emojis_cache if not k.startswith("emoji_")})
        print(f"[*] Emojis cargados ({len(nombres_unicos)}): {nombres_unicos}")

    def _cargar_flecha_y_circulo(self, fotos_dir: Path, emojis_dir: Path) -> None:
        rutas_flecha = [
            fotos_dir / "flecha.png",
            emojis_dir / "flecha.png",
        ]
        for rf in rutas_flecha:
            if rf.exists():
                try:
                    img_f = Image.open(rf).convert("RGBA")
                    self.flecha_base = self._estilizar_asset_luminoso_rojo(img_f, 480)
                    break
                except Exception:
                    pass

        rutas_circulo = [
            fotos_dir / "circulo_rojo.png",
            fotos_dir / "circulo.png",
            emojis_dir / "circulo_rojo.png",
        ]
        for rc in rutas_circulo:
            if rc.exists():
                try:
                    img_c = Image.open(rc).convert("RGBA")
                    self.circulo_base = self._estilizar_asset_luminoso_rojo(img_c, 580)
                    break
                except Exception:
                    pass

        print(
            f"[*] Assets de señalamiento listos -> Flecha Roja: {'Sí' if self.flecha_base else 'No'} | "
            f"Círculo Rojo: {'Sí' if self.circulo_base else 'No'}"
        )

    def aplicar_efecto_camara_y_transformar_puntos(
        self,
        frame_rgb: np.ndarray,
        efecto: str,
        t_seg: float,
        dur_seg: float,
        foco_video: Tuple[float, float],
        puntos_rastreados: List[Tuple[float, float]],
    ) -> Tuple[Image.Image, List[Tuple[float, float]]]:
        """
        Aplica el efecto visual elegido sobre `frame_rgb` (1080x1920) y transforma
        las coordenadas de los objetivos rastreados `(vx, vy) -> (screen_x, screen_y)`
        para que las flechas y círculos rojos permanezcan 100% clavados sobre el objeto
        incluso durante un zoom o sacudida de cámara.
        """
        progreso = min(1.0, max(0.0, t_seg / max(0.1, dur_seg)))
        fx, fy = foco_video

        zoom = 1.0
        shake_x, shake_y = 0.0, 0.0

        if efecto == "zoom_impacto":
            # Golpe de zoom rápido al inicio + leve sacudida de impacto
            pulso_ini = math.sin(min(1.0, t_seg / 0.26) * math.pi) if t_seg < 0.26 else 0.0
            zoom = 1.0 + 0.14 * pulso_ini + 0.08 * progreso
            if t_seg < 0.28:
                amort = math.exp(-t_seg * 12.0)
                shake_x = 16.0 * math.sin(t_seg * 68.0) * amort
                shake_y = 12.0 * math.cos(t_seg * 54.0) * amort
        elif efecto == "zoom_in":
            # Acercamiento cinematográfico suave hacia el objetivo
            curva = progreso * progreso * (3.0 - 2.0 * progreso)
            zoom = 1.0 + 0.19 * curva
        elif efecto == "zoom_out":
            curva = progreso * progreso * (3.0 - 2.0 * progreso)
            zoom = 1.19 - 0.19 * curva
        elif efecto == "temblor":
            zoom = 1.08 + 0.04 * math.sin(t_seg * 6.0)
            amort = math.exp(-t_seg * 2.2) if t_seg < 1.2 else 0.25
            shake_x = 22.0 * math.sin(t_seg * 58.0) * amort
            shake_y = 18.0 * math.cos(t_seg * 47.0) * amort
        elif efecto == "alerta_roja":
            zoom = 1.04 + 0.04 * abs(math.sin(t_seg * 4.5))
        elif efecto == "brillo_epico":
            zoom = 1.0 + 0.10 * progreso
        elif efecto == "blanco_negro":
            zoom = 1.02 + 0.08 * progreso
        else:
            # Movimiento orgánico sutil para que el video nunca quede estático
            zoom = 1.0 + 0.05 * progreso

        # Calcular ventana de recorte [x0, y0, crop_w, crop_h] centrada hacia el objetivo
        crop_w = WIDTH / zoom
        crop_h = HEIGHT / zoom

        # Acercar el centro de cámara suavemente hacia el objetivo (foco_video)
        cx_cam = 0.55 * (WIDTH / 2.0) + 0.45 * fx + shake_x
        cy_cam = 0.55 * (HEIGHT / 2.0) + 0.45 * fy + shake_y

        x0 = float(np.clip(cx_cam - crop_w / 2.0, 0.0, WIDTH - crop_w))
        y0 = float(np.clip(cy_cam - crop_h / 2.0, 0.0, HEIGHT - crop_h))

        ix0 = int(round(x0))
        iy0 = int(round(y0))
        ix1 = min(WIDTH, max(ix0 + 16, int(round(x0 + crop_w))))
        iy1 = min(HEIGHT, max(iy0 + 16, int(round(y0 + crop_h))))

        if ix0 > 0 or iy0 > 0 or ix1 < WIDTH or iy1 < HEIGHT:
            recorte = frame_rgb[iy0:iy1, ix0:ix1]
            frame_zoomed = cv2.resize(recorte, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
        else:
            frame_zoomed = frame_rgb

        # Transformar cada punto rastreado (vx, vy) al espacio de pantalla (screen_x, screen_y)
        escala_x = WIDTH / float(max(1, ix1 - ix0))
        escala_y = HEIGHT / float(max(1, iy1 - iy0))
        puntos_pantalla: List[Tuple[float, float]] = []
        for vx, vy in puntos_rastreados:
            sx = (vx - ix0) * escala_x
            sy = (vy - iy0) * escala_y
            sx = float(np.clip(sx, 28.0, WIDTH - 28.0))
            sy = float(np.clip(sy, 40.0, HEIGHT - 160.0))
            puntos_pantalla.append((sx, sy))

        # Efecto de aberración cromática RGB durante impactos fuertes (temblor / zoom_impacto inicial)
        if (efecto == "temblor" and t_seg < 0.7) or (efecto == "zoom_impacto" and t_seg < 0.18):
            shift = int(round(7.0 * math.exp(-t_seg * 6.0)))
            if shift >= 2:
                out_rgb = frame_zoomed.copy()
                out_rgb[:, shift:, 0] = frame_zoomed[:, :-shift, 0]
                out_rgb[:, :-shift, 2] = frame_zoomed[:, shift:, 2]
                frame_zoomed = out_rgb

        img_pil = Image.fromarray(frame_zoomed, mode="RGB").convert("RGBA")

        # Efectos de color y atmósfera
        if efecto == "blanco_negro":
            gris = img_pil.convert("L")
            gris_contraste = ImageEnhance.Contrast(gris).enhance(1.22)
            img_pil = Image.merge("RGBA", (gris_contraste, gris_contraste, gris_contraste, Image.new("L", (WIDTH, HEIGHT), 255)))
            img_pil = Image.alpha_composite(img_pil, self.vineta_oscura_base)

        elif efecto == "alerta_roja":
            pulso_rojo = 0.45 + 0.55 * abs(math.sin(t_seg * 6.5))
            r, g, b, a = self.vineta_roja_base.split()
            a_mod = a.point(lambda p: int(p * pulso_rojo))
            vineta_p = Image.merge("RGBA", (r, g, b, a_mod))
            img_pil = Image.alpha_composite(img_pil, vineta_p)

        elif efecto == "brillo_epico":
            rgb_temp = ImageEnhance.Color(img_pil.convert("RGB")).enhance(1.26)
            rgb_temp = ImageEnhance.Contrast(rgb_temp).enhance(1.08)
            img_pil = rgb_temp.convert("RGBA")
            if t_seg < 0.30:
                alpha_dorado = int(round(90.0 * (1.0 - t_seg / 0.30)))
                capa_dorada = Image.new("RGBA", (WIDTH, HEIGHT), (255, 215, 60, alpha_dorado))
                img_pil = Image.alpha_composite(img_pil, capa_dorada)

        elif efecto == "flash":
            if t_seg < 0.32:
                alpha_flash = int(round(220.0 * ((1.0 - t_seg / 0.32) ** 1.8)))
                capa_blanca = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha_flash))
                img_pil = Image.alpha_composite(img_pil, capa_blanca)

        # Micro-destello de transición suave en los primeros 3 fotogramas de cada segmento
        if t_seg < 0.06 and efecto != "flash":
            alpha_tr = int(round(55.0 * (1.0 - t_seg / 0.06)))
            if alpha_tr > 4:
                img_pil = Image.alpha_composite(
                    img_pil, Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha_tr))
                )

        return img_pil, puntos_pantalla

    def dibujar_circulo_rojo(
        self,
        lienzo: Image.Image,
        activo: bool,
        target_xy: Tuple[float, float],
        tamano_mod: str,
        t_seg: float,
        dur_seg: float,
    ) -> float:
        """
        Dibuja `circulo_rojo.png` centrado exactamente sobre `target_xy` y devuelve
        el radio exterior actual en píxeles (para que la flecha apunte al borde del círculo).
        """
        if not activo or self.circulo_base is None:
            return 0.0

        dur_mostrar = max(0.8, min(dur_seg - 0.15, self.duracion_callouts))
        if t_seg < 0.04 or t_seg > dur_mostrar:
            return 0.0

        mapa_diametro = {
            "chico": 370,
            "medio": 475,
            "grande": 580,
        }
        diam_base = mapa_diametro.get(tamano_mod, 475)

        if t_seg < 0.22:
            p_in = (t_seg - 0.04) / 0.18
            escala = 0.25 + 0.88 * math.sin(p_in * math.pi * 0.65)
            alpha_f = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.18:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.18)
            escala = 0.75 + 0.25 * p_out
            alpha_f = p_out
        else:
            # Pulso rítmico llamativo alrededor del objetivo
            escala = 1.0 + 0.075 * math.sin(t_seg * 11.5)
            alpha_f = 1.0

        diam_actual = max(48, int(round(diam_base * escala)))
        circ_img = self.circulo_base.resize((diam_actual, diam_actual), Image.Resampling.LANCZOS)

        if alpha_f < 0.99:
            r, g, b, a = circ_img.split()
            a = a.point(lambda p: int(p * alpha_f))
            circ_img = Image.merge("RGBA", (r, g, b, a))

        tx, ty = int(round(target_xy[0])), int(round(target_xy[1]))
        pos_x = tx - diam_actual // 2
        pos_y = ty - diam_actual // 2

        # Si el círculo sobresale parcialmente del borde, recortar el sprite en lugar de desplazar su centro
        crop_l = max(0, -pos_x)
        crop_t = max(0, -pos_y)
        crop_r = min(diam_actual, WIDTH - pos_x)
        crop_b = min(diam_actual, HEIGHT - pos_y)
        if crop_r > crop_l and crop_b > crop_t:
            if crop_l > 0 or crop_t > 0 or crop_r < diam_actual or crop_b < diam_actual:
                circ_img = circ_img.crop((crop_l, crop_t, crop_r, crop_b))
            lienzo.alpha_composite(circ_img, dest=(max(0, pos_x), max(0, pos_y)))

        # Radio visible real del anillo rojo (0.406 del ancho de la imagen)
        return diam_actual * 0.406

    def dibujar_flecha_roja(
        self,
        lienzo: Image.Image,
        activo: bool,
        target_xy: Tuple[float, float],
        radio_circulo_activo: float,
        t_seg: float,
        dur_seg: float,
    ) -> None:
        """
        Dibuja `flecha.png` apuntando con precisión trigonométrica hacia `target_xy`
        y persiguiéndolo cuadro a cuadro. Si hay un círculo rojo sobre el mismo objetivo,
        la punta de la flecha señala justo al borde exterior del círculo.
        """
        if not activo or self.flecha_base is None:
            return

        dur_mostrar = max(0.8, min(dur_seg - 0.15, self.duracion_callouts))
        if t_seg < 0.04 or t_seg > dur_mostrar:
            return

        tx, ty = target_xy

        # Elegir el vector unitario u = (ux, uy) que va DESDE el objetivo HACIA la cola de la flecha,
        # apuntando siempre desde el lado de la pantalla con mayor espacio libre para que la cola
        # jamás se salga del lienzo 1080x1920.
        dx_centro = (WIDTH * 0.50) - tx
        dy_centro = (HEIGHT * 0.42) - ty

        if abs(dx_centro) < 95.0 and abs(dy_centro) < 95.0:
            # Si el objetivo está en el centro, apuntar en diagonal desde arriba-derecha (-32°)
            ux, uy = 0.848, -0.530
        else:
            # Apuntar desde el espacio abierto hacia el objetivo con una inclinación diagonal atractiva
            ux = dx_centro
            uy = dy_centro - 90.0 if ty > 420 else dy_centro + 110.0
            norm = math.hypot(ux, uy)
            if norm < 1e-3:
                ux, uy = 0.848, -0.530
            else:
                ux /= norm
                uy /= norm

        # En `flecha.png`, la punta apunta a la IZQUIERDA (-1, 0) y la cola está hacia (+1, 0).
        # Para orientar el eje de la cola hacia (ux, uy), el ángulo de rotación en PIL es -atan2(uy, ux).
        angulo_pil = -math.degrees(math.atan2(uy, ux))

        if t_seg < 0.20:
            p_in = (t_seg - 0.04) / 0.16
            escala_in = 0.45 + 0.62 * math.sin(p_in * math.pi * 0.65)
            alpha_f = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.18:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.18)
            escala_in = 0.75 + 0.25 * p_out
            alpha_f = p_out
        else:
            escala_in = 1.0
            alpha_f = 1.0

        tam_flecha = max(96, int(round(355 * escala_in)))
        flecha_scaled = self.flecha_base.resize((tam_flecha, tam_flecha), Image.Resampling.LANCZOS)
        flecha_rot = flecha_scaled.rotate(angulo_pil, resample=Image.Resampling.BICUBIC, expand=True)

        if alpha_f < 0.99:
            r, g, b, a = flecha_rot.split()
            a = a.point(lambda p: int(p * alpha_f))
            flecha_rot = Image.merge("RGBA", (r, g, b, a))

        # Distancia exacta desde el objetivo hasta la punta de la flecha + rebote rítmico a lo largo de su eje
        gap_objetivo = (radio_circulo_activo + 6.0) if radio_circulo_activo > 10.0 else 18.0
        rebote = 28.0 * abs(math.sin(t_seg * 10.5))
        dist_centro_a_punta = tam_flecha * 0.472
        dist_total = gap_objetivo + rebote + dist_centro_a_punta

        cx = int(round(tx + ux * dist_total))
        cy = int(round(ty + uy * dist_total))

        fw, fh = flecha_rot.size
        pos_x = cx - fw // 2
        pos_y = cy - fh // 2

        # Recortar únicamente si la cola sobresale del borde para NUNCA desviar la punta del objetivo
        crop_l = max(0, -pos_x)
        crop_t = max(0, -pos_y)
        crop_r = min(fw, WIDTH - pos_x)
        crop_b = min(fh, HEIGHT - pos_y)
        if crop_r > crop_l and crop_b > crop_t:
            if crop_l > 0 or crop_t > 0 or crop_r < fw or crop_b < fh:
                flecha_rot = flecha_rot.crop((crop_l, crop_t, crop_r, crop_b))
            lienzo.alpha_composite(flecha_rot, dest=(max(0, pos_x), max(0, pos_y)))

    def dibujar_emoji(
        self,
        lienzo: Image.Image,
        nombre_emoji: Optional[str],
        posicion_solicitada: str,
        target_principal_xy: Optional[Tuple[float, float]],
        t_seg: float,
        dur_seg: float,
    ) -> None:
        if not nombre_emoji:
            return
        clave = _quitar_acentos(nombre_emoji.strip().lower())
        img_base = self.emojis_cache.get(clave)
        if img_base is None:
            return

        dur_mostrar = max(1.2, min(dur_seg - 0.05, 3.6))
        if t_seg < 0.05 or t_seg > dur_mostrar:
            return

        if t_seg < 0.24:
            p_in = (t_seg - 0.05) / 0.19
            escala_anim = 0.22 + 0.90 * math.sin(p_in * math.pi * 0.65)
            alpha_factor = min(1.0, p_in * 1.6)
        elif t_seg > dur_mostrar - 0.20:
            p_out = max(0.0, (dur_mostrar - t_seg) / 0.20)
            escala_anim = 0.65 + 0.35 * p_out
            alpha_factor = p_out
        else:
            escala_anim = 1.0 + 0.065 * math.sin(t_seg * 7.5)
            alpha_factor = 1.0

        tam_base = 245
        tam_actual = max(32, int(round(tam_base * escala_anim)))
        emoji_img = img_base.resize((tam_actual, tam_actual), Image.Resampling.LANCZOS)

        angulo = 7.5 * math.sin(t_seg * 5.8)
        emoji_img = emoji_img.rotate(angulo, resample=Image.Resampling.BICUBIC, expand=True)

        if alpha_factor < 0.99:
            r, g, b, a = emoji_img.split()
            a = a.point(lambda p: int(p * alpha_factor))
            emoji_img = Image.merge("RGBA", (r, g, b, a))

        # Evitar que el emoji se superponga con el círculo/flecha si están del mismo lado
        pos_efectiva = posicion_solicitada
        if target_principal_xy is not None:
            tx, ty = target_principal_xy
            if pos_efectiva == "auto":
                pos_efectiva = "izquierda" if tx >= WIDTH * 0.5 else "derecha"
            elif pos_efectiva == "derecha" and tx > WIDTH * 0.62 and abs(ty - 340) < 230:
                pos_efectiva = "izquierda"
            elif pos_efectiva == "izquierda" and tx < WIDTH * 0.38 and abs(ty - 340) < 230:
                pos_efectiva = "derecha"
        elif pos_efectiva == "auto":
            pos_efectiva = "derecha"

        pos_map = {
            "derecha": (WIDTH - 195, 330),
            "izquierda": (195, 330),
            "arriba_der": (WIDTH - 190, 240),
            "arriba_izq": (190, 240),
            "centro": (WIDTH // 2, 340),
            "abajo": (WIDTH - 195, 1060),
        }
        cx, cy = pos_map.get(pos_efectiva, pos_map["derecha"])
        cy += int(round(9.0 * math.sin(t_seg * 6.2)))

        ew, eh = emoji_img.size
        lienzo.alpha_composite(emoji_img, dest=(max(0, cx - ew // 2), max(0, cy - eh // 2)))


# ==============================================================================
# 8. GESTOR DE AUDIO/SFX (.MP3/.WAV) Y PIPELINE DE RENDERIZADO POR SEGMENTO
# ==============================================================================
class GestorAudioSFX:
    """
    Decodifica y cachea todos los archivos de `sfx/` (.mp3, .MP3, .wav, .ogg) usando FFmpeg,
    recorta silencios muertos al inicio/final para sincronización instantánea y normaliza
    sus picos para una mezcla profesional junto a la voz IA.
    """

    def __init__(self, sfx_dir: Path, sr: int = 44100):
        self.sfx_dir = sfx_dir
        self.sr = sr
        self.cache_pcm: Dict[str, np.ndarray] = {}
        self._cargar_todos_los_sfx()

    def _cargar_todos_los_sfx(self) -> None:
        if not self.sfx_dir.exists():
            return
        for archivo in sorted(self.sfx_dir.glob("*.*")):
            if archivo.suffix.lower() not in (".mp3", ".wav", ".ogg", ".m4a"):
                continue
            clave = _quitar_acentos(archivo.stem.strip().lower())
            try:
                res = subprocess.run(
                    [
                        "ffmpeg", "-v", "error",
                        "-i", str(archivo),
                        "-f", "s16le", "-ac", "1", "-ar", str(self.sr), "-",
                    ],
                    capture_output=True,
                    check=False,
                )
                if res.returncode != 0 or len(res.stdout) < 100:
                    continue
                pcm = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                peak = float(np.max(np.abs(pcm)))
                if peak < 1e-4:
                    continue

                # Recortar silencio muerto inicial y final (ej. xp_Error o riser_suction)
                umbral = max(0.008, peak * 0.045)
                activos = np.where(np.abs(pcm) > umbral)[0]
                if len(activos) > 0:
                    pad_ini = int(self.sr * 0.012)
                    pad_fin = int(self.sr * 0.040)
                    i0 = max(0, int(activos[0]) - pad_ini)
                    i1 = min(len(pcm), int(activos[-1]) + pad_fin)
                    pcm = pcm[i0:i1].copy()

                # Normalizar pico a 0.85 para consistencia entre efectos
                pcm = pcm * (0.85 / peak)

                # Fade-out suave en los últimos 25ms
                fade_n = min(int(self.sr * 0.025), len(pcm) // 4)
                if fade_n > 2:
                    pcm[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

                self.cache_pcm[clave] = pcm
            except Exception:
                continue

        print(f"[*] Efectos de sonido (SFX) cargados ({len(self.cache_pcm)}): {sorted(self.cache_pcm.keys())}")

    def obtener_pcm(self, nombre_sfx: str) -> Optional[np.ndarray]:
        clave = _quitar_acentos(nombre_sfx.strip().lower())
        return self.cache_pcm.get(clave)

    def mezclar_audio_segmento(
        self,
        ruta_voz_wav: Path,
        duracion_total_seg: float,
        sfx_lista: List[str],
        tiene_emoji_o_flecha: bool,
        ruta_salida_wav: Path,
    ) -> None:
        n_total = int(round(duracion_total_seg * self.sr))
        mezcla = np.zeros(n_total, dtype=np.float32)

        with wave.open(str(ruta_voz_wav), "r") as wf:
            voz_pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            n_copy = min(n_total, len(voz_pcm))
            voz_fuerte = np.tanh(voz_pcm[:n_copy] * VOLUMEN_VOZ_NARRADOR)
            mezcla[:n_copy] += voz_fuerte

        # Superponer los SFX solicitados (con ligero escalonamiento si hay más de uno)
        for idx_s, nombre_sfx in enumerate(sfx_lista):
            sfx_pcm = self.obtener_pcm(nombre_sfx)
            if sfx_pcm is None or len(sfx_pcm) == 0:
                continue
            offset_samples = int(round(idx_s * 0.14 * self.sr))
            if offset_samples >= n_total:
                continue
            n_disp = min(n_total - offset_samples, len(sfx_pcm))
            # Limitar duración máxima de SFX muy largos para no ensuciar toda la frase
            max_samples_sfx = int(round(2.4 * self.sr))
            n_usar = min(n_disp, max_samples_sfx)
            bloque_sfx = sfx_pcm[:n_usar].copy()
            if n_usar < len(sfx_pcm) and n_usar > 400:
                bloque_sfx[-400:] *= np.linspace(1.0, 0.0, 400, dtype=np.float32)

            ganancia_sfx = 0.34 if idx_s == 0 else 0.28
            mezcla[offset_samples : offset_samples + n_usar] += bloque_sfx * ganancia_sfx

        # Si aparece un emoji o flecha y no se pidió 'pop', añadir un sutil pop acústico a los 60ms
        if tiene_emoji_o_flecha and "pop" not in sfx_lista:
            pop_pcm = self.obtener_pcm("pop")
            if pop_pcm is not None:
                off_pop = int(round(0.06 * self.sr))
                n_pop = min(max(0, n_total - off_pop), len(pop_pcm))
                if n_pop > 0:
                    mezcla[off_pop : off_pop + n_pop] += pop_pcm[:n_pop] * 0.18

        mezcla = np.clip(mezcla, -0.98, 0.98)
        pcm_out = (mezcla * 32767).astype(np.int16)
        with wave.open(str(ruta_salida_wav), "w") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(self.sr)
            wf_out.writeframes(pcm_out.tobytes())


def obtener_info_video(ruta_video: Path) -> Tuple[float, int, int, float]:
    """
    Devuelve (duracion_seg, ancho, alto, fps) exactos del video de entrada.
    """
    if not ruta_video.exists():
        raise FileNotFoundError(f"No se encontró el archivo de video: {ruta_video}")
    cap = cv2.VideoCapture(str(ruta_video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
    cap.release()

    dur = 0.0
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(ruta_video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        dur = float(res.stdout.strip())
    except Exception:
        dur = 0.0

    if dur <= 0.1 and n_frames > 0 and fps > 0:
        dur = float(n_frames) / float(fps)
    if dur <= 0.1:
        dur = 15.0
    return max(0.5, dur), w, h, float(fps)


def _asignar_tiempos_reales_segmentos(
    segmentos: List[SegmentoVideoGuion],
    dur_video_origen: float,
) -> List[Tuple[int, float]]:
    """
    Asigna a cada segmento su tramo exacto `[t_inicio_video, t_fin_video]` dentro de
    `[0.0, dur_video_origen]` a velocidad 1.0x real (sin cámara lenta ni estiramientos),
    garantizando que la suma de fotogramas de todos los segmentos coincida exactamente
    con la duración de `video_input`.
    Devuelve una lista de `(total_frames_seg, dur_seg_exacta)` por cada segmento.
    """
    n_segs = len(segmentos)
    total_frames_video = max(n_segs, int(round(dur_video_origen * FPS)))
    dur_exacta_total = total_frames_video / float(FPS)

    todos_explicitos = all(
        (s.t_inicio_video is not None and s.t_fin_video is not None and s.t_fin_video > s.t_inicio_video)
        for s in segmentos
    )

    limites_seg: List[float] = [0.0]
    if todos_explicitos:
        t_max_guion = float(segmentos[-1].t_fin_video or dur_exacta_total)
        penultimo_fin = float(segmentos[-2].t_fin_video or 0.0) if n_segs > 1 else 0.0

        # Si los tiempos del guion coinciden con el video (salvo redondeo de ±3.5s en el último bloque)
        if penultimo_fin < (dur_exacta_total - 0.8) and abs(t_max_guion - dur_exacta_total) <= 3.5:
            cursor_t = 0.0
            for idx_s, s in enumerate(segmentos):
                if idx_s == n_segs - 1:
                    limites_seg.append(dur_exacta_total)
                else:
                    t_f = float(np.clip(float(s.t_fin_video or cursor_t + 1.0), cursor_t + 0.4, dur_exacta_total - 0.4))
                    limites_seg.append(t_f)
                    cursor_t = t_f
        else:
            # Escalar proporcionalmente las duraciones solicitadas para cubrir exactamente [0, dur_exacta_total]
            pesos = [max(0.5, float(s.t_fin_video - s.t_inicio_video)) for s in segmentos]
            suma_p = sum(pesos)
            acum = 0.0
            for idx_s, p in enumerate(pesos):
                acum += p
                if idx_s == n_segs - 1:
                    limites_seg.append(dur_exacta_total)
                else:
                    limites_seg.append((acum / suma_p) * dur_exacta_total)
    else:
        # Si algún segmento tiene 'auto', repartir [0, dur_exacta_total] proporcionalmente a las palabras
        pesos = []
        for s in segmentos:
            if s.t_inicio_video is not None and s.t_fin_video is not None and s.t_fin_video > s.t_inicio_video:
                pesos.append(max(1.0, (s.t_fin_video - s.t_inicio_video) * 3.5))
            else:
                pesos.append(max(3.0, float(len(s.texto_voz.split()))))
        suma_p = sum(pesos)
        acum = 0.0
        for idx_s, p in enumerate(pesos):
            acum += p
            if idx_s == n_segs - 1:
                limites_seg.append(dur_exacta_total)
            else:
                limites_seg.append((acum / suma_p) * dur_exacta_total)

    # Convertir los límites de tiempo a índices de fotograma exactos a 60 FPS
    limites_frames: List[int] = [0]
    for idx_s in range(1, n_segs):
        f_ideal = int(round(limites_seg[idx_s] * FPS))
        f_min = limites_frames[-1] + 1
        f_max = total_frames_video - (n_segs - idx_s)
        limites_frames.append(max(f_min, min(f_max, f_ideal)))
    limites_frames.append(total_frames_video)

    resultado: List[Tuple[int, float]] = []
    for idx_s, seg in enumerate(segmentos):
        f0 = limites_frames[idx_s]
        f1 = limites_frames[idx_s + 1]
        n_frames_seg = max(1, f1 - f0)
        dur_seg = n_frames_seg / float(FPS)
        seg.t_inicio_video = f0 / float(FPS)
        seg.t_fin_video = f1 / float(FPS)
        resultado.append((n_frames_seg, dur_seg))

    return resultado


def extraer_frames_segmento_video(
    ruta_video: Path,
    t_ini: float,
    t_fin: float,
    total_frames_salida: int,
    modo_encuadre: str = "full",
) -> List[np.ndarray]:
    """
    Extrae el rango [t_ini, t_fin] a velocidad real 1.0x (60 FPS) sin cámara lenta
    y devuelve exactamente `total_frames_salida` fotogramas RGB (1080x1920).
    """
    dur_clip = max(0.05, t_fin - t_ini)
    fps_extraccion = float(FPS)

    if modo_encuadre == "blur":
        filtro_vf = (
            f"split[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},boxblur=24:4,eq=brightness=-0.12[bg_b];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fg_s];"
            f"[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2,fps={fps_extraccion:.3f}"
        )
        cmd_ff = [
            "ffmpeg", "-v", "error",
            "-ss", f"{max(0.0, t_ini):.4f}",
            "-t", f"{dur_clip:.4f}",
            "-i", str(ruta_video),
            "-filter_complex", filtro_vf,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ]
    else:
        filtro_vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"fps={fps_extraccion:.3f}"
        )
        cmd_ff = [
            "ffmpeg", "-v", "error",
            "-ss", f"{max(0.0, t_ini):.4f}",
            "-t", f"{dur_clip:.4f}",
            "-i", str(ruta_video),
            "-vf", filtro_vf,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ]

    frames_raw: List[np.ndarray] = []
    bytes_por_frame = WIDTH * HEIGHT * 3
    try:
        proc = subprocess.Popen(cmd_ff, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if proc.stdout:
            while True:
                buf = proc.stdout.read(bytes_por_frame)
                if len(buf) < bytes_por_frame:
                    break
                frame_np = np.frombuffer(buf, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy()
                frames_raw.append(frame_np)
        proc.wait()
    except Exception:
        frames_raw.clear()

    # Fallback con OpenCV si FFmpeg no devolvió frames
    if not frames_raw:
        cap = cv2.VideoCapture(str(ruta_video))
        fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_ini) * 1000.0)
        max_leer = max(2, int(round(dur_clip * fps_orig)))
        for _ in range(max_leer):
            ret, frame_bgr = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, _ = frame_rgb.shape
            scale = max(WIDTH / float(w), HEIGHT / float(h))
            nw, nh = int(round(w * scale)), int(round(h * scale))
            resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
            x0 = (nw - WIDTH) // 2
            y0 = (nh - HEIGHT) // 2
            frames_raw.append(resized[y0 : y0 + HEIGHT, x0 : x0 + WIDTH].copy())
        cap.release()

    if not frames_raw:
        if t_ini > 0.1:
            return extraer_frames_segmento_video(ruta_video, 0.0, dur_clip, total_frames_salida, modo_encuadre)
        raise RuntimeError(f"No se pudieron decodificar fotogramas de: {ruta_video}")

    if len(frames_raw) == total_frames_salida:
        return frames_raw
    if len(frames_raw) > total_frames_salida:
        return frames_raw[:total_frames_salida]

    # Si por redondeo de paquetes falta 1 o 2 cuadros al final, seleccionar sin blending fantasma
    resultado: List[np.ndarray] = []
    n_src = len(frames_raw)
    for f_idx in range(total_frames_salida):
        idx_src = min(n_src - 1, int(round((f_idx / float(max(1, total_frames_salida - 1))) * (n_src - 1))))
        resultado.append(frames_raw[idx_src])
    return resultado


def calcular_envolvente_rms(ruta_wav: Path, fps: int) -> np.ndarray:
    with wave.open(str(ruta_wav), "r") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    muestras_por_frame = max(1, int(sr / fps))
    total_video_frames = int(math.ceil(len(audio) / muestras_por_frame))
    rms_por_frame = np.zeros(total_video_frames, dtype=np.float32)

    for i in range(total_video_frames):
        chunk = audio[i * muestras_por_frame : (i + 1) * muestras_por_frame]
        if len(chunk) > 0:
            rms_por_frame[i] = float(np.sqrt(np.mean(chunk ** 2)))
    return rms_por_frame


_ENCODER_SELECCIONADO: Optional[Tuple[str, List[str]]] = None


def detectar_encoder_video() -> Tuple[str, List[str]]:
    """
    Detecta y prueba qué codificador de video H.264 acelerado por hardware
    (NVIDIA NVENC, AMD AMF o Intel QSV) o CPU (libx264) es compatible
    y funcional en la GPU/sistema actual mediante una prueba real de 1 frame.
    """
    global _ENCODER_SELECCIONADO
    if _ENCODER_SELECCIONADO is not None:
        return _ENCODER_SELECCIONADO

    candidatos: List[Tuple[str, List[str]]] = [
        # NVIDIA NVENC
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "14M", "-pix_fmt", "yuv420p"]),
        # AMD Radeon AMF
        ("h264_amf", ["-c:v", "h264_amf", "-quality", "quality", "-b:v", "14M", "-pix_fmt", "yuv420p"]),
        # Intel Quick Sync Video
        ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", "14M", "-pix_fmt", "yuv420p"]),
    ]

    for nombre, args in candidatos:
        try:
            # Probar si el encoder inicializa correctamente en el hardware actual (256x256 cumple el mínimo de AMD y NVIDIA)
            cmd_test = [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
                *args,
                "-f", "null", "-"
            ]
            res = subprocess.run(cmd_test, capture_output=True, check=False)
            if res.returncode == 0:
                _ENCODER_SELECCIONADO = (nombre, args)
                return _ENCODER_SELECCIONADO
        except Exception:
            continue

    # Fallback universal por CPU (funciona en cualquier máquina)
    args_cpu = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-threads", str(CPU_THREADS), "-pix_fmt", "yuv420p",
    ]
    _ENCODER_SELECCIONADO = ("libx264", args_cpu)
    return _ENCODER_SELECCIONADO


def detectar_encoder_nvidia() -> str:
    encoder, _ = detectar_encoder_video()
    return encoder


MAX_CIRCULOS_POR_VIDEO = 2
MAX_FLECHAS_POR_VIDEO = 2


def _limitar_circulos_guion(
    segmentos: List[SegmentoVideoGuion],
    max_circulos: int = MAX_CIRCULOS_POR_VIDEO,
    max_flechas: int = MAX_FLECHAS_POR_VIDEO,
) -> None:
    """
    Limita tanto los círculos rojos como las flechas rojas para que aparezcan de forma
    espaciada y menos frecuente, evitando saturar todos los segmentos del Short.
    """
    con_circulo = [i for i, s in enumerate(segmentos) if s.circulo]
    if len(con_circulo) > max_circulos:
        prioridad = sorted(con_circulo, key=lambda i: (0 if segmentos[i].tamano_circulo == "grande" else 1, i))
        conservar = set(prioridad[:max_circulos])
        for i in con_circulo:
            if i not in conservar:
                segmentos[i].circulo = None
        print(
            f"[*] Círculo rojo limitado a {max_circulos} segmento(s): "
            f"{', '.join(str(i + 1) for i in sorted(conservar))}."
        )

    # Si un segmento ya tiene círculo rojo, quitarle la flecha para no superponer ambos
    for s in segmentos:
        if s.circulo and s.flecha:
            s.flecha = None

    # Limitar la frecuencia de flechas rojas (espaciadas, evitando segmentos consecutivos)
    con_flecha = [i for i, s in enumerate(segmentos) if s.flecha]
    if len(con_flecha) > max_flechas:
        seleccionadas: List[int] = []
        for idx in con_flecha:
            # Preferir segmentos no consecutivos para que la aparición sea intermitente
            if not seleccionadas or (idx - seleccionadas[-1]) >= 2:
                seleccionadas.append(idx)
            if len(seleccionadas) >= max_flechas:
                break
        # Si aún faltan hasta llegar al tope permitido, completar
        for idx in con_flecha:
            if len(seleccionadas) >= max_flechas:
                break
            if idx not in seleccionadas:
                seleccionadas.append(idx)

        conservar_flechas = set(seleccionadas[:max_flechas])
        for i in con_flecha:
            if i not in conservar_flechas:
                segmentos[i].flecha = None
        print(
            f"[*] Flechas rojas limitadas a {len(conservar_flechas)} segmento(s) clave: "
            f"{', '.join(str(i + 1) for i in sorted(conservar_flechas))}."
        )


async def editar_video_con_guion(
    ruta_video: Path,
    ruta_guion: Path,
    voz_override: Optional[str] = None,
    modo_encuadre_override: Optional[str] = None,
    progreso_cb: Optional[object] = None,
) -> Path:
    def _notificar_prog(frac_0_1: float, detalle: str) -> None:
        if callable(progreso_cb):
            try:
                progreso_cb(float(np.clip(frac_0_1, 0.0, 1.0)), detalle)
            except Exception:
                pass

    print("=" * 78)
    print(" EDITOR SHORTS STUDIO v1.0 - AUTOMATIZACIÓN DE SHORTS (VOZ IA + TRACKING)")
    print("=" * 78)

    for carpeta in [EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, TEMP_DIR, OUTPUT_DIR]:
        carpeta.mkdir(parents=True, exist_ok=True)
    asegurar_fuente_mrbeast()

    config = cargar_guion_video(ruta_guion)
    if not config.segmentos:
        raise ValueError(f"El guión '{ruta_guion.name}' no contiene segmentos válidos.")

    if voz_override:
        config.voz_narrador = voz_override
    if modo_encuadre_override:
        config.modo_encuadre = modo_encuadre_override

    _limitar_circulos_guion(config.segmentos)

    dur_video_origen, w_orig, h_orig, fps_orig = obtener_info_video(ruta_video)
    print(
        f"[*] Video base: '{ruta_video.name}' ({w_orig}x{h_orig} a {fps_orig:.1f} FPS | Duración exacta: {dur_video_origen:.2f}s)"
    )

    # 1. Fijar los tramos reales 1.0x de cada segmento sobre `dur_video_origen` ANTES de generar la voz
    # para que el video de fondo NUNCA vaya en cámara lenta y dure exactamente lo mismo que `video_input`.
    tiempos_reales = _asignar_tiempos_reales_segmentos(config.segmentos, dur_video_origen)

    gestor_assets = GestorEfectosYAssets(EMOJIS_DIR, FOTOS_DIR, duracion_callouts=config.duracion_callouts)
    gestor_sfx = GestorAudioSFX(SFX_DIR)

    datos_segmentos = []
    archivos_audio_seg: List[Path] = []
    n_segs = max(1, len(config.segmentos))

    # 2. Generar voz IA ajustada a la duración real 1.0x de cada segmento, subtítulos y mezcla de SFX
    for idx, (seg, (total_frames_seg, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales)):
        _notificar_prog(
            0.05 + 0.30 * (idx / float(n_segs)),
            f"Generando voz IA y mezcla de efectos (bloque {idx + 1}/{n_segs})...",
        )
        sfx_str = "+".join(seg.sfx_lista) if seg.sfx_lista else "-"
        info_seg = (
            f"{seg.t_inicio_video:.1f}s-{seg.t_fin_video:.1f}s | efecto={seg.efecto_visual} | "
            f"sfx={sfx_str} | emoji={seg.emoji or '-'} | flecha={seg.flecha or '-'} | circulo={seg.circulo or '-'}"
        )
        print(f"[+] Segmento [{idx + 1}/{len(config.segmentos)}] ({info_seg}): {seg.texto_voz}")

        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        dur_voz, palabras_sub, ini_voz, fin_voz = await generar_voz_y_timestamps_segmento(
            seg.texto_voz,
            ruta_mp3,
            voz_edge=config.voz_narrador,
            dur_objetivo_seg=dur_seg_exacta,
        )

        ruta_voz_wav = ruta_mp3.with_suffix(".wav")
        rms_env = calcular_envolvente_rms(ruta_voz_wav, FPS)

        ruta_mix_wav = TEMP_DIR / f"{seg.id_segmento}_mix.wav"
        tiene_overlay_pop = bool(seg.emoji or seg.flecha or seg.circulo)
        gestor_sfx.mezclar_audio_segmento(
            ruta_voz_wav=ruta_voz_wav,
            duracion_total_seg=dur_seg_exacta,
            sfx_lista=seg.sfx_lista,
            tiene_emoji_o_flecha=tiene_overlay_pop,
            ruta_salida_wav=ruta_mix_wav,
        )
        archivos_audio_seg.append(ruta_mix_wav)
        datos_segmentos.append([seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env])

    _notificar_prog(0.38, "Masterizando pista de audio final con música de fondo...")

    # 3. Unir el audio maestro de la voz + SFX + audio de fondo del video original
    ruta_voz_maestra = TEMP_DIR / "voz_maestra.wav"
    bloques_pcm = []
    for ruta_w in archivos_audio_seg:
        with wave.open(str(ruta_w), "r") as wf:
            bloques_pcm.append(wf.readframes(wf.getnframes()))
    with wave.open(str(ruta_voz_maestra), "w") as wf_master:
        wf_master.setnchannels(1)
        wf_master.setsampwidth(2)
        wf_master.setframerate(44100)
        for b in bloques_pcm:
            wf_master.writeframes(b)

    ruta_audio_final = TEMP_DIR / "audio_final_combinado.wav"
    if config.volumen_video_original > 0.001:
        res_mix = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(ruta_voz_maestra),
                "-stream_loop", "-1", "-i", str(ruta_video),
                "-filter_complex",
                f"[1:a]volume={config.volumen_video_original}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=disabled[aout]",
                "-map", "[aout]",
                "-ar", "44100", "-ac", "1",
                str(ruta_audio_final),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if res_mix.returncode != 0 or not ruta_audio_final.exists():
            ruta_audio_final = ruta_voz_maestra
    else:
        ruta_audio_final = ruta_voz_maestra

    # 4. Configurar nombre de archivo de salida y codificador FFmpeg (NVENC o libx264)
    if config.titulo_superior:
        titulo_limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", config.titulo_superior).strip().rstrip(".")
        nombre_out = titulo_limpio or config.archivo_salida or f"short_editado_{ruta_video.stem}.mp4"
    else:
        nombre_out = config.archivo_salida or f"short_editado_{ruta_video.stem}.mp4"

    if not nombre_out.lower().endswith(".mp4"):
        nombre_out += ".mp4"
    ruta_mp4_final = OUTPUT_DIR / nombre_out
    encoder, args_codec = detectar_encoder_video()
    if "amf" in encoder:
        tipo_gpu = "Aceleración Hardware AMD Radeon (AMF)"
    elif "nvenc" in encoder:
        tipo_gpu = "Aceleración Hardware NVIDIA (NVENC)"
    elif "qsv" in encoder:
        tipo_gpu = "Aceleración Hardware Intel (QSV)"
    else:
        tipo_gpu = "Procesador CPU (libx264)"
    print(f"[*] Renderizando Short final con {encoder} [{tipo_gpu}] ({WIDTH}x{HEIGHT} a {FPS} FPS)...")

    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(ruta_audio_final),
        *args_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(ruta_mp4_final),
    ]

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_err_ffmpeg = TEMP_DIR / "ffmpeg_render_error.log"
    f_err = open(ruta_err_ffmpeg, "w", encoding="utf-8", errors="replace")
    proceso_ffmpeg = subprocess.Popen(cmd_ffmpeg, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=f_err)

    # Nota: `config.titulo_superior` se usa únicamente para darle nombre al archivo MP4 exportado
    # y NO se renderiza encima del video.

    # 5. Renderizar segmento por segmento con seguimiento de objetivos (Optical Flow) y subtítulos luminosos
    for idx_seg, (seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env) in enumerate(datos_segmentos):
        _notificar_prog(
            0.40 + 0.58 * (idx_seg / float(max(1, len(datos_segmentos)))),
            f"Renderizando video a 60 FPS con subtítulos neón y tracking ({idx_seg + 1}/{len(datos_segmentos)})...",
        )
        t_vid_ini = float(seg.t_inicio_video or 0.0)
        t_vid_fin = float(seg.t_fin_video or dur_video_origen)

        frames_seg_rgb = extraer_frames_segmento_video(
            ruta_video=ruta_video,
            t_ini=t_vid_ini,
            t_fin=t_vid_fin,
            total_frames_salida=total_frames_seg,
            modo_encuadre=config.modo_encuadre,
        )

        # Calcular trayectorias rastreadas por visión artificial para FLECHA y CIRCULO
        mismo_objetivo = bool(
            seg.flecha and seg.circulo and (_quitar_acentos(seg.flecha) == _quitar_acentos(seg.circulo))
        )

        trayectoria_flecha: Optional[List[Tuple[float, float]]] = None
        trayectoria_circulo: Optional[List[Tuple[float, float]]] = None

        if seg.circulo:
            trayectoria_circulo = RastreadorObjetivosVideo.calcular_trayectoria(frames_seg_rgb, seg.circulo)
        if seg.flecha:
            if mismo_objetivo and trayectoria_circulo is not None:
                trayectoria_flecha = trayectoria_circulo
            else:
                trayectoria_flecha = RastreadorObjetivosVideo.calcular_trayectoria(frames_seg_rgb, seg.flecha)

        print(
            f"    -> Renderizando segmento {idx_seg + 1}/{len(datos_segmentos)} "
            f"({total_frames_seg} frames | video {t_vid_ini:.1f}s..{t_vid_fin:.1f}s)..."
        )

        for f_idx in range(total_frames_seg):
            t_seg = f_idx / float(FPS)
            rms_val = float(rms_env[f_idx]) if f_idx < len(rms_env) else 0.0
            frame_rgb = frames_seg_rgb[f_idx]

            pt_c_vid = trayectoria_circulo[f_idx] if trayectoria_circulo else (WIDTH / 2.0, HEIGHT * 0.44)
            pt_f_vid = trayectoria_flecha[f_idx] if trayectoria_flecha else pt_c_vid
            foco_camara = pt_c_vid if trayectoria_circulo else (pt_f_vid if trayectoria_flecha else (WIDTH / 2.0, HEIGHT * 0.46))

            lienzo, pts_pantalla = gestor_assets.aplicar_efecto_camara_y_transformar_puntos(
                frame_rgb=frame_rgb,
                efecto=seg.efecto_visual,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
                foco_video=foco_camara,
                puntos_rastreados=[pt_c_vid, pt_f_vid],
            )
            pt_c_screen, pt_f_screen = pts_pantalla[0], pts_pantalla[1]

            # 1) Círculo Rojo siguiendo al objetivo
            radio_circulo = gestor_assets.dibujar_circulo_rojo(
                lienzo=lienzo,
                activo=bool(seg.circulo),
                target_xy=pt_c_screen,
                tamano_mod=seg.tamano_circulo,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 2) Flecha Roja siguiendo al objetivo (si comparte objetivo con el círculo, apunta a su borde)
            radio_para_flecha = radio_circulo if mismo_objetivo else 0.0
            gestor_assets.dibujar_flecha_roja(
                lienzo=lienzo,
                activo=bool(seg.flecha),
                target_xy=pt_f_screen,
                radio_circulo_activo=radio_para_flecha,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 3) Emoji animado (evitando superponerse con el objetivo rastreado)
            target_ref_emoji = pt_c_screen if seg.circulo else (pt_f_screen if seg.flecha else None)
            gestor_assets.dibujar_emoji(
                lienzo=lienzo,
                nombre_emoji=seg.emoji,
                posicion_solicitada=seg.posicion_emoji,
                target_principal_xy=target_ref_emoji,
                t_seg=t_seg,
                dur_seg=dur_seg_exacta,
            )

            # 4) Subtítulos dinámicos ultra llamativos con resplandor neón y pulso reactivo a la voz
            renderizar_subtitulos_luminosos(
                lienzo=lienzo,
                palabras=palabras_sub,
                t_actual=t_seg,
                nivel_voz_rms=rms_val,
                y_centro=1340,
                palabras_verdes_extra=config.palabras_verdes_extra,
                palabras_rojas_extra=config.palabras_rojas_extra,
                palabras_cian_extra=config.palabras_cian_extra,
            )

            if proceso_ffmpeg.poll() is not None:
                f_err.flush()
                f_err.close()
                err_txt = ""
                try:
                    err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    pass
                raise RuntimeError(
                    f"FFmpeg se cerró antes de tiempo con código {proceso_ffmpeg.returncode}.\n"
                    f"Detalles:\n{err_txt}"
                )

            if proceso_ffmpeg.stdin:
                try:
                    proceso_ffmpeg.stdin.write(lienzo.convert("RGB").tobytes())
                except OSError as e:
                    f_err.flush()
                    f_err.close()
                    err_txt = ""
                    try:
                        err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"Error al enviar frame a FFmpeg ({e}).\nDetalles del encoder:\n{err_txt}"
                    ) from e

    if proceso_ffmpeg.stdin:
        try:
            proceso_ffmpeg.stdin.close()
        except Exception:
            pass
    proceso_ffmpeg.wait()
    f_err.flush()
    f_err.close()

    if proceso_ffmpeg.returncode != 0:
        err_txt = ""
        try:
            err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            pass
        raise RuntimeError(f"FFmpeg finalizó con código {proceso_ffmpeg.returncode}.\nDetalles:\n{err_txt}")

    _notificar_prog(1.0, "Renderizado 60 FPS completado con éxito.")
    print("=" * 78)
    print(f"[ÉXITO] Short generado y listo en: {ruta_mp4_final}")
    print("=" * 78)
    return ruta_mp4_final


# ==============================================================================
# 9. DESCARGA CON YT-DLP E INTERFAZ GRÁFICA COMPLETA (APLICACIÓN DE ESCRITORIO)
# ==============================================================================
ULTIMA_INFO_YTDLP: Dict[str, str] = {"titulo": "", "descripcion": ""}


def descargar_video_youtube(url: str) -> Path:
    """
    Descarga el video o Short de YouTube usando yt-dlp en formato MP4 compatible
    y guarda su título/descripción original (`--write-info-json`) para que la IA
    entienda siempre el contexto real exacto de lo que ocurre en el video.
    """
    url_limpia = url.strip()
    if not url_limpia:
        raise ValueError("La URL del video de YouTube está vacía.")

    ULTIMA_INFO_YTDLP["titulo"] = ""
    ULTIMA_INFO_YTDLP["descripcion"] = ""

    for existente in BASE_DIR.glob("video_input.*"):
        try:
            existente.unlink()
        except OSError:
            pass

    ejecutable_ytdlp = shutil.which("yt-dlp")
    if ejecutable_ytdlp:
        cmd_base = [ejecutable_ytdlp]
    else:
        cmd_base = [sys.executable, "-m", "yt_dlp"]

    args_js = ["--js-runtimes", "node"] if shutil.which("node") else []

    cmd = [
        *cmd_base,
        *args_js,
        "--extractor-args", "youtube:player_client=android,web",
        "--write-info-json",
        "-S", "res,ext:mp4:m4a",
        "-o", "video_input.%(ext)s",
        url_limpia,
    ]

    print("=" * 78)
    print(f"[*] Descargando video de YouTube con yt-dlp: {url_limpia}")
    print("=" * 78)

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        for linea in proc.stdout:
            linea_s = linea.rstrip()
            if linea_s:
                print(f"[yt-dlp] {linea_s}")
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp terminó con código {proc.returncode}. Verifica que el link de YouTube sea válido.")

    info_json_path = BASE_DIR / "video_input.info.json"
    if info_json_path.exists():
        try:
            datos_info = json.loads(info_json_path.read_text(encoding="utf-8", errors="replace"))
            ULTIMA_INFO_YTDLP["titulo"] = str(datos_info.get("title") or "").strip()
            ULTIMA_INFO_YTDLP["descripcion"] = str(datos_info.get("description") or "").strip()[:500]
        except Exception:
            pass

    if DEFAULT_VIDEO_INPUT.exists():
        return DEFAULT_VIDEO_INPUT

    descargados = [p for p in sorted(BASE_DIR.glob("video_input.*")) if not p.name.endswith(".json")]
    if descargados:
        return descargados[0]

    raise FileNotFoundError("No se encontró el archivo 'video_input.mp4' luego de la descarga.")


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
    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video para crear el mosaico: {ruta_video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur_seg, _, _, _ = obtener_info_video(ruta_video)
    if dur_seg <= 0 and total_frames > 0:
        dur_seg = total_frames / fps

    num_tiles = cols * rows
    tile_w, tile_h = 270, 480
    mosaico = Image.new("RGB", (cols * tile_w, rows * tile_h), (15, 17, 23))

    for i in range(num_tiles):
        t_sec = min(max(0.15, (i + 0.5) * (dur_seg / num_tiles)), max(0.2, dur_seg - 0.15))
        cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000.0)
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img_tile = Image.fromarray(frame_rgb).resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img_tile)

        # Banda superior oscura con timestamp exacto y guía de zonas
        draw.rectangle([0, 0, tile_w, 34], fill=(0, 0, 0))
        mm = int(t_sec) // 60
        ss = int(t_sec) % 60
        etiqueta = f"#{i + 1} | {mm:02d}:{ss:02d} ({t_sec:.1f}s)"
        draw.text((8, 6), etiqueta, fill=(250, 204, 21))

        # Líneas sutiles divisorias IZQ / CENTRO / DER abajo
        draw.rectangle([0, tile_h - 22, tile_w, tile_h], fill=(0, 0, 0))
        draw.text((10, tile_h - 19), "IZQ        |        CENTRO        |        DER", fill=(180, 190, 210))

        c = i % cols
        r = i // cols
        mosaico.paste(img_tile, (c * tile_w, r * tile_h))

    cap.release()

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

🚫 PROHIBIDO INCLUIR LLAMADAS A LA ACCIÓN (CTA): la voz NUNCA debe pedir "like", "me gusta", "suscríbete", "comenta", "comparte", "sígueme", "activa la campanita" ni nada parecido. El último bloque también debe ser pura narración de lo que ocurre en pantalla (el desenlace o la reacción final), sin despedidas ni pedidos al espectador.
🚫 PROHIBIDO PONER `[SIGUE_SONIDO_ORIGINAL]` O DEJAR BLOQUES SIN NARRACIÓN: La voz en español debe hablar SIEMPRE en TODOS los bloques de principio a fin (para tapar cualquier idioma extranjero o silencio del video original).

Debes entregarme el resultado EXCLUSIVAMENTE en el formato exacto de bloque de texto que se muestra al final, sin explicaciones adicionales ni bloques ```.

================================================================================
⚠️ REGLA CRÍTICA DE TIEMPOS (1x) Y LÍMITE DE PALABRAS POR BLOQUE
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
   - 🚫 **PROHIBIDO escribir más de 20 palabras en un bloque de 5 segundos**, y tampoco menos de 17. Redacta **2 oraciones fluidas, enérgicas y muy expresivas** (con signos `¡!` o `¿?`) por línea que cuenten exactamente lo que está pasando en pantalla en ese instante.

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
5. FLECHA (`flecha.png` con seguimiento de objetivos):
   - Escribe la **coordenada porcentual exacta `X,Y`** (de `15` a `85`, donde `X` es horizontal izq->der y `Y` es vertical arriba->abajo, ej: `28,45` para un objeto a la izquierda, `72,50` a la derecha, `50,38` en el centro-arriba) del objeto o rostro exacto que quieres señalar en ese bloque, o bien `izquierda`, `derecha`, `centro`, `arriba`, `abajo`, o `ninguna`.
   - ⚠️ **FRECUENCIA MODERADA**: usa la flecha solo en **1 o 2 bloques clave del guion como máximo**, dejando el resto en `ninguna`. No pongas flechas en bloques seguidos.
6. CIRCULO (`circulo_rojo.png`):
   - Escribe la **coordenada porcentual exacta `X,Y`** del objeto exacto a rodear (ej: `30,48` o `68,45:grande`), o bien `centro`, `izquierda`, `derecha`, `arriba`, `abajo` (opcional `:grande`), o `ninguno`.
   - ⚠️ **LÍMITE ESTRICTO**: usa el círculo en **1 bloque COMO MÁXIMO** en todo el guion. En todos los demás escribe `ninguno`.
7. TEXTO (Narración de Voz IA continua + Subtítulos Luminosos):
   - Entre **18 y 20 palabras por cada bloque de 5 segundos** con máxima emoción (`¡!`). Narra siempre lo que pasa en el video sin pedir likes ni suscripciones.

================================================================================
PLANTILLA DE ENTREGA OBLIGATORIA:
================================================================================
TITULO_SUPERIOR: [Nombre corto de 4-5 palabras para el archivo MP4, ej: Abuela Venganza Epica Troleo]
TITULO_YOUTUBE: [Título viral llamativo con emojis y #shorts, ej: ¡La mejor venganza de la abuela! 🤣👵 #shorts]
DESCRIPCION_YOUTUBE: [Descripción atrapante de 2 oraciones + pregunta a la audiencia + hashtags #shorts #humor #fail #viral]
ESTADO_PUBLICACION: privado
SCHEDULE: auto
PARA_NINOS: no
MODO_ENCUADRE: full
VOLUMEN_VIDEO_ORIGINAL: 0.16
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
    modelo_preferido: str = "gemini-4-argon",
) -> str:
    """
    Envía el VIDEO COMPLETO comprimido + el mosaico de guía espacial + el contexto
    original del video a la API de Google (soportando Argon 4 `gemini-4-argon`,
    `gemini-3.8-flash` y `gemini-3.5-flash-lite`) usando un ejecutor con timeout
    estricto por hilo para NUNCA quedarse trabado si un servidor de Google tiene
    demanda alta o límite de cuota.
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

    tit_ctx = (contexto_titulo_orig or ULTIMA_INFO_YTDLP.get("titulo") or "").strip()
    desc_ctx = (ULTIMA_INFO_YTDLP.get("descripcion") or "").strip()
    bloque_contexto_real = ""
    if tit_ctx or desc_ctx:
        bloque_contexto_real = (
            f"\n🔎 CONTEXTO REAL DEL VIDEO ORIGINAL (ÚSALO PARA SABER QUÉ SON LOS OBJETOS REALMENTE Y NO ADIVINAR):\n"
            f"- Título original del video: {tit_ctx}\n"
            + (f"- Descripción original: {desc_ctx}\n" if desc_ctx else "")
            + "- ⚠️ IMPORTANTE: Presta mucha atención a lo que hace la persona y qué objetos reales usa (ej. si tiene un control remoto en las manos y maneja juguetes robóticos/magnéticos, o si es una broma física, descríbelo con total exactitud sin confundir juguetes con comida ni inventar cosas que no están).\n"
        )

    instruccion_extra = (
        f"{bloque_contexto_real}\n"
        f"DATOS EXACTOS DEL VIDEO ANALIZADO:\n"
        f"- Duración total exacta del video: {dur_redondeada} segundos (de 00:00 a 00:{dur_redondeada:02d}).\n"
        f"- Divide los bloques de 00:00 hasta 00:{dur_redondeada:02d} en tramos de 5 segundos (18 a 20 palabras por bloque, hablando de corrido sin silencios de principio a fin).\n"
        f"- En ESTADO_PUBLICACION escribe: {modo_privacidad}\n"
        f"- En SCHEDULE escribe: {schedule_str.strip() if schedule_str.strip() else 'no'}\n"
        f"- En PARA_NINOS escribe: no\n"
        f"- En VOLUMEN_VIDEO_ORIGINAL escribe: 0.16 (para mantener la música de fondo suave mientras la voz habla encima todo el tiempo).\n"
        f"- Recuerda usar FLECHA como máximo en 2 bloques clave de todo el guion y CIRCULO como máximo en 1 bloque.\n"
        f"Observa el video completo y el mosaico adjunto y entrega ÚNICAMENTE el bloque de guion:"
    )
    prompt_final = PROMPT_COMPACTO_INTERNO + instruccion_extra

    partes_con_video: List[object] = []
    if video_bytes:
        partes_con_video.append(types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"))
    partes_con_video.append(types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"))
    partes_con_video.append(prompt_final)

    partes_solo_mosaico: List[object] = [
        types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
        prompt_final,
    ]

    # Plan escalonado con timeout duro por hilo (Google requiere timeout HTTP >= 12000 ms):
    # - `gemini-3.6-flash` es el modelo más potente con cuota gratuita activa (`Free Tier`) para Video+Mosaico.
    # - `gemini-4-argon` solo tiene cuota > 0 si la cuenta tiene facturación (Tier 1) activa en Google AI Studio.
    plan_intentos: List[Tuple[str, List[object], float]] = [
        ("gemini-3.6-flash", partes_con_video, 16.0),
        ("gemini-3-flash-preview", partes_con_video, 15.0),
        (modelo_preferido, partes_con_video, 12.0),
        ("gemini-3.5-flash-lite", partes_con_video, 16.0),
        ("gemini-3.6-flash", partes_solo_mosaico, 14.0),
        ("gemini-3.5-flash-lite", partes_solo_mosaico, 15.0),
    ]

    ultimo_err: Optional[Exception] = None
    texto_respuesta = ""

    def _llamar_modelo_una_vez(mod_name: str, contenido_enviar: List[object], timeout_s: float) -> str:
        cli = genai.Client(
            api_key=key_limpia,
            http_options=types.HttpOptions(
                timeout=max(12000, int(timeout_s * 1000)),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        resp = cli.models.generate_content(
            model=mod_name,
            contents=contenido_enviar,
        )
        return (resp.text or "").strip()

    for mod, cont_env, t_lim in plan_intentos:
        ex_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex_pool.submit(_llamar_modelo_una_vez, mod, cont_env, t_lim)
        try:
            modo_lbl = "Video+Mosaico" if len(cont_env) == 3 else "Mosaico+Contexto"
            print(f"[*] Consultando {mod} ({modo_lbl}, máx {int(t_lim)}s)...")
            texto_respuesta = fut.result(timeout=t_lim + 1.5)
            ex_pool.shutdown(wait=False, cancel_futures=True)
            if texto_respuesta and "[GUION]" in texto_respuesta:
                print(f"[+] Respuesta recibida de {mod} correctamente.")
                break
            elif texto_respuesta:
                print(f"[+] Respuesta recibida de {mod}.")
                break
        except Exception as e:
            ultimo_err = e
            ex_pool.shutdown(wait=False, cancel_futures=True)
            print(f"[!] {mod} ocupado o sin cuota en este segundo, pasando al siguiente ({str(e)[:75]})...")

    if not texto_respuesta:
        raise RuntimeError(f"No se pudo obtener respuesta de Gemini: {ultimo_err}")

    # Limpiar posibles bloques markdown ```
    if texto_respuesta.startswith("```"):
        lineas = texto_respuesta.splitlines()
        if lineas and lineas[0].startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].strip().startswith("```"):
            lineas = lineas[:-1]
        texto_respuesta = "\n".join(lineas).strip()

    DEFAULT_GUION_TXT.write_text(texto_respuesta + "\n", encoding="utf-8")
    print(f"[+] ¡Guión generado y guardado en {DEFAULT_GUION_TXT.name}!")
    return texto_respuesta


# ==============================================================================
# 9.5 POOL DE CANALES VIRALES, HISTORIAL ANTI-REPETIDOS Y CUOTA DE API DIARIA
# ==============================================================================
HISTORIAL_USADOS_FILE = BASE_DIR / "videos_usados.json"
CUOTA_DIARIA_FILE = BASE_DIR / "cuota_api_diaria.json"
MAX_SHORTS_YOUTUBE_DIA = 6  # 10.000 unidades YouTube Data API v3 / 1.600 por subida = 6 Shorts gratis/día


def normalizar_url_canal_shorts(entrada: str) -> str:
    """
    Convierte '@NombreCanal', 'NombreCanal' o cualquier URL de canal de YouTube
    en la URL directa a su pestaña '/shorts'.
    """
    s = entrada.strip().strip('"').rstrip("/")
    if not s:
        return ""
    if s.startswith("@"):
        return f"https://www.youtube.com/{s}/shorts"
    if not s.startswith(("http://", "https://")):
        if "youtube.com" in s or "youtu.be" in s:
            s = "https://" + s
        else:
            return f"https://www.youtube.com/@{s.lstrip('@')}/shorts"
    # Quitar sufijos previos (/videos, /featured, /streams) y asegurar /shorts
    for suf in ("/shorts", "/videos", "/featured", "/streams", "/community", "/playlists"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)]
            break
    return f"{s}/shorts"


def etiqueta_corta_canal(url_canal: str) -> str:
    m = re.search(r"(@[^/?#]+)", url_canal)
    if m:
        return m.group(1)
    partes = [p for p in url_canal.replace("/shorts", "").split("/") if p]
    return partes[-1] if partes else url_canal


def cargar_videos_usados() -> Set[str]:
    if HISTORIAL_USADOS_FILE.exists():
        try:
            datos = json.loads(HISTORIAL_USADOS_FILE.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                return set(str(x) for x in datos)
        except Exception:
            pass
    return set()


def registrar_video_usado(video_id_o_url: str) -> None:
    usados = cargar_videos_usados()
    vid = video_id_o_url.strip()
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", vid)
    if m:
        usados.add(m.group(1))
    else:
        usados.add(vid)
    try:
        HISTORIAL_USADOS_FILE.write_text(json.dumps(sorted(usados), indent=2), encoding="utf-8")
    except Exception:
        pass


def _fecha_cuota_pacifico_iso() -> str:
    """
    La cuota de YouTube Data API v3 se reinicia todos los días a las 00:00 Pacific Time (UTC-7/UTC-8).
    """
    import datetime as _dt
    tz_pt = _dt.timezone(_dt.timedelta(hours=-7))
    return _dt.datetime.now(tz_pt).strftime("%Y-%m-%d")


def _cargar_datos_cuota_raw() -> Dict[str, object]:
    if CUOTA_DIARIA_FILE.exists():
        try:
            return json.loads(CUOTA_DIARIA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def obtener_max_shorts_pool_dia() -> Tuple[int, int]:
    """
    Devuelve `(max_shorts_dia_total, cantidad_proyectos_api)` según cuántos archivos
    `client_secrets*.json` únicos haya cargados en el Pool (`apis_google/` + principal).
    Cada proyecto de Google Cloud aporta 6 Shorts gratis por día.
    """
    try:
        from subir_a_youtube import listar_archivos_credenciales_pool
        n_apis = max(1, len(listar_archivos_credenciales_pool()))
    except Exception:
        n_apis = 1
    return n_apis * MAX_SHORTS_YOUTUBE_DIA, n_apis


def obtener_estado_cuota_diaria() -> Tuple[int, int, float]:
    """
    Devuelve (usados_hoy, disponibles_restantes, porcentaje_disponible_0_a_1).
    Se reinicia automáticamente cada nuevo día de cuota (Pacific Time), escala con
    la cantidad de proyectos API cargados en el Pool (6 Shorts x N APIs) y excluye
    los videos que fueron subidos ayer pero programados para salir hoy.
    """
    import datetime as _dt
    max_total, _ = obtener_max_shorts_pool_dia()
    hoy_pt = _fecha_cuota_pacifico_iso()
    hoy_local = _dt.date.today().strftime("%Y-%m-%d")
    d = _cargar_datos_cuota_raw()
    usados_hoy = 0
    if d.get("fecha") in (hoy_pt, hoy_local):
        ids_hoy = d.get("ids_subidos_hoy")
        if isinstance(ids_hoy, list):
            usados_hoy = max(int(d.get("subidos", 0)), len(ids_hoy))
        else:
            usados_hoy = int(d.get("subidos", 0))
    restantes = max(0, max_total - usados_hoy)
    pct_disp = restantes / float(max(1, max_total))
    return usados_hoy, restantes, pct_disp


def incrementar_cuota_diaria(video_id: Optional[str] = None) -> None:
    """
    Registra que se consumieron 1,600 unidades de cuota HOY al ejecutar `videos.insert`,
    guardando el `video_id` en el historial de subidas para que mañana, cuando el video
    se haga público por programación (`publishAt`), NO se vuelva a descontar como gasto
    de mañana.
    """
    hoy_pt = _fecha_cuota_pacifico_iso()
    d = _cargar_datos_cuota_raw()
    historial: Dict[str, str] = dict(d.get("historial_ids_fecha_subida") or {})
    ids_hoy: List[str] = list(d.get("ids_subidos_hoy") or []) if d.get("fecha") == hoy_pt else []

    usados, _, _ = obtener_estado_cuota_diaria()
    nuevo_usados = usados + 1

    if video_id:
        vid_clean = str(video_id).strip()
        historial[vid_clean] = hoy_pt
        if vid_clean not in ids_hoy:
            ids_hoy.append(vid_clean)
        nuevo_usados = max(nuevo_usados, len(ids_hoy))

    try:
        CUOTA_DIARIA_FILE.write_text(
            json.dumps(
                {
                    "fecha": hoy_pt,
                    "subidos": nuevo_usados,
                    "ids_subidos_hoy": ids_hoy,
                    "historial_ids_fecha_subida": historial,
                    "sincronizado_yt": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def sincronizar_cuota_real_youtube() -> Tuple[int, int, float]:
    """
    Consulta directamente a la API de Google/YouTube los videos del canal para
    contar cuántos tokens se gastaron HOY (en el día de cuota actual, Pacific Time).
    IMPORTANTE:
    - En YouTube, `snippet.publishedAt` dentro de la playlist `uploads` es el momento
      exacto en que el archivo fue SUBIDO a los servidores (momento en que se gastaron
      los tokens), mientras que `status.publishAt` es la fecha futura programada.
    - Además, cruzamos con `historial_ids_fecha_subida`: si un video fue subido ayer
      programado para hoy, queda etiquetado con la fecha de ayer y JAMÁS descuenta
      tokens del día de hoy.
    """
    import datetime as _dt
    tz_pt = _dt.timezone(_dt.timedelta(hours=-7))
    hoy_pt_date = _dt.datetime.now(tz_pt).date()
    hoy_pt_iso = hoy_pt_date.strftime("%Y-%m-%d")

    d_prev = _cargar_datos_cuota_raw()
    historial: Dict[str, str] = dict(d_prev.get("historial_ids_fecha_subida") or {})
    ids_hoy_prev: List[str] = (
        list(d_prev.get("ids_subidos_hoy") or []) if d_prev.get("fecha") == hoy_pt_iso else []
    )
    usados_local, _, _ = obtener_estado_cuota_diaria()

    ids_detectados_hoy: Set[str] = set(ids_hoy_prev)
    try:
        from subir_a_youtube import obtener_servicio_youtube, listar_cuentas_vinculadas
        cuentas_v = listar_cuentas_vinculadas()
        for c_item in cuentas_v:
            cid_chk = str(c_item.get("id") or "principal")
            try:
                yt = obtener_servicio_youtube(cuenta_id=cid_chk)
                ch_resp = yt.channels().list(mine=True, part="contentDetails").execute()
                items_ch = ch_resp.get("items", [])
                if items_ch:
                    uploads_id = items_ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
                    pl_resp = yt.playlistItems().list(
                        playlistId=uploads_id,
                        part="snippet,contentDetails",
                        maxResults=25,
                    ).execute()
                    for it in pl_resp.get("items", []):
                        vid_id = (
                            it.get("contentDetails", {}).get("videoId")
                            or it.get("snippet", {}).get("resourceId", {}).get("videoId")
                            or ""
                        ).strip()
                        if not vid_id:
                            continue

                        # Si ya sabemos que este video se subió en una fecha anterior, NO gasta cuota hoy
                        fecha_conocida = historial.get(vid_id)
                        if fecha_conocida and fecha_conocida != hoy_pt_iso:
                            continue
                        if fecha_conocida == hoy_pt_iso:
                            ids_detectados_hoy.add(vid_id)
                            continue

                        # `snippet.publishedAt` en playlistItems es la fecha/hora de subida del item a la playlist uploads
                        upload_str = it.get("snippet", {}).get("publishedAt") or ""
                        if not upload_str:
                            continue
                        try:
                            dt_utc = _dt.datetime.fromisoformat(upload_str.replace("Z", "+00:00"))
                            dt_pt = dt_utc.astimezone(tz_pt)
                            fecha_item_iso = dt_pt.date().strftime("%Y-%m-%d")
                            historial[vid_id] = fecha_item_iso
                            if dt_pt.date() == hoy_pt_date:
                                ids_detectados_hoy.add(vid_id)
                        except Exception:
                            continue
            except Exception:
                continue

        real_usados = max(usados_local, len(ids_detectados_hoy))
        CUOTA_DIARIA_FILE.write_text(
            json.dumps(
                {
                    "fecha": hoy_pt_iso,
                    "subidos": real_usados,
                    "ids_subidos_hoy": sorted(ids_detectados_hoy),
                    "historial_ids_fecha_subida": historial,
                    "sincronizado_yt": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return obtener_estado_cuota_diaria()


def buscar_short_viral_en_canal(
    url_canal: str,
    min_views: int = 1_000_000,
    max_escanear: int = 45,
) -> Optional[Tuple[str, str, int]]:
    """
    Escanea rápidamente la pestaña /shorts de un canal con yt-dlp (--flat-playlist)
    y devuelve el primer Short NO usado previamente que supere `min_views`.
    Retorna (url_short, titulo, view_count) o None.
    """
    url_shorts = normalizar_url_canal_shorts(url_canal)
    if not url_shorts:
        return None

    usados = cargar_videos_usados()
    ejecutable_ytdlp = shutil.which("yt-dlp")
    cmd_base = [ejecutable_ytdlp] if ejecutable_ytdlp else [sys.executable, "-m", "yt_dlp"]

    cmd = [
        *cmd_base,
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(max_escanear),
        url_shorts,
    ]
    print(f"[*] Escaneando Shorts virales en {etiqueta_corta_canal(url_shorts)} (mínimo {min_views:,} vistas)...")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=28,
        )
    except Exception as e:
        print(f"[!] Error al escanear canal {url_shorts}: {e}")
        return None

    candidatos: List[Tuple[str, str, int]] = []
    respaldo_sin_min: List[Tuple[str, str, int]] = []
    for linea in proc.stdout.splitlines():
        linea_s = linea.strip()
        if not linea_s.startswith("{"):
            continue
        try:
            item = json.loads(linea_s)
            vid_id = str(item.get("id") or "").strip()
            if not vid_id or vid_id in usados:
                continue
            vistas = int(item.get("view_count") or 0)
            titulo = str(item.get("title") or vid_id)
            url_v = f"https://www.youtube.com/shorts/{vid_id}"
            if vistas >= min_views:
                candidatos.append((url_v, titulo, vistas))
            else:
                respaldo_sin_min.append((url_v, titulo, vistas))
        except Exception:
            continue

    if candidatos:
        elegido = candidatos[0]
        print(f"[+] Short viral encontrado: '{elegido[1]}' ({elegido[2]:,} vistas) -> {elegido[0]}")
        return elegido

    if respaldo_sin_min:
        # Si ningún video reciente superó el umbral pero hay videos sin usar, ordenar por el más visto
        respaldo_sin_min.sort(key=lambda x: x[2], reverse=True)
        mejor = respaldo_sin_min[0]
        print(
            f"[!] Ningún Short reciente superó {min_views:,} vistas; "
            f"eligiendo el más visto disponible ({mejor[2]:,} vistas): '{mejor[1]}'"
        )
        return mejor

    return None


HORARIOS_PICO_OPTIMOS: Dict[int, List[str]] = {
    1: ["19:00"],
    2: ["13:00", "20:00"],
    3: ["12:30", "17:30", "21:00"],
    4: ["11:00", "15:00", "18:30", "21:30"],
    5: ["10:00", "13:00", "16:00", "19:00", "22:00"],
    6: ["09:30", "12:00", "14:30", "17:00", "19:30", "22:00"],
}


def calcular_horarios_inteligentes(
    cantidad_total: int,
    por_dia: int,
    fecha_base_iso: str,
    modo_horario: str = "🔥 Horarios Pico (Auto)",
    hora_inicio: str = "13:00",
    intervalo_hs: int = 8,
) -> List[str]:
    """
    Calcula la agenda exacta ('YYYY-MM-DD HH:MM') para `cantidad_total` Shorts
    respetando un máximo de `por_dia` salidas por fecha y asegurando que NUNCA
    salgan dos videos al mismo tiempo:
    - En modo '🔥 Horarios Pico (Auto)': usa los mejores horarios virales según la
      cantidad diaria elegida (1 a 6 por día).
    - En modo '⏱️ Cada X hs (Desde mi Hora)': arranca desde `hora_inicio` y suma
      `intervalo_hs` entre cada Short hasta completar `por_dia` en ese día, pasando
      luego al día siguiente.
    """
    import datetime as _dt
    ahora = _dt.datetime.now()
    limite_minimo = ahora + _dt.timedelta(minutes=12)

    try:
        d_base = _dt.date.fromisoformat(fecha_base_iso)
    except Exception:
        d_base = ahora.date()
    if d_base < ahora.date():
        d_base = ahora.date()

    cantidad_total = max(1, min(18, int(cantidad_total)))
    por_dia = max(1, min(6, int(por_dia)))
    intervalo_hs = max(1, min(24, int(intervalo_hs)))

    slots: List[str] = []

    if "Pico" in modo_horario:
        horas_del_dia = HORARIOS_PICO_OPTIMOS.get(por_dia, HORARIOS_PICO_OPTIMOS[2])
        d_cursor = d_base
        guard = 0
        while len(slots) < cantidad_total and guard < 60:
            guard += 1
            for h_str in horas_del_dia:
                hh, mm = [int(x) for x in h_str.split(":", 1)]
                dt_cand = _dt.datetime(d_cursor.year, d_cursor.month, d_cursor.day, hh, mm)
                if dt_cand > limite_minimo:
                    slots.append(dt_cand.strftime("%Y-%m-%d %H:%M"))
                    if len(slots) >= cantidad_total:
                        break
            d_cursor += _dt.timedelta(days=1)
        return slots

    # Modo "⏱️ Cada X hs (Desde mi Hora)"
    try:
        hh_ini, mm_ini = [int(x) for x in hora_inicio.strip().split(":", 1)]
    except Exception:
        hh_ini, mm_ini = 13, 0

    d_cursor = d_base
    guard = 0
    while len(slots) < cantidad_total and guard < 60:
        guard += 1
        dt_dia_ini = _dt.datetime(d_cursor.year, d_cursor.month, d_cursor.day, hh_ini, mm_ini)
        subidos_en_este_dia = 0
        for idx_en_dia in range(por_dia):
            dt_cand = dt_dia_ini + _dt.timedelta(hours=idx_en_dia * intervalo_hs)
            # Si al sumar horas se pasa al día siguiente, igual es válido y mantiene el espaciado
            if dt_cand > limite_minimo:
                cand_str = dt_cand.strftime("%Y-%m-%d %H:%M")
                if not slots or cand_str > slots[-1]:
                    slots.append(cand_str)
                    subidos_en_este_dia += 1
                    if len(slots) >= cantidad_total:
                        break
        d_cursor += _dt.timedelta(days=1)

    return slots


def iniciar_aplicacion_gui() -> None:
    import calendar as _cal
    import datetime as _dt
    import json as _json
    import queue
    import random
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import webbrowser
    import customtkinter as ctk

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mateo.EditorShortsStudio.BlueIcon.v2")
    except Exception:
        pass

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Shorts Studio")
    root.geometry("860x790")
    root.minsize(800, 680)
    root.configure(fg_color="#0b0d13")

    _ico_azul = BASE_DIR / "icono_ctk_azul.ico"
    if _ico_azul.exists():
        def _forzar_icono_azul() -> None:
            try:
                root.wm_iconbitmap(default=str(_ico_azul))
                root.iconbitmap(str(_ico_azul))
            except Exception:
                pass
            try:
                from PIL import Image, ImageTk
                im_ico = Image.open(_ico_azul)
                photo_ico = ImageTk.PhotoImage(im_ico)
                root._icono_tk_ref = photo_ico  # type: ignore[attr-defined]
                root.wm_iconphoto(True, photo_ico)
            except Exception:
                pass
            try:
                import ctypes
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                WM_SETICON = 0x0080
                ICON_SMALL = 0
                ICON_BIG = 1
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
                hicon_big = ctypes.windll.user32.LoadImageW(None, str(_ico_azul), IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
                hicon_sm = ctypes.windll.user32.LoadImageW(None, str(_ico_azul), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                if hicon_big:
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                if hicon_sm:
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
            except Exception:
                pass

        _forzar_icono_azul()
        root.after(220, _forzar_icono_azul)
        root.after(600, _forzar_icono_azul)

    cola_logs: "queue.Queue[str]" = queue.Queue()
    editando_lock = threading.Lock()
    ultimo_video_generado: List[Optional[Path]] = [None]

    BG_DARK = "#0b0d13"
    CARD_BG = "#141824"
    CARD_BORDER = "#252b3d"
    INPUT_BG = "#0e111a"
    TEXT_MAIN = "#f8fafc"
    TEXT_MUTED = "#94a3b8"
    TEXT_DIM = "#64748b"
    PURPLE_MAIN = "#7c3aed"
    PURPLE_HOVER = "#6d28d9"
    CYAN_ACCENT = "#38bdf8"
    GREEN_ACCENT = "#10b981"

    SCHEDULE_MEM_FILE = BASE_DIR / "ultimo_schedule.json"
    MESES_ES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    DIAS_CORTOS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    encuadre_map = {
        "Pantalla Completa Vertical (Crop 9:16)": "full",
        "Fondo Borroso para Horizontales (Blur 9:16)": "blur",
    }

    MAPA_MODELOS_IA = {
        "Gemini 3.6 Flash (Máxima Inteligencia Gratis · Video Completo)": "gemini-3.6-flash",
        "Argon 4 (gemini-4-argon · Requiere Tier 1 en AI Studio)": "gemini-4-argon",
        "Gemini 3.8 Flash (Rápido y Preciso)": "gemini-3.8-flash",
        "Gemini 3.5 Flash Lite (Ultra Rápido)": "gemini-3.5-flash-lite",
    }

    def _cargar_memoria() -> Dict[str, object]:
        manana = _dt.date.today() + _dt.timedelta(days=1)
        def_data: Dict[str, object] = {
            "activar_schedule": True,
            "fecha": manana.strftime("%Y-%m-%d"),
            "hora": "13:00",
            "privacidad": "Privado",
            "voz": list(VOCES_DISPONIBLES.keys())[0],
            "encuadre": list(encuadre_map.keys())[0],
            "modo_fuente": "Canales Automáticos",
            "modo_contenido": "IA Automática",
            "modelo_ia": list(MAPA_MODELOS_IA.keys())[0],
            "orden_canales": "Rotación (En fila)",
            "min_views_millones": "1.0M+ vistas",
            "cantidad_total": "2 Shorts",
            "shorts_por_dia": "2 / día",
            "modo_horario": "🔥 Horarios Pico (Auto)",
            "intervalo_horas": "Cada 8h",
            "cuenta_destino": "Canal Principal",
            "modo_cuentas": "una",
            "cuenta_activa_id": "",
            "grupo_cuentas_ids": [],
            "canales_por_cuenta": {},
            "canales": [],
            "indice_rotacion": 0,
            "custom_reels": [],
        }
        if SCHEDULE_MEM_FILE.exists():
            try:
                leido = _json.loads(SCHEDULE_MEM_FILE.read_text(encoding="utf-8"))
                fecha_str = str(leido.get("fecha", def_data["fecha"]))
                f_parsed = _dt.date.fromisoformat(fecha_str)
                if f_parsed < _dt.date.today():
                    f_parsed = _dt.date.today()
                return {
                    "activar_schedule": bool(leido.get("activar_schedule", True)),
                    "fecha": f_parsed.strftime("%Y-%m-%d"),
                    "hora": str(leido.get("hora", "13:00")),
                    "privacidad": str(leido.get("privacidad", "Privado")),
                    "voz": str(leido.get("voz", def_data["voz"])),
                    "encuadre": str(leido.get("encuadre", def_data["encuadre"])),
                    "modo_fuente": str(leido.get("modo_fuente", "Canales Automáticos")),
                    "modo_contenido": str(leido.get("modo_contenido", "IA Automática")),
                    "modelo_ia": str(leido.get("modelo_ia", def_data["modelo_ia"])),
                    "orden_canales": str(leido.get("orden_canales", "Rotación (En fila)")),
                    "min_views_millones": str(leido.get("min_views_millones", "1.0M+ vistas")),
                    "cantidad_total": str(leido.get("cantidad_total", "2 Shorts")),
                    "shorts_por_dia": str(leido.get("shorts_por_dia", "2 / día")),
                    "modo_horario": str(leido.get("modo_horario", "🔥 Horarios Pico (Auto)")),
                    "intervalo_horas": str(leido.get("intervalo_horas", "Cada 8h")),
                    "cuenta_destino": str(leido.get("cuenta_destino", "Canal Principal")),
                    "modo_cuentas": str(leido.get("modo_cuentas", "una")),
                    "cuenta_activa_id": str(leido.get("cuenta_activa_id", "")),
                    "grupo_cuentas_ids": list(leido.get("grupo_cuentas_ids", [])),
                    "canales_por_cuenta": dict(leido.get("canales_por_cuenta") or {}),
                    "canales": list(leido.get("canales", [])),
                    "indice_rotacion": int(leido.get("indice_rotacion", 0)),
                    "custom_reels": list(leido.get("custom_reels", [])),
                }
            except Exception:
                pass
        return def_data

    mem = _cargar_memoria()

    programar_var = tk.BooleanVar(value=bool(mem["activar_schedule"]))
    fecha_elegida_var = tk.StringVar(value=str(mem["fecha"]))
    hora_elegida_var = tk.StringVar(value=str(mem["hora"]))
    privacidad_var = tk.StringVar(value=str(mem["privacidad"]))
    voz_var = tk.StringVar(value=str(mem["voz"]))
    encuadre_var = tk.StringVar(value=str(mem["encuadre"]))
    modo_fuente_var = tk.StringVar(value=str(mem["modo_fuente"]))
    modo_contenido_var = tk.StringVar(value=str(mem["modo_contenido"]))
    modelo_ia_var = tk.StringVar(value=str(mem["modelo_ia"]))
    orden_canales_var = tk.StringVar(value=str(mem["orden_canales"]))
    min_views_var = tk.StringVar(value=str(mem["min_views_millones"]))
    cantidad_total_var = tk.StringVar(value=str(mem["cantidad_total"]))
    shorts_por_dia_var = tk.StringVar(value=str(mem["shorts_por_dia"]))
    modo_horario_var = tk.StringVar(value=str(mem["modo_horario"]))
    intervalo_horas_var = tk.StringVar(value=str(mem["intervalo_horas"]))
    cuenta_destino_var = tk.StringVar(value=str(mem.get("cuenta_destino", "Canal Principal")))
    lista_canales: List[str] = [str(c) for c in (mem.get("canales") or []) if str(c).strip()]
    estado_rotacion = {"idx": int(mem.get("indice_rotacion", 0))}
    mapa_cuentas_ui: Dict[str, str] = {}

    # Estado multi-cuenta y canales fuente guardados individualmente por cuenta de YouTube
    canales_por_cuenta: Dict[str, List[str]] = {}
    raw_cpc = mem.get("canales_por_cuenta")
    if isinstance(raw_cpc, dict):
        for k_cp, v_cp in raw_cpc.items():
            if isinstance(v_cp, list):
                canales_por_cuenta[str(k_cp)] = [str(x) for x in v_cp if str(x).strip()]

    estado_seleccion_cuentas: Dict[str, object] = {
        "modo": str(mem.get("modo_cuentas") or "una"),  # "una" | "todas" | "grupo"
        "cuenta_id": str(mem.get("cuenta_activa_id") or ""),
        "grupo_ids": [str(x) for x in (mem.get("grupo_cuentas_ids") or []) if str(x).strip()],
    }
    cache_avatares_ctk: Dict[str, ctk.CTkImage] = {}

    # Lista de diccionarios para personalizar cada Reel individualmente (hasta 12 Shorts)
    datos_custom_reels: List[Dict[str, str]] = []
    raw_custom = mem.get("custom_reels")
    if isinstance(raw_custom, list):
        for item_c in raw_custom:
            if isinstance(item_c, dict):
                datos_custom_reels.append(
                    {
                        "titulo": str(item_c.get("titulo") or ""),
                        "descripcion": str(item_c.get("descripcion") or ""),
                        "guion": str(item_c.get("guion") or ""),
                    }
                )
    while len(datos_custom_reels) < 12:
        datos_custom_reels.append({"titulo": "", "descripcion": "", "guion": ""})
    estado_reel_custom = {"idx": 0, "cargando": False}

    MAPA_MIN_VIEWS = {
        "100K+ vistas": 100_000,
        "500K+ vistas": 500_000,
        "1.0M+ vistas": 1_000_000,
        "5.0M+ vistas": 5_000_000,
        "Sin mínimo": 0,
    }

    MAPA_CANTIDAD_TOTAL = {
        "1 Short": 1,
        "2 Shorts": 2,
        "3 Shorts": 3,
        "4 Shorts": 4,
        "5 Shorts": 5,
        "6 Shorts": 6,
        "8 Shorts": 8,
        "10 Shorts": 10,
        "12 Shorts": 12,
    }

    MAPA_POR_DIA = {
        "1 / día": 1,
        "2 / día": 2,
        "3 / día": 3,
        "4 / día": 4,
        "5 / día": 5,
        "6 / día": 6,
        "8 / día": 8,
        "10 / día": 10,
        "12 / día": 12,
    }

    MAPA_INTERVALO_HS = {
        "Cada 3h": 3,
        "Cada 4h": 4,
        "Cada 6h": 6,
        "Cada 8h": 8,
        "Cada 12h": 12,
    }

    def _guardar_memoria(*_args: object) -> None:
        try:
            cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "")
            if cid_act and str(estado_seleccion_cuentas.get("modo") or "una") == "una":
                canales_por_cuenta[cid_act] = list(lista_canales)
            SCHEDULE_MEM_FILE.write_text(
                _json.dumps(
                    {
                        "activar_schedule": programar_var.get(),
                        "fecha": fecha_elegida_var.get(),
                        "hora": hora_elegida_var.get(),
                        "privacidad": privacidad_var.get(),
                        "voz": voz_var.get(),
                        "encuadre": encuadre_var.get(),
                        "modo_fuente": modo_fuente_var.get(),
                        "modo_contenido": modo_contenido_var.get(),
                        "modelo_ia": modelo_ia_var.get(),
                        "orden_canales": orden_canales_var.get(),
                        "min_views_millones": min_views_var.get(),
                        "cantidad_total": cantidad_total_var.get(),
                        "shorts_por_dia": shorts_por_dia_var.get(),
                        "modo_horario": modo_horario_var.get(),
                        "intervalo_horas": intervalo_horas_var.get(),
                        "cuenta_destino": cuenta_destino_var.get(),
                        "modo_cuentas": estado_seleccion_cuentas.get("modo", "una"),
                        "cuenta_activa_id": estado_seleccion_cuentas.get("cuenta_id", ""),
                        "grupo_cuentas_ids": estado_seleccion_cuentas.get("grupo_ids", []),
                        "canales_por_cuenta": canales_por_cuenta,
                        "canales": lista_canales,
                        "indice_rotacion": estado_rotacion["idx"],
                        "custom_reels": datos_custom_reels[:12],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _formatear_boton_fecha(iso_str: str) -> str:
        try:
            d = _dt.date.fromisoformat(iso_str)
            hoy = _dt.date.today()
            pref = " · Hoy" if d == hoy else (" · Mañana" if d == hoy + _dt.timedelta(days=1) else "")
            return f"📅  {d.day:02d} {MESES_ES[d.month][:3]} {d.year}{pref}"
        except Exception:
            return f"📅  {iso_str}"

    # ==========================================================================
    # ENCABEZADO SUPERIOR + BARRA DE CUOTA DIARIA REAL DE GOOGLE + BOTÓN AJUSTES
    # ==========================================================================
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.pack(fill="x", padx=28, pady=(16, 8))

    title_box = ctk.CTkFrame(header, fg_color="transparent")
    title_box.pack(side="left")

    ctk.CTkLabel(
        title_box,
        text="⚡ Shorts Studio",
        font=ctk.CTkFont(family="Segoe UI", size=23, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(anchor="w")

    ctk.CTkLabel(
        title_box,
        text="Piloto automático de Shorts virales con IA",
        font=ctk.CTkFont(family="Segoe UI", size=12),
        text_color=TEXT_MUTED,
    ).pack(anchor="w")

    # Tarjeta Píldora Compacta de Shorts Restantes Hoy + Botón '+' para agregar API JSON (+6 Shorts/día)
    quota_pill = ctk.CTkFrame(header, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
    quota_pill.pack(side="right", padx=(10, 0), pady=4)

    quota_top = ctk.CTkFrame(quota_pill, fg_color="transparent")
    quota_top.pack(fill="both", expand=True, padx=10, pady=4)

    def agregar_api_json_gui(parent_win: Optional[tk.Misc] = None) -> None:
        from tkinter import filedialog
        import shutil as _shutil

        ruta_sel = filedialog.askopenfilename(
            parent=parent_win or root,
            title="Selecciona un archivo client_secrets.json de otro proyecto Google Cloud (+6 Shorts/día)",
            filetypes=[("Credenciales OAuth Google", "*.json"), ("Todos los archivos", "*.*")],
        )
        if not ruta_sel:
            return
        try:
            p_origen = Path(ruta_sel)
            raw_j = _json.loads(p_origen.read_text(encoding="utf-8"))
            info_j = raw_j.get("installed") or raw_j.get("web") or {}
            cid = str(info_j.get("client_id") or "").strip()
            if not cid:
                messagebox.showwarning(
                    "Archivo inválido",
                    "El archivo JSON seleccionado no parece ser un client_secrets.json OAuth válido de Google Cloud.",
                    parent=parent_win or root,
                )
                return
            dir_apis = BASE_DIR / "apis_google"
            dir_apis.mkdir(parents=True, exist_ok=True)
            pref_id = re.sub(r"[^a-zA-Z0-9]", "", cid[:12])
            destino = dir_apis / f"client_secrets_{pref_id}.json"
            _shutil.copy2(p_origen, destino)
            refrescar_barra_cuota()
            max_n, cant_n = obtener_max_shorts_pool_dia()
            messagebox.showinfo(
                "API Agregada (+6 Shorts/día)",
                f"¡Proyecto Google Cloud sumado al Pool!\n\nAhora tienes {cant_n} API(s) activas = hasta {max_n} Shorts por día.",
                parent=parent_win or root,
            )
        except Exception as e_ap:
            messagebox.showerror("Error", f"No se pudo importar el archivo JSON:\n{e_ap}", parent=parent_win or root)

    btn_cuota_info = ctk.CTkButton(
        quota_top,
        text="🔋 6/6 Shorts hoy",
        command=lambda: agregar_api_json_gui(root),
        height=30,
        corner_radius=14,
        fg_color="transparent",
        hover_color="#1f2637",
        text_color=GREEN_ACCENT,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    btn_cuota_info.pack(side="left", padx=(2, 4))

    btn_add_api_top = ctk.CTkButton(
        quota_top,
        text="+",
        command=lambda: agregar_api_json_gui(root),
        width=28,
        height=28,
        corner_radius=14,
        fg_color=PURPLE_MAIN,
        hover_color=PURPLE_HOVER,
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
    )
    btn_add_api_top.pack(side="left", padx=(0, 2))

    def refrescar_barra_cuota() -> None:
        max_tot, n_apis = obtener_max_shorts_pool_dia()
        usados_h, disp_h, _pct = obtener_estado_cuota_diaria()
        color_b = GREEN_ACCENT if disp_h >= 3 else ("#facc15" if disp_h >= 1 else "#ef4444")
        btn_cuota_info.configure(
            text=f"🔋 {disp_h}/{max_tot} Shorts restantes",
            text_color=color_b,
        )

    def sincronizar_cuota_async() -> None:
        btn_cuota_info.configure(text="🔄 Sincronizando...", text_color=CYAN_ACCENT)

        def _worker_sync() -> None:
            sincronizar_cuota_real_youtube()
            root.after(0, refrescar_barra_cuota)

        threading.Thread(target=_worker_sync, daemon=True).start()

    btn_sync_api = ctk.CTkButton(
        quota_top,
        text="🔄",
        command=sincronizar_cuota_async,
        width=26,
        height=28,
        corner_radius=14,
        fg_color="transparent",
        hover_color="#252d42",
        text_color=CYAN_ACCENT,
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    btn_sync_api.pack(side="right", padx=(2, 0))

    refrescar_barra_cuota()
    root.after(400, sincronizar_cuota_async)

    # Contenedor dinámico del Paso 1 (alterna entre Modo Canales y Modo Link según Ajustes)
    contenedor_paso1 = ctk.CTkFrame(root, fg_color="transparent")
    contenedor_paso1.pack(fill="x", padx=28, pady=(0, 10))

    # --- TARJETA MODO A: POOL DE CANALES FUENTE ---
    card_canales = ctk.CTkFrame(contenedor_paso1, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)

    top_canales = ctk.CTkFrame(card_canales, fg_color="transparent")
    top_canales.pack(fill="x", padx=20, pady=(12, 6))

    lbl_titulo_canales = ctk.CTkLabel(
        top_canales,
        text="📺  Canales Fuente de Shorts Virales",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color=TEXT_MAIN,
    )
    lbl_titulo_canales.pack(side="left")

    lbl_modo_orden = ctk.CTkLabel(
        top_canales,
        text="",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=CYAN_ACCENT,
    )
    lbl_modo_orden.pack(side="right")

    add_canal_row = ctk.CTkFrame(card_canales, fg_color="transparent")
    add_canal_row.pack(fill="x", padx=20, pady=(0, 8))

    entry_nuevo_canal = ctk.CTkEntry(
        add_canal_row,
        placeholder_text="Pega el link del canal (https://youtube.com/@canal) o escribe @canal...",
        corner_radius=16,
        height=38,
        fg_color=INPUT_BG,
        border_width=1,
        border_color="#2a3147",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Consolas", size=12),
    )
    entry_nuevo_canal.pack(side="left", fill="x", expand=True, padx=(0, 8))

    chips_scroll = ctk.CTkScrollableFrame(
        card_canales,
        height=58,
        corner_radius=14,
        fg_color=INPUT_BG,
        border_width=1,
        border_color="#1f2537",
        orientation="horizontal",
    )
    chips_scroll.pack(fill="x", padx=20, pady=(0, 12))

    def renderizar_chips_canales() -> None:
        for w in chips_scroll.winfo_children():
            w.destroy()
        lbl_modo_orden.configure(text=f"🔄 {orden_canales_var.get()}  ·  🔥 {min_views_var.get()}")
        if not lista_canales:
            ctk.CTkLabel(
                chips_scroll,
                text="Aún no agregaste canales. Pega el link de un canal arriba y toca '+ Agregar'.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED,
            ).pack(padx=12, pady=12)
            return

        for idx_c, c_url in enumerate(lista_canales):
            es_turno = (idx_c == (estado_rotacion["idx"] % len(lista_canales))) and ("Rotación" in orden_canales_var.get())
            chip = ctk.CTkFrame(
                chips_scroll,
                fg_color="#251d42" if es_turno else "#1b2234",
                corner_radius=14,
                border_width=1,
                border_color=PURPLE_MAIN if es_turno else "#2c3652",
            )
            chip.pack(side="left", padx=5, pady=6)

            pref_turno = "▶ " if es_turno else ""
            ctk.CTkLabel(
                chip,
                text=f"{pref_turno}{idx_c + 1}. {etiqueta_corta_canal(c_url)}",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#ffffff" if es_turno else TEXT_MAIN,
            ).pack(side="left", padx=(12, 6), pady=4)

            def _quitar_c(u: str = c_url) -> None:
                if u in lista_canales:
                    lista_canales.remove(u)
                    _guardar_memoria()
                    renderizar_chips_canales()

            ctk.CTkButton(
                chip,
                text="✕",
                width=22,
                height=22,
                corner_radius=11,
                fg_color="transparent",
                hover_color="#dc2626",
                text_color=TEXT_MUTED,
                command=_quitar_c,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).pack(side="right", padx=(0, 6), pady=4)

    def agregar_canal_gui() -> None:
        raw = entry_nuevo_canal.get().strip()
        if not raw:
            try:
                raw = root.clipboard_get().strip()
            except Exception:
                pass
        url_norm = normalizar_url_canal_shorts(raw)
        if not url_norm:
            return
        if url_norm not in lista_canales:
            lista_canales.append(url_norm)
            _guardar_memoria()
        entry_nuevo_canal.delete(0, tk.END)
        renderizar_chips_canales()

    ctk.CTkButton(
        add_canal_row,
        text="📋 Pegar",
        command=lambda: (
            entry_nuevo_canal.delete(0, tk.END),
            entry_nuevo_canal.insert(0, root.clipboard_get().strip()),
        ),
        corner_radius=16,
        height=38,
        width=85,
        fg_color="#1e2538",
        hover_color="#2b3550",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    ).pack(side="left", padx=(0, 6))

    ctk.CTkButton(
        add_canal_row,
        text="+ Agregar Canal",
        command=agregar_canal_gui,
        corner_radius=16,
        height=38,
        width=130,
        fg_color=PURPLE_MAIN,
        hover_color=PURPLE_HOVER,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    ).pack(side="right")

    # --- TARJETA MODO B: LINK INDIVIDUAL MANUAL ---
    card_link = ctk.CTkFrame(contenedor_paso1, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)

    ctk.CTkLabel(
        card_link,
        text="🔗  Link del Short de YouTube (Modo Individual)",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(anchor="w", padx=22, pady=(14, 6))

    url_row = ctk.CTkFrame(card_link, fg_color="transparent")
    url_row.pack(fill="x", padx=22, pady=(0, 14))

    entry_url = ctk.CTkEntry(
        url_row,
        placeholder_text="https://www.youtube.com/shorts/...",
        corner_radius=18,
        height=42,
        fg_color=INPUT_BG,
        border_width=1,
        border_color="#2a3147",
        text_color="#ffffff",
        font=ctk.CTkFont(family="Consolas", size=13),
    )
    entry_url.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def pegar_url() -> None:
        try:
            texto_clip = root.clipboard_get().strip()
            entry_url.delete(0, tk.END)
            entry_url.insert(0, texto_clip)
        except Exception:
            pass

    ctk.CTkButton(
        url_row,
        text="📋 Pegar",
        command=pegar_url,
        corner_radius=18,
        height=42,
        width=110,
        fg_color="#1e2538",
        hover_color="#2b3550",
        text_color=TEXT_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    ).pack(side="right")

    # ==========================================================================
    # PASO 2 UNIFICADO: PLAN DE SUBIDA, CANTIDAD POR DÍA Y HORARIOS INTELIGENTES
    # (Sin hueco vacío entre Canales/Link y Programación; la personalización manual
    #  se abre en una ventana emergente DESPUÉS de elegir los videos reales)
    # ==========================================================================
    card_pub = ctk.CTkFrame(root, fg_color=CARD_BG, corner_radius=22, border_width=1, border_color=CARD_BORDER)
    card_pub.pack(fill="x", padx=28, pady=(0, 12))

    pub_header = ctk.CTkFrame(card_pub, fg_color="transparent")
    pub_header.pack(fill="x", padx=20, pady=(12, 6))

    ctk.CTkLabel(
        pub_header,
        text="📅  Plan de Subida y Programación Inteligente",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color=TEXT_MAIN,
    ).pack(side="left")

    # Selector de Estrategia de Horarios (Pico Automático vs Cada X horas desde hora elegida)
    seg_estrategia = ctk.CTkSegmentedButton(
        pub_header,
        values=["🔥 Horarios Pico (Auto)", "⏱️ Cada X hs (Manual)"],
        variable=modo_horario_var,
        corner_radius=16,
        height=32,
        fg_color=INPUT_BG,
        selected_color=PURPLE_MAIN,
        selected_hover_color=PURPLE_HOVER,
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
    )
    seg_estrategia.pack(side="right")

    # FILA 1: Cantidad Total + Shorts por Día + Privacidad + Switch Programar
    row_plan1 = ctk.CTkFrame(card_pub, fg_color="transparent")
    row_plan1.pack(fill="x", padx=20, pady=(2, 8))

    box_cant = ctk.CTkFrame(row_plan1, fg_color="transparent")
    box_cant.pack(side="left", padx=(0, 10))
    ctk.CTkLabel(
        box_cant, text="📦 Cantidad Total", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_MUTED
    ).pack(anchor="w", pady=(0, 2))
    opt_cantidad_total = ctk.CTkOptionMenu(
        box_cant,
        variable=cantidad_total_var,
        values=list(MAPA_CANTIDAD_TOTAL.keys()),
        corner_radius=14,
        height=34,
        width=118,
        fg_color=INPUT_BG,
        button_color="#252d42",
        button_hover_color="#333e5a",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    opt_cantidad_total.pack()

    box_pordia = ctk.CTkFrame(row_plan1, fg_color="transparent")
    box_pordia.pack(side="left", padx=(0, 14))
    ctk.CTkLabel(
        box_pordia, text="📆 Shorts por Día", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_MUTED
    ).pack(anchor="w", pady=(0, 2))
    opt_por_dia = ctk.CTkOptionMenu(
        box_pordia,
        variable=shorts_por_dia_var,
        values=list(MAPA_POR_DIA.keys()),
        corner_radius=14,
        height=34,
        width=112,
        fg_color=INPUT_BG,
        button_color="#252d42",
        button_hover_color="#333e5a",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    opt_por_dia.pack()

    box_priv = ctk.CTkFrame(row_plan1, fg_color="transparent")
    box_priv.pack(side="left", padx=(0, 12))
    ctk.CTkLabel(
        box_priv, text="🔒 Visibilidad Base", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_MUTED
    ).pack(anchor="w", pady=(0, 2))
    seg_priv = ctk.CTkSegmentedButton(
        box_priv,
        values=["Privado", "Público", "Oculto"],
        variable=privacidad_var,
        corner_radius=14,
        height=34,
        fg_color=INPUT_BG,
        selected_color=PURPLE_MAIN,
        selected_hover_color=PURPLE_HOVER,
        unselected_color=INPUT_BG,
        unselected_hover_color="#1a2030",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
    )
    seg_priv.pack()

    def _cargar_imagen_avatar_ctk(avatar_path_str: str, size_px: int = 24) -> Optional[ctk.CTkImage]:
        if not avatar_path_str:
            return None
        key_c = f"{avatar_path_str}:{size_px}"
        if key_c in cache_avatares_ctk:
            return cache_avatares_ctk[key_c]
        try:
            p_av = Path(avatar_path_str)
            if p_av.exists():
                from PIL import Image
                pil_im = Image.open(p_av).convert("RGBA")
                ctk_im = ctk.CTkImage(light_image=pil_im, dark_image=pil_im, size=(size_px, size_px))
                cache_avatares_ctk[key_c] = ctk_im
                return ctk_im
        except Exception:
            pass
        return None

    def _sincronizar_canales_de_cuenta_activa(nuevo_cid: str, guardar_previo: bool = True) -> None:
        cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        if guardar_previo and cid_prev and str(estado_seleccion_cuentas.get("modo") or "una") == "una":
            canales_por_cuenta[cid_prev] = list(lista_canales)

        if nuevo_cid:
            estado_seleccion_cuentas["cuenta_id"] = nuevo_cid
            if nuevo_cid not in canales_por_cuenta:
                # Inicializar con los canales actuales la primera vez
                canales_por_cuenta[nuevo_cid] = list(lista_canales)
            else:
                lista_canales.clear()
                lista_canales.extend(canales_por_cuenta[nuevo_cid])
            estado_rotacion["idx"] = 0

    def refrescar_selector_cuentas_ui() -> None:
        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas = listar_cuentas_vinculadas()
        except Exception:
            cuentas = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]
        if not cuentas:
            cuentas = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]

        mapa_cuentas_ui.clear()
        ids_validos = [str(c.get("id") or "principal") for c in cuentas]
        dict_por_id = {str(c.get("id") or "principal"): c for c in cuentas}
        for c_info in cuentas:
            cid = str(c_info.get("id") or "principal")
            cnom = str(c_info.get("nombre") or cid)
            mapa_cuentas_ui[cnom] = cid

        cid_act = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        if not cid_act or cid_act not in dict_por_id:
            cid_act = ids_validos[0]
            _sincronizar_canales_de_cuenta_activa(cid_act, guardar_previo=False)
        else:
            if cid_act not in canales_por_cuenta:
                canales_por_cuenta[cid_act] = list(lista_canales)
            elif str(estado_seleccion_cuentas.get("modo") or "una") == "una":
                lista_canales.clear()
                lista_canales.extend(canales_por_cuenta[cid_act])

        modo_act = str(estado_seleccion_cuentas.get("modo") or "una")
        grupo_ids = [g for g in (estado_seleccion_cuentas.get("grupo_ids") or []) if g in dict_por_id]
        estado_seleccion_cuentas["grupo_ids"] = grupo_ids

        # Actualizar botón superior de Cuenta y etiqueta de Canales Fuente
        if modo_act == "todas" and len(cuentas) > 1:
            txt_btn = f"🔄 Todas ({len(cuentas)} cuentas)"
            img_btn = None
            lbl_titulo_canales.configure(
                text=f"📺  Canales Fuente de Shorts Virales  ·  🔄 Todas las cuentas ({len(cuentas)})"
            )
        elif modo_act == "grupo" and len(grupo_ids) >= 1:
            txt_btn = f"👥 Grupo ({len(grupo_ids)} cuentas)"
            img_btn = None
            lbl_titulo_canales.configure(
                text=f"📺  Canales Fuente de Shorts Virales  ·  👥 Grupo seleccionado ({len(grupo_ids)} cuentas)"
            )
        else:
            estado_seleccion_cuentas["modo"] = "una"
            info_c = dict_por_id.get(cid_act, cuentas[0])
            nom_c = str(info_c.get("nombre") or "Mi Canal")
            av_p = str(info_c.get("avatar_path") or "")
            img_btn = _cargar_imagen_avatar_ctk(av_p, size_px=24)
            txt_btn = f"{nom_c[:18]} ▾" if img_btn else f"📺 {nom_c[:18]} ▾"
            lbl_titulo_canales.configure(
                text=f"📺  Canales Fuente de Shorts Virales  ·  Cuenta: {nom_c}"
            )

        if "btn_cuenta_top" in locals() or "btn_cuenta_top" in globals():
            try:
                btn_cuenta_top.configure(text=txt_btn, image=img_btn)
            except Exception:
                pass
        renderizar_chips_canales()

    def vincular_nueva_cuenta_gui(parent_win: Optional[tk.Misc] = None) -> None:
        def _worker_vinc() -> None:
            try:
                from subir_a_youtube import vincular_nueva_cuenta_interactivo
                info_nueva = vincular_nueva_cuenta_interactivo()
                nom_c = str(info_nueva.get("nombre") or "Nueva Cuenta")
                nuevo_id = str(info_nueva.get("id") or "")

                def _ok_v() -> None:
                    if nuevo_id:
                        _sincronizar_canales_de_cuenta_activa(nuevo_id, guardar_previo=True)
                        # Una cuenta recién vinculada empieza con su propia lista de canales (copia o limpia)
                        estado_seleccion_cuentas["modo"] = "una"
                    refrescar_selector_cuentas_ui()
                    _guardar_memoria()
                    sincronizar_cuota_async()
                    messagebox.showinfo(
                        "Cuenta Vinculada",
                        f"¡Canal '{nom_c}' vinculado con éxito!\n\nAhora está seleccionado arriba a la derecha con sus propios canales guardados.",
                        parent=parent_win or root,
                    )

                root.after(0, _ok_v)
            except Exception as e_v:
                root.after(
                    0,
                    lambda msg=str(e_v): messagebox.showerror(
                        "Error al vincular cuenta",
                        f"No se pudo completar la vinculación:\n{msg}",
                        parent=parent_win or root,
                    ),
                )

        threading.Thread(target=_worker_vinc, daemon=True).start()

    sw_prog = ctk.CTkSwitch(
        row_plan1,
        text="Programar",
        variable=programar_var,
        progress_color=PURPLE_MAIN,
        button_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    sw_prog.pack(side="right", pady=(14, 0))

    # FILA 2: Fecha de Inicio + Controles de Hora / Intervalo + Vista Previa en Vivo
    row_plan2 = ctk.CTkFrame(card_pub, fg_color="transparent")
    row_plan2.pack(fill="x", padx=20, pady=(0, 12))

    btn_calendario = ctk.CTkButton(
        row_plan2,
        text=_formatear_boton_fecha(fecha_elegida_var.get()),
        corner_radius=16,
        height=34,
        width=165,
        fg_color=INPUT_BG,
        hover_color="#1c2233",
        border_width=1,
        border_color="#2e3852",
        text_color=CYAN_ACCENT,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    btn_calendario.pack(side="left", padx=(0, 8))

    # Sub-frame para Controles Manuales (Hora de arranque + Intervalo cada X hs)
    frame_manual_horas = ctk.CTkFrame(row_plan2, fg_color="transparent")

    lbl_desde = ctk.CTkLabel(
        frame_manual_horas,
        text="Desde:",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color=TEXT_MUTED,
    )
    lbl_desde.pack(side="left", padx=(2, 4))

    LISTA_HORAS_SCROLL = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
    combo_hora = ctk.CTkComboBox(
        frame_manual_horas,
        variable=hora_elegida_var,
        values=LISTA_HORAS_SCROLL,
        state="readonly",
        corner_radius=14,
        height=34,
        width=92,
        fg_color=INPUT_BG,
        border_color="#2a3147",
        button_color="#252d42",
        button_hover_color="#333e5a",
        dropdown_fg_color="#141824",
        dropdown_hover_color=PURPLE_MAIN,
        font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
    )
    combo_hora.pack(side="left", padx=(0, 6))

    opt_intervalo = ctk.CTkOptionMenu(
        frame_manual_horas,
        variable=intervalo_horas_var,
        values=list(MAPA_INTERVALO_HS.keys()),
        corner_radius=14,
        height=34,
        width=102,
        fg_color=INPUT_BG,
        button_color="#252d42",
        button_hover_color="#333e5a",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
    )
    opt_intervalo.pack(side="left", padx=(0, 6))

    # Píldora de Vista Previa de los horarios exactos en los que saldrá cada Short
    preview_box = ctk.CTkFrame(row_plan2, fg_color=INPUT_BG, corner_radius=14, border_width=1, border_color="#1f263a")
    preview_box.pack(side="left", fill="x", expand=True)

    lbl_preview_horarios = ctk.CTkLabel(
        preview_box,
        text="",
        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        text_color="#a7f3d0",
    )
    lbl_preview_horarios.pack(anchor="w", padx=12, pady=6)

    def calcular_lista_horarios_actual() -> List[Optional[str]]:
        es_canales = "Canales" in modo_fuente_var.get()
        cant_t = MAPA_CANTIDAD_TOTAL.get(cantidad_total_var.get(), 2) if es_canales else 1
        por_d = MAPA_POR_DIA.get(shorts_por_dia_var.get(), 2)
        if not programar_var.get():
            return [None] * cant_t
        interv = MAPA_INTERVALO_HS.get(intervalo_horas_var.get(), 8)
        slots = calcular_horarios_inteligentes(
            cantidad_total=cant_t,
            por_dia=por_d,
            fecha_base_iso=fecha_elegida_var.get().strip(),
            modo_horario=modo_horario_var.get(),
            hora_inicio=hora_elegida_var.get().strip() or "13:00",
            intervalo_hs=interv,
        )
        return [s for s in slots]

    def refrescar_plan_ui(*_args: object) -> None:
        _guardar_memoria()
        es_canales = "Canales" in modo_fuente_var.get()
        if es_canales:
            opt_cantidad_total.configure(state="normal")
            opt_por_dia.configure(state="normal")
        else:
            opt_cantidad_total.configure(state="disabled")
            opt_por_dia.configure(state="disabled")

        if "Pico" in modo_horario_var.get():
            frame_manual_horas.pack_forget()
        else:
            preview_box.pack_forget()
            frame_manual_horas.pack(side="left", padx=(0, 6))
            preview_box.pack(side="left", fill="x", expand=True)

        if not programar_var.get():
            lbl_preview_horarios.configure(
                text="⚡ Subida inmediata sin programación (se publicarán ahora mismo)",
                text_color="#facc15",
            )
            return

        slots = calcular_lista_horarios_actual()
        hoy = _dt.date.today()
        partes_prev: List[str] = []
        for idx_s, s_str in enumerate(slots[:4]):
            if not s_str:
                continue
            f_part, h_part = s_str.split(" ")
            d_obj = _dt.date.fromisoformat(f_part)
            if d_obj == hoy:
                d_txt = "Hoy"
            elif d_obj == hoy + _dt.timedelta(days=1):
                d_txt = "Mañana"
            else:
                d_txt = f"{d_obj.day:02d}/{d_obj.month:02d}"
            partes_prev.append(f"#{idx_s + 1} {d_txt} {h_part}")
        if len(slots) > 4:
            partes_prev.append(f"+{len(slots) - 4} más")

        resumen_str = "  ·  ".join(partes_prev)
        lbl_preview_horarios.configure(
            text=f"🎯 Salidas: {resumen_str}",
            text_color="#a7f3d0",
        )

    seg_estrategia.configure(command=refrescar_plan_ui)
    opt_cantidad_total.configure(command=refrescar_plan_ui)
    opt_por_dia.configure(command=refrescar_plan_ui)
    seg_priv.configure(command=refrescar_plan_ui)
    sw_prog.configure(command=refrescar_plan_ui)
    combo_hora.configure(command=refrescar_plan_ui)
    opt_intervalo.configure(command=refrescar_plan_ui)

    def actualizar_modo_vista(*_args: object) -> None:
        _guardar_memoria()
        renderizar_chips_canales()
        if "Canales" in modo_fuente_var.get():
            card_link.pack_forget()
            card_canales.pack(fill="x")
        else:
            card_canales.pack_forget()
            card_link.pack(fill="x")
        refrescar_plan_ui()

    # ==========================================================================
    # VENTANA DE AJUSTES (CON TOGGLE DE MODO, CONTENIDO IA/MANUAL Y MODELO ARGON 4)
    # ==========================================================================
    def abrir_ventana_ajustes() -> None:
        win = ctk.CTkToplevel(root)
        win.title("Ajustes y Herramientas")
        win.geometry("580x630")
        win.resizable(False, False)
        win.configure(fg_color=BG_DARK)
        win.transient(root)
        win.grab_set()

        ctk.CTkLabel(
            win,
            text="⚙️  Ajustes del Estudio",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=24, pady=(16, 8))

        # 1. Tarjeta de Modo de Trabajo, Título/Guión (IA vs Manual) y Selección de Canales
        card_modo = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_modo.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(
            card_modo,
            text="🔀 Modo de Obtención de Videos",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(10, 4))

        ctk.CTkSegmentedButton(
            card_modo,
            values=["Canales Automáticos", "Link Manual"],
            variable=modo_fuente_var,
            command=actualizar_modo_vista,
            corner_radius=14,
            height=32,
            selected_color=PURPLE_MAIN,
        ).pack(fill="x", padx=18, pady=(0, 8))

        ctk.CTkLabel(
            card_modo,
            text="✍️ Modo de Título, Descripción y Guión",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(2, 4))

        ctk.CTkSegmentedButton(
            card_modo,
            values=["IA Automática", "Personalizado por mí"],
            variable=modo_contenido_var,
            command=actualizar_modo_vista,
            corner_radius=14,
            height=32,
            selected_color=PURPLE_MAIN,
        ).pack(fill="x", padx=18, pady=(0, 8))

        row_ord = ctk.CTkFrame(card_modo, fg_color="transparent")
        row_ord.pack(fill="x", padx=18, pady=(0, 10))

        col_ord1 = ctk.CTkFrame(row_ord, fg_color="transparent")
        col_ord1.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(
            col_ord1,
            text="🔄 Selección de Canal:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkOptionMenu(
            col_ord1,
            variable=orden_canales_var,
            values=["Rotación (En fila)", "Aleatorio"],
            command=lambda _: (_guardar_memoria(), renderizar_chips_canales()),
            corner_radius=14,
            height=32,
            fg_color="#1e2436",
            button_color="#2d354d",
        ).pack(fill="x")

        col_ord2 = ctk.CTkFrame(row_ord, fg_color="transparent")
        col_ord2.pack(side="right", fill="x", expand=True, padx=(6, 0))
        ctk.CTkLabel(
            col_ord2,
            text="🔥 Filtro de Vistas Mínimas:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkOptionMenu(
            col_ord2,
            variable=min_views_var,
            values=list(MAPA_MIN_VIEWS.keys()),
            command=lambda _: (_guardar_memoria(), renderizar_chips_canales()),
            corner_radius=14,
            height=32,
            fg_color="#1e2436",
            button_color="#2d354d",
        ).pack(fill="x")

        # 2. Cerebro IA (Argon 4 / Gemini), Voz y Encuadre
        card_cfg = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_cfg.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(
            card_cfg,
            text="🧠 Modelo de IA para Guiones (Argon 4 / Gemini)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(10, 4))

        ctk.CTkOptionMenu(
            card_cfg,
            variable=modelo_ia_var,
            values=list(MAPA_MODELOS_IA.keys()),
            command=_guardar_memoria,
            corner_radius=14,
            height=32,
            fg_color="#1e2436",
            button_color="#2d354d",
        ).pack(fill="x", padx=18, pady=(0, 8))

        ctk.CTkLabel(
            card_cfg,
            text="🎙️ Voz del Narrador IA",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(2, 4))

        ctk.CTkOptionMenu(
            card_cfg,
            variable=voz_var,
            values=list(VOCES_DISPONIBLES.keys()),
            command=_guardar_memoria,
            corner_radius=14,
            height=32,
            fg_color="#1e2436",
            button_color="#2d354d",
        ).pack(fill="x", padx=18, pady=(0, 8))

        ctk.CTkLabel(
            card_cfg,
            text="📐 Formato de Encuadre Vertical (9:16)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=18, pady=(0, 4))

        ctk.CTkOptionMenu(
            card_cfg,
            variable=encuadre_var,
            values=list(encuadre_map.keys()),
            command=_guardar_memoria,
            corner_radius=14,
            height=32,
            fg_color="#1e2436",
            button_color="#2d354d",
        ).pack(fill="x", padx=18, pady=(0, 12))

        # 3. Tarjeta de API Key Gemini
        card_api = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_api.pack(fill="x", padx=24, pady=(0, 10))

        top_api = ctk.CTkFrame(card_api, fg_color="transparent")
        top_api.pack(fill="x", padx=18, pady=(12, 6))

        ctk.CTkLabel(
            top_api,
            text="🔑 Clave API de Gemini Flash (Gratis)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        ctk.CTkButton(
            top_api,
            text="🌐 Obtener Gratis",
            command=lambda: webbrowser.open("https://aistudio.google.com/apikey"),
            corner_radius=14,
            height=28,
            width=120,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="right")

        key_var = tk.StringVar(value=obtener_gemini_api_key())
        row_k = ctk.CTkFrame(card_api, fg_color="transparent")
        row_k.pack(fill="x", padx=18, pady=(0, 12))

        ent_k = ctk.CTkEntry(
            row_k,
            textvariable=key_var,
            corner_radius=14,
            height=34,
            fg_color=INPUT_BG,
            border_color="#2e364f",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        ent_k.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _guardar_k() -> None:
            k = key_var.get().strip()
            if k:
                guardar_gemini_api_key(k)
                messagebox.showinfo("Guardado", "API Key guardada correctamente.", parent=win)

        ctk.CTkButton(
            row_k,
            text="Guardar",
            command=_guardar_k,
            corner_radius=14,
            height=34,
            width=90,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            text_color="#052e16",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right")

        # 4. Carpeta Output
        card_tools = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_tools.pack(fill="x", padx=24, pady=(0, 12))

        grid_t = ctk.CTkFrame(card_tools, fg_color="transparent")
        grid_t.pack(fill="x", padx=16, pady=(10, 10))

        ctk.CTkButton(
            grid_t,
            text="📂 Abrir Carpeta Output de Shorts",
            command=abrir_carpeta_salida,
            corner_radius=14,
            height=36,
            fg_color="#1e2436",
            hover_color="#2d354d",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(fill="x", padx=4)

    def finalizar_app_completamente() -> None:
        try:
            root.destroy()
        except Exception:
            pass
        os._exit(0)

    def al_cerrar_ventana_x() -> None:
        # Si está editando/subiendo Reels, al tocar la X pasa a segundo plano sin cortar nada;
        # al volver a abrir el icono del Escritorio/Inicio, la ventana reaparece con el progreso actual.
        if editando_lock.locked():
            root.withdraw()
        else:
            finalizar_app_completamente()

    root.protocol("WM_DELETE_WINDOW", al_cerrar_ventana_x)

    def _vigilar_senal_mostrar_ventana() -> None:
        sig_file = BASE_DIR / "temp_build" / "mostrar_ventana.signal"
        if sig_file.exists():
            try:
                sig_file.unlink()
            except Exception:
                pass
            try:
                root.deiconify()
                root.lift()
                root.focus_force()
            except Exception:
                pass
        root.after(400, _vigilar_senal_mostrar_ventana)

    root.after(400, _vigilar_senal_mostrar_ventana)

    def abrir_selector_cuentas_popup() -> None:
        pop = ctk.CTkToplevel(root)
        pop.title("Elegir Cuenta o Grupo de Subida")
        pop.geometry("460x530")
        pop.resizable(False, False)
        pop.configure(fg_color=BG_DARK)
        pop.transient(root)
        pop.grab_set()

        ctk.CTkLabel(
            pop,
            text="📺  Elegir Cuenta de Subida",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=22, pady=(16, 2))

        ctk.CTkLabel(
            pop,
            text="Cada cuenta recuerda sus propios Canales Fuente guardados.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 10))

        try:
            from subir_a_youtube import listar_cuentas_vinculadas
            cuentas_disp = listar_cuentas_vinculadas()
        except Exception:
            cuentas_disp = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]
        if not cuentas_disp:
            cuentas_disp = [{"id": "principal", "nombre": "Canal Principal", "avatar_path": ""}]

        modo_actual = str(estado_seleccion_cuentas.get("modo") or "una")
        cid_actual = str(estado_seleccion_cuentas.get("cuenta_id") or "")
        grupo_actual = set(estado_seleccion_cuentas.get("grupo_ids") or [])

        # Selector superior de modo: 1 Cuenta | Todas las Cuentas | Grupo Seleccionado
        mapa_modo_seg = {
            "👤 1 Cuenta": "una",
            "🔄 Todas": "todas",
            "👥 Grupo": "grupo",
        }
        inv_modo_seg = {v: k for k, v in mapa_modo_seg.items()}
        seg_modo_var = tk.StringVar(value=inv_modo_seg.get(modo_actual, "👤 1 Cuenta"))

        lista_scroll = ctk.CTkScrollableFrame(
            pop,
            height=300,
            corner_radius=16,
            fg_color=CARD_BG,
            border_width=1,
            border_color=CARD_BORDER,
        )

        vars_checks_grupo: Dict[str, tk.BooleanVar] = {}

        def _seleccionar_cuenta_unica(cid_elegido: str) -> None:
            _sincronizar_canales_de_cuenta_activa(cid_elegido, guardar_previo=True)
            estado_seleccion_cuentas["modo"] = "una"
            refrescar_selector_cuentas_ui()
            _guardar_memoria()
            pop.destroy()

        def _render_lista_popup(*_args: object) -> None:
            for w in lista_scroll.winfo_children():
                w.destroy()
            m_sel = mapa_modo_seg.get(seg_modo_var.get(), "una")

            if m_sel == "todas":
                ctk.CTkLabel(
                    lista_scroll,
                    text=f"🔄 Se subirán los Shorts rotando entre TODAS tus cuentas ({len(cuentas_disp)}).\nCada Reel usará los Canales Fuente guardados de la cuenta que le toque.",
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    text_color=CYAN_ACCENT,
                    justify="left",
                    wraplength=390,
                ).pack(anchor="w", padx=12, pady=(8, 10))

            elif m_sel == "grupo":
                ctk.CTkLabel(
                    lista_scroll,
                    text="👥 Marca las cuentas que quieres incluir en el grupo de subida:",
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    text_color=CYAN_ACCENT,
                ).pack(anchor="w", padx=12, pady=(6, 8))

            for c_it in cuentas_disp:
                c_id = str(c_it.get("id") or "principal")
                c_nom = str(c_it.get("nombre") or c_id)
                c_av = str(c_it.get("avatar_path") or "")
                n_can = len(canales_por_cuenta.get(c_id, lista_canales if c_id == cid_actual else []))
                es_activa = (m_sel == "una" and c_id == cid_actual)

                item_f = ctk.CTkFrame(
                    lista_scroll,
                    fg_color="#1f273d" if es_activa else INPUT_BG,
                    corner_radius=14,
                    border_width=1,
                    border_color=PURPLE_MAIN if es_activa else "#242c42",
                )
                item_f.pack(fill="x", padx=8, pady=4)

                av_img = _cargar_imagen_avatar_ctk(c_av, size_px=34)
                if av_img:
                    ctk.CTkLabel(item_f, text="", image=av_img).pack(side="left", padx=(10, 8), pady=8)
                else:
                    ctk.CTkLabel(
                        item_f,
                        text="📺",
                        font=ctk.CTkFont(size=18),
                    ).pack(side="left", padx=(12, 8), pady=8)

                info_col = ctk.CTkFrame(item_f, fg_color="transparent")
                info_col.pack(side="left", fill="x", expand=True, pady=6)

                ctk.CTkLabel(
                    info_col,
                    text=c_nom,
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    text_color="#ffffff" if es_activa else TEXT_MAIN,
                ).pack(anchor="w")

                ctk.CTkLabel(
                    info_col,
                    text=f"{n_can} canal(es) fuente guardados",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color=CYAN_ACCENT if es_activa else TEXT_MUTED,
                ).pack(anchor="w")

                if m_sel == "una":
                    ctk.CTkButton(
                        item_f,
                        text="✓ Activa" if es_activa else "Elegir",
                        command=lambda cid_x=c_id: _seleccionar_cuenta_unica(cid_x),
                        corner_radius=12,
                        height=30,
                        width=82,
                        fg_color=GREEN_ACCENT if es_activa else PURPLE_MAIN,
                        hover_color="#059669" if es_activa else PURPLE_HOVER,
                        text_color="#052e16" if es_activa else "#ffffff",
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    ).pack(side="right", padx=10)
                elif m_sel == "grupo":
                    if c_id not in vars_checks_grupo:
                        vars_checks_grupo[c_id] = tk.BooleanVar(
                            value=(c_id in grupo_actual) or (not grupo_actual and c_id == cid_actual)
                        )
                    ctk.CTkCheckBox(
                        item_f,
                        text="",
                        variable=vars_checks_grupo[c_id],
                        width=24,
                        checkbox_width=22,
                        checkbox_height=22,
                        corner_radius=6,
                        fg_color=PURPLE_MAIN,
                        hover_color=PURPLE_HOVER,
                    ).pack(side="right", padx=10)

        seg_modo = ctk.CTkSegmentedButton(
            pop,
            values=["👤 1 Cuenta", "🔄 Todas", "👥 Grupo"],
            variable=seg_modo_var,
            command=_render_lista_popup,
            corner_radius=14,
            height=34,
            selected_color=PURPLE_MAIN,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        seg_modo.pack(fill="x", padx=22, pady=(0, 10))
        lista_scroll.pack(fill="both", expand=True, padx=22, pady=(0, 10))

        _render_lista_popup()

        bot_bar = ctk.CTkFrame(pop, fg_color="transparent")
        bot_bar.pack(fill="x", padx=22, pady=(0, 14))

        ctk.CTkButton(
            bot_bar,
            text="➕ Vincular Nueva Cuenta",
            command=lambda: (pop.destroy(), vincular_nueva_cuenta_gui(root)),
            corner_radius=14,
            height=36,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        def _aplicar_cierre_popup() -> None:
            m_f = mapa_modo_seg.get(seg_modo_var.get(), "una")
            if m_f == "todas":
                # Guardar canales de la cuenta que estaba activa
                cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                if cid_prev:
                    canales_por_cuenta[cid_prev] = list(lista_canales)
                estado_seleccion_cuentas["modo"] = "todas"
            elif m_f == "grupo":
                elegidos_g = [k for k, v in vars_checks_grupo.items() if v.get()]
                if not elegidos_g and cuentas_disp:
                    elegidos_g = [str(cuentas_disp[0].get("id") or "principal")]
                cid_prev = str(estado_seleccion_cuentas.get("cuenta_id") or "")
                if cid_prev:
                    canales_por_cuenta[cid_prev] = list(lista_canales)
                estado_seleccion_cuentas["modo"] = "grupo"
                estado_seleccion_cuentas["grupo_ids"] = elegidos_g
            else:
                estado_seleccion_cuentas["modo"] = "una"
            refrescar_selector_cuentas_ui()
            _guardar_memoria()
            pop.destroy()

        ctk.CTkButton(
            bot_bar,
            text="✅ Aplicar Selección",
            command=_aplicar_cierre_popup,
            corner_radius=14,
            height=36,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            text_color="#052e16",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).pack(side="right", fill="x", expand=True, padx=(6, 0))

    btn_cuenta_top = ctk.CTkButton(
        header,
        text="📺 Mi Cuenta ▾",
        command=abrir_selector_cuentas_popup,
        compound="left",
        corner_radius=20,
        height=40,
        fg_color=CARD_BG,
        hover_color="#1f2637",
        border_width=1,
        border_color=PURPLE_MAIN,
        text_color=TEXT_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    btn_cuenta_top.pack(side="right", padx=(8, 0), pady=4)

    refrescar_selector_cuentas_ui()

    btn_ajustes = ctk.CTkButton(
        header,
        text="⚙️  Ajustes",
        command=abrir_ventana_ajustes,
        corner_radius=20,
        height=40,
        width=115,
        fg_color=CARD_BG,
        hover_color="#1f2637",
        border_width=1,
        border_color=CARD_BORDER,
        text_color=TEXT_MAIN,
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
    )
    btn_ajustes.pack(side="right", pady=4)

    actualizar_modo_vista()

    def abrir_calendario_popup() -> None:
        hoy = _dt.date.today()
        try:
            f_actual = _dt.date.fromisoformat(fecha_elegida_var.get())
        except Exception:
            f_actual = hoy
        if f_actual < hoy:
            f_actual = hoy

        estado_cal = {"year": f_actual.year, "month": f_actual.month}

        pop = ctk.CTkToplevel(root)
        pop.title("Elegir Fecha")
        pop.configure(fg_color=BG_DARK)
        pop.resizable(False, False)
        pop.transient(root)
        pop.grab_set()

        bx = max(40, btn_calendario.winfo_rootx() - 40)
        by = btn_calendario.winfo_rooty() + btn_calendario.winfo_height() + 6
        pop.geometry(f"330x330+{bx}+{by}")

        wrap = ctk.CTkFrame(pop, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        nav_row = ctk.CTkFrame(wrap, fg_color="transparent")
        nav_row.pack(fill="x", padx=12, pady=(10, 6))

        btn_prev = ctk.CTkButton(
            nav_row, text="◀", width=34, height=30, corner_radius=12,
            fg_color="#1e2538", hover_color="#2d3753",
        )
        btn_prev.pack(side="left")

        lbl_mes = ctk.CTkLabel(
            nav_row, text="", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_MAIN,
        )
        lbl_mes.pack(side="left", expand=True)

        btn_next = ctk.CTkButton(
            nav_row, text="▶", width=34, height=30, corner_radius=12,
            fg_color="#1e2538", hover_color="#2d3753",
        )
        btn_next.pack(side="right")

        grid_frame = ctk.CTkFrame(wrap, fg_color="transparent")
        grid_frame.pack(padx=10, pady=2)

        atajos_row = ctk.CTkFrame(wrap, fg_color="transparent")
        atajos_row.pack(fill="x", padx=10, pady=(8, 10))

        def _elegir_fecha(d_sel: _dt.date) -> None:
            iso = d_sel.strftime("%Y-%m-%d")
            fecha_elegida_var.set(iso)
            programar_var.set(True)
            btn_calendario.configure(text=_formatear_boton_fecha(iso))
            refrescar_plan_ui()
            pop.destroy()

        for lbl_at, delta_d in [("Hoy", 0), ("Mañana", 1), ("Pasado", 2)]:
            d_target = hoy + _dt.timedelta(days=delta_d)
            ctk.CTkButton(
                atajos_row,
                text=lbl_at,
                command=lambda dt=d_target: _elegir_fecha(dt),
                corner_radius=12,
                height=28,
                fg_color="#1e2538",
                hover_color=PURPLE_MAIN,
                text_color=CYAN_ACCENT,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            ).pack(side="left", expand=True, fill="x", padx=3)

        def _dibujar_mes() -> None:
            for w in grid_frame.winfo_children():
                w.destroy()

            y = estado_cal["year"]
            m = estado_cal["month"]
            lbl_mes.configure(text=f"{MESES_ES[m]} {y}")

            if (y, m) <= (hoy.year, hoy.month):
                btn_prev.configure(state="disabled", fg_color="#10131c")
            else:
                btn_prev.configure(state="normal", fg_color="#1e2538")

            for col_i, nombre_d in enumerate(DIAS_CORTOS_ES):
                ctk.CTkLabel(
                    grid_frame, text=nombre_d, width=36,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=TEXT_MUTED,
                ).grid(row=0, column=col_i, pady=(0, 4))

            cal_matrix = _cal.monthcalendar(y, m)
            for r_i, semana in enumerate(cal_matrix, start=1):
                for c_i, dia_num in enumerate(semana):
                    if dia_num == 0:
                        ctk.CTkLabel(grid_frame, text="", width=36, height=30).grid(row=r_i, column=c_i)
                        continue

                    fecha_celda = _dt.date(y, m, dia_num)
                    es_pasado = fecha_celda < hoy
                    es_sel = fecha_celda == f_actual
                    es_hoy = fecha_celda == hoy

                    if es_pasado:
                        ctk.CTkButton(
                            grid_frame, text=str(dia_num), width=36, height=30, corner_radius=10,
                            fg_color="transparent", text_color="#334155", state="disabled",
                        ).grid(row=r_i, column=c_i, padx=2, pady=2)
                    else:
                        bg_c = PURPLE_MAIN if es_sel else ("#0284c7" if es_hoy else "#1b2234")
                        ctk.CTkButton(
                            grid_frame,
                            text=str(dia_num),
                            command=lambda fc=fecha_celda: _elegir_fecha(fc),
                            width=36,
                            height=30,
                            corner_radius=10,
                            fg_color=bg_c,
                            hover_color=GREEN_ACCENT,
                            text_color="#ffffff",
                            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold" if (es_sel or es_hoy) else "normal"),
                        ).grid(row=r_i, column=c_i, padx=2, pady=2)

        def _mes_anterior() -> None:
            if (estado_cal["year"], estado_cal["month"]) <= (hoy.year, hoy.month):
                return
            if estado_cal["month"] == 1:
                estado_cal["month"] = 12
                estado_cal["year"] -= 1
            else:
                estado_cal["month"] -= 1
            _dibujar_mes()

        def _mes_siguiente() -> None:
            if estado_cal["month"] == 12:
                estado_cal["month"] = 1
                estado_cal["year"] += 1
            else:
                estado_cal["month"] += 1
            _dibujar_mes()

        btn_prev.configure(command=_mes_anterior)
        btn_next.configure(command=_mes_siguiente)
        _dibujar_mes()

    btn_calendario.configure(command=abrir_calendario_popup)

    def obtener_schedule_seleccionado() -> Optional[str]:
        _guardar_memoria()
        if not programar_var.get():
            return None
        return f"{fecha_elegida_var.get().strip()} {hora_elegida_var.get().strip()}"

    # ==========================================================================
    # PASO 3 Y 4 UNIFICADOS: BOTÓN DE INICIO QUE SE REEMPLAZA POR LA BARRA DE CARGA
    # ==========================================================================
    contenedor_accion_y_progreso = ctk.CTkFrame(root, fg_color="transparent")
    contenedor_accion_y_progreso.pack(fill="x", padx=28, pady=(2, 20))

    btn_auto_1clic = ctk.CTkButton(
        contenedor_accion_y_progreso,
        text="🚀  CREAR Y SUBIR SHORT AHORA",
        corner_radius=26,
        height=58,
        fg_color=PURPLE_MAIN,
        hover_color=PURPLE_HOVER,
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
    )
    btn_auto_1clic.pack(fill="x")

    progress_card = ctk.CTkFrame(
        contenedor_accion_y_progreso,
        fg_color=CARD_BG,
        corner_radius=22,
        border_width=1,
        border_color=CARD_BORDER,
    )
    # Oculto inicialmente; al tocar "CREAR Y SUBIR SHORT AHORA", el botón desaparece
    # y aparece esta tarjeta de progreso en su lugar.

    def _mostrar_modo_progreso_activo(activo: bool) -> None:
        if activo:
            btn_auto_1clic.pack_forget()
            progress_card.pack(fill="x")
        else:
            progress_card.pack_forget()
            btn_auto_1clic.configure(
                state="normal",
                text="🚀  CREAR Y SUBIR SHORT AHORA",
                fg_color=PURPLE_MAIN,
            )
            btn_auto_1clic.pack(fill="x")

    prog_top_row = ctk.CTkFrame(progress_card, fg_color="transparent")
    prog_top_row.pack(fill="x", padx=20, pady=(14, 6))

    lbl_estado = ctk.CTkLabel(
        prog_top_row,
        text="✨ Listo — Elige tus canales o link arriba y dale a Crear y Subir",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color=CYAN_ACCENT,
    )
    lbl_estado.pack(side="left")

    lbl_porcentaje_proceso = ctk.CTkLabel(
        prog_top_row,
        text="0%",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        text_color="#ffffff",
    )
    lbl_porcentaje_proceso.pack(side="right")

    barra_progreso_proceso = ctk.CTkProgressBar(
        progress_card,
        height=14,
        corner_radius=8,
        fg_color="#181e2e",
        progress_color=PURPLE_MAIN,
    )
    barra_progreso_proceso.pack(fill="x", padx=20, pady=(2, 10))
    barra_progreso_proceso.set(0.0)

    frame_milestones = ctk.CTkFrame(progress_card, fg_color="transparent")
    frame_milestones.pack(fill="x", padx=18, pady=(0, 12))

    def _actualizar_progreso_ui(
        pct_total: float,
        texto_estado: Optional[str] = None,
        color_estado: str = "#facc15",
        color_barra: str = PURPLE_MAIN,
    ) -> None:
        pct_clamp = max(0.0, min(100.0, float(pct_total)))
        barra_progreso_proceso.set(pct_clamp / 100.0)
        barra_progreso_proceso.configure(progress_color=color_barra)
        lbl_porcentaje_proceso.configure(text=f"{int(round(pct_clamp))}%")
        if texto_estado is not None:
            lbl_estado.configure(text=texto_estado, text_color=color_estado)

    def _renderizar_milestones_ui(estados_reels: List[Dict[str, str]]) -> None:
        for w in frame_milestones.winfo_children():
            w.destroy()
        if len(estados_reels) <= 1:
            ctk.CTkLabel(
                frame_milestones,
                text="🎯 Modo 1 Reel · La barra avanza en tiempo real desde la descarga hasta quedar subido al 100%",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_DIM,
            ).pack(anchor="w", padx=4)
            return
        for item_m in estados_reels:
            est_tipo = item_m.get("tipo", "pendiente")
            txt_m = item_m.get("texto", "")
            if est_tipo == "subido":
                bg_m = "#0f291e"
                bd_m = GREEN_ACCENT
                tc_m = "#4ade80"
            elif est_tipo == "activo":
                bg_m = "#231c38"
                bd_m = PURPLE_MAIN
                tc_m = "#e9d5ff"
            else:
                bg_m = "#151a28"
                bd_m = "#262f45"
                tc_m = TEXT_DIM
            pill_m = ctk.CTkFrame(
                frame_milestones,
                fg_color=bg_m,
                corner_radius=12,
                border_width=1,
                border_color=bd_m,
            )
            pill_m.pack(side="left", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                pill_m,
                text=txt_m,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=tc_m,
            ).pack(padx=10, pady=3)

    _renderizar_milestones_ui([])

    class RedireccionadorSilencioso:
        def __init__(self, q: "queue.Queue[str]"):
            self.q = q

        def write(self, texto: str) -> None:
            if texto:
                self.q.put(texto)

        def flush(self) -> None:
            pass

    def vaciar_cola_logs() -> None:
        while not cola_logs.empty():
            try:
                cola_logs.get_nowait()
            except Exception:
                break
        root.after(200, vaciar_cola_logs)

    def reproducir_ultimo_short() -> None:
        ruta_rep = ultimo_video_generado[0]
        if ruta_rep is None or not ruta_rep.exists():
            mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mp4s:
                ruta_rep = mp4s[0]
        if ruta_rep and ruta_rep.exists():
            try:
                os.startfile(str(ruta_rep))
            except Exception:
                pass
        else:
            messagebox.showinfo("Sin videos", "Aún no hay videos generados en 'output_shorts'.")

    def abrir_carpeta_salida() -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(OUTPUT_DIR))
        except Exception:
            pass

    def verificar_canal_gui() -> None:
        try:
            from subir_a_youtube import obtener_servicio_youtube
            youtube = obtener_servicio_youtube()
            resp = youtube.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            if items:
                nombre_canal = items[0]["snippet"]["title"]
                messagebox.showinfo(
                    "Canal de YouTube Vinculado",
                    f"✅ ¡Conexión Activa!\n\nCanal: {nombre_canal}\n\n"
                    f"Tus credenciales están listas para subir videos directamente.",
                )
            else:
                messagebox.showinfo("Canal de YouTube", "Conectado a la API de YouTube correctamente.")
        except Exception as e:
            messagebox.showerror("Error de Vinculación", f"No se pudo conectar con YouTube:\n{e}")

    def _aplicar_custom_a_guion_txt(
        idx_reel: int,
        ruta_video: Path,
        custom_tit: str,
        custom_desc: str,
        custom_guion: str,
        sched_str: str,
        modo_priv: str,
    ) -> bool:
        """
        Si el usuario escribió un guión personalizado completo (y opcionalmente título/descripción),
        puede construir o sobreescribir `DEFAULT_GUION_TXT`.
        Retorna True si YA construyó el archivo completo sin necesitar llamar a la IA,
        o False si primero debe ejecutarse la IA y luego sobreescribir los campos personalizados.
        """
        if not custom_guion:
            return False

        dur_v = max(10.0, min(60.0, obtener_duracion_video_ffprobe(ruta_video)))
        lineas_guion_formateadas: List[str] = []

        # Detectar si el usuario ya pegó formato con '|' o texto libre
        lineas_raw = [ln.strip() for ln in custom_guion.replace(";", "\n").splitlines() if ln.strip()]
        if any("|" in ln for ln in lineas_raw):
            for ln in lineas_raw:
                if "|" in ln:
                    lineas_guion_formateadas.append(ln)
        else:
            # Dividir el texto libre del usuario en bloques de ~5 segundos cubriendo todo el video
            oraciones = [
                s.strip()
                for s in re.split(r"(?<=[\.\!\?])\s+", custom_guion.strip())
                if s.strip()
            ]
            if not oraciones:
                oraciones = [custom_guion.strip()]
            num_bloques = max(1, len(oraciones))
            paso = dur_v / num_bloques
            emojis_ciclo = ["😱", "🔥", "⚡", "🤯", "👀", "🏆", "✨"]
            sfx_ciclo = ["whoosh", "pop", "impact", "ding", "riser", "bell"]
            for i_b, orac in enumerate(oraciones):
                t_ini = round(i_b * paso, 1)
                t_fin = round(min(dur_v, (i_b + 1) * paso), 1)
                if i_b == num_bloques - 1:
                    t_fin = round(dur_v, 1)
                emj = emojis_ciclo[i_b % len(emojis_ciclo)]
                sfx = sfx_ciclo[i_b % len(sfx_ciclo)]
                zoom_v = "1.12" if i_b % 2 == 0 else "1.06"
                lineas_guion_formateadas.append(
                    f"{t_ini:04.1f}-{t_fin:04.1f} | {orac} | {emj} | {sfx} | zoom={zoom_v}"
                )

        tit_yt = custom_tit if custom_tit else "Mira lo que ocurre en este video increíble 😱🔥 #shorts"
        if "#shorts" not in tit_yt.lower():
            tit_yt = f"{tit_yt.strip()} #shorts"
        palabras_sup = [w for w in re.sub(r"#\S+", "", custom_tit or "MIRA ESTO").strip().split() if w][:5]
        tit_sup = " ".join(palabras_sup).upper() + " 😱🔥"
        desc_yt = custom_desc if custom_desc else "No vas a creer este momento hasta el final. ¡Suscríbete para más! #shorts #viral #increible"

        contenido_txt = (
            "[CONFIGURACION]\n"
            f"VOZ = { VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT) }\n"
            "VELOCIDAD_VOZ = +12%\n"
            "VOLUMEN_VIDEO_ORIGINAL = 0.28\n"
            f"MODO_ENCUADRE = { encuadre_map.get(encuadre_var.get(), 'full') }\n"
            f"TITULO_SUPERIOR = {tit_sup}\n"
            "SUBTITULO_SUPERIOR = ¡MIRA HASTA EL FINAL!\n"
            f"TITULO_YOUTUBE = {tit_yt}\n"
            f"DESCRIPCION_YOUTUBE = {desc_yt}\n"
            "TAGS_YOUTUBE = shorts, viral, increible, español, tendencias, entretenimiento, curioso\n"
            f"PRIVACIDAD_YOUTUBE = {modo_priv}\n"
            f"PROGRAMAR_SUBIDA = {sched_str}\n\n"
            "[GUION]\n"
            + "\n".join(lineas_guion_formateadas)
            + "\n"
        )
        DEFAULT_GUION_TXT.write_text(contenido_txt, encoding="utf-8")
        return True

    def _sobreescribir_campos_custom_en_guion_txt(custom_tit: str, custom_desc: str) -> None:
        if not DEFAULT_GUION_TXT.exists():
            return
        texto = DEFAULT_GUION_TXT.read_text(encoding="utf-8", errors="ignore")
        lineas = texto.splitlines()
        nuevas: List[str] = []
        for ln in lineas:
            if custom_tit and ln.strip().upper().startswith("TITULO_YOUTUBE"):
                t_val = custom_tit.strip()
                if "#shorts" not in t_val.lower():
                    t_val = f"{t_val} #shorts"
                nuevas.append(f"TITULO_YOUTUBE = {t_val}")
            elif custom_tit and ln.strip().upper().startswith("TITULO_SUPERIOR"):
                palabras_sup = [w for w in re.sub(r"#\S+", "", custom_tit).strip().split() if w][:5]
                t_sup = (" ".join(palabras_sup).upper() + " 😱🔥") if palabras_sup else "MIRA ESTO 😱🔥"
                nuevas.append(f"TITULO_SUPERIOR = {t_sup}")
            elif custom_desc and ln.strip().upper().startswith("DESCRIPCION_YOUTUBE"):
                nuevas.append(f"DESCRIPCION_YOUTUBE = {custom_desc.strip()}")
            else:
                nuevas.append(ln)
        DEFAULT_GUION_TXT.write_text("\n".join(nuevas) + "\n", encoding="utf-8")

    def _abrir_ventana_personalizar_lote(
        videos_elegidos: List[Dict[str, object]],
        evento_listo: threading.Event,
        resultado_modal: Dict[str, bool],
    ) -> None:
        win_c = ctk.CTkToplevel(root)
        win_c.title("✍️ Personalizar Reels Seleccionados")
        win_c.geometry("680x510")
        win_c.resizable(False, False)
        win_c.configure(fg_color=BG_DARK)
        win_c.transient(root)
        win_c.grab_set()

        total_v = len(videos_elegidos)
        estado_nav = {"idx": 0}

        top_bar = ctk.CTkFrame(win_c, fg_color="transparent")
        top_bar.pack(fill="x", padx=24, pady=(16, 6))

        ctk.CTkLabel(
            top_bar,
            text="✍️  Videos Elegidos — Personaliza Título, Descripción y Guión",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        nav_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        nav_box.pack(side="right")

        btn_p = ctk.CTkButton(
            nav_box,
            text="◀",
            width=34,
            height=28,
            corner_radius=10,
            fg_color="#1e2538",
            hover_color=PURPLE_MAIN,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_p.pack(side="left", padx=(0, 6))

        lbl_nav_r = ctk.CTkLabel(
            nav_box,
            text=f"Reel 1 de {total_v}",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=CYAN_ACCENT,
            width=95,
        )
        lbl_nav_r.pack(side="left")

        btn_n = ctk.CTkButton(
            nav_box,
            text="▶",
            width=34,
            height=28,
            corner_radius=10,
            fg_color="#1e2538",
            hover_color=PURPLE_MAIN,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_n.pack(side="left", padx=(6, 0))

        # Tarjeta con la info del video elegido y su link clickeable
        info_card = ctk.CTkFrame(win_c, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        info_card.pack(fill="x", padx=24, pady=(4, 10))

        lbl_info_vid = ctk.CTkLabel(
            info_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#facc15",
            anchor="w",
        )
        lbl_info_vid.pack(fill="x", padx=16, pady=(10, 2))

        row_lnk = ctk.CTkFrame(info_card, fg_color="transparent")
        row_lnk.pack(fill="x", padx=16, pady=(0, 10))

        ent_link_elegido = ctk.CTkEntry(
            row_lnk,
            corner_radius=12,
            height=30,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            text_color=CYAN_ACCENT,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        ent_link_elegido.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _abrir_link_navegador() -> None:
            u = str(videos_elegidos[estado_nav["idx"]].get("url") or "")
            if u.startswith("http"):
                webbrowser.open(u)

        ctk.CTkButton(
            row_lnk,
            text="🌐 Ver Video en YouTube",
            command=_abrir_link_navegador,
            corner_radius=12,
            height=30,
            width=165,
            fg_color="#1e293b",
            hover_color=PURPLE_MAIN,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="right")

        # Tarjeta de Campos de Personalización
        form_card = ctk.CTkFrame(win_c, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        form_card.pack(fill="both", expand=True, padx=24, pady=(0, 10))

        ctk.CTkLabel(
            form_card,
            text="📌 Título de YouTube Shorts (deja vacío para que lo arme la IA):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=16, pady=(10, 2))

        ent_m_tit = ctk.CTkEntry(
            form_card,
            placeholder_text="Ej: ¡No vas a creer lo que hace con este control remoto! 😱🔥 #shorts",
            corner_radius=12,
            height=34,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        ent_m_tit.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            form_card,
            text="📝 Descripción y Hashtags (deja vacío para que lo arme la IA):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        ent_m_desc = ctk.CTkEntry(
            form_card,
            placeholder_text="Ej: Mirá hasta el final cómo reaccionan todos 🤣 #shorts #viral #humor",
            corner_radius=12,
            height=34,
            fg_color=INPUT_BG,
            border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        ent_m_desc.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            form_card,
            text="🎙️ Guión / Narración del Reel (escribe el texto a narrar o déjalo vacío para la IA):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        txt_m_guion = ctk.CTkTextbox(
            form_card,
            height=90,
            corner_radius=12,
            fg_color=INPUT_BG,
            border_width=1,
            border_color="#2a3147",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        txt_m_guion.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def _guardar_actual_en_mem() -> None:
            i_c = estado_nav["idx"]
            datos_custom_reels[i_c]["titulo"] = ent_m_tit.get().strip()
            datos_custom_reels[i_c]["descripcion"] = ent_m_desc.get().strip()
            datos_custom_reels[i_c]["guion"] = txt_m_guion.get("1.0", "end").strip()
            _guardar_memoria()

        def _mostrar_reel_idx() -> None:
            i_c = estado_nav["idx"]
            v_item = videos_elegidos[i_c]
            canal_str = str(v_item.get("canal") or "Link directo")
            tit_orig = str(v_item.get("titulo_orig") or "Video seleccionado")
            vistas_v = int(v_item.get("vistas") or 0)
            vistas_txt = f" · {vistas_v:,} vistas" if vistas_v > 0 else ""
            lbl_info_vid.configure(text=f"🎯 Reel #{i_c + 1} ({canal_str}{vistas_txt}): {tit_orig[:58]}")

            ent_link_elegido.configure(state="normal")
            ent_link_elegido.delete(0, tk.END)
            ent_link_elegido.insert(0, str(v_item.get("url") or ""))
            ent_link_elegido.configure(state="readonly")

            d_c = datos_custom_reels[i_c]
            ent_m_tit.delete(0, tk.END)
            if d_c.get("titulo"):
                ent_m_tit.insert(0, d_c["titulo"])
            ent_m_desc.delete(0, tk.END)
            if d_c.get("descripcion"):
                ent_m_desc.insert(0, d_c["descripcion"])
            txt_m_guion.delete("1.0", "end")
            if d_c.get("guion"):
                txt_m_guion.insert("1.0", d_c["guion"])

            lbl_nav_r.configure(text=f"Reel {i_c + 1} de {total_v}")
            btn_p.configure(state="normal" if i_c > 0 else "disabled")
            btn_n.configure(state="normal" if i_c < total_v - 1 else "disabled")

        def _prev_m() -> None:
            _guardar_actual_en_mem()
            if estado_nav["idx"] > 0:
                estado_nav["idx"] -= 1
                _mostrar_reel_idx()

        def _next_m() -> None:
            _guardar_actual_en_mem()
            if estado_nav["idx"] < total_v - 1:
                estado_nav["idx"] += 1
                _mostrar_reel_idx()

        btn_p.configure(command=_prev_m)
        btn_n.configure(command=_next_m)

        bot_row = ctk.CTkFrame(win_c, fg_color="transparent")
        bot_row.pack(fill="x", padx=24, pady=(0, 16))

        def _cancelar_m() -> None:
            resultado_modal["confirmado"] = False
            try:
                win_c.destroy()
            except Exception:
                pass
            evento_listo.set()

        def _confirmar_m() -> None:
            _guardar_actual_en_mem()
            resultado_modal["confirmado"] = True
            try:
                win_c.destroy()
            except Exception:
                pass
            evento_listo.set()

        win_c.protocol("WM_DELETE_WINDOW", _cancelar_m)

        ctk.CTkButton(
            bot_row,
            text="Cancelar",
            command=_cancelar_m,
            corner_radius=18,
            height=42,
            width=130,
            fg_color="#1e2436",
            hover_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            bot_row,
            text="🚀  COMENZAR EDICIÓN Y SUBIDA AHORA",
            command=_confirmar_m,
            corner_radius=18,
            height=42,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            text_color="#052e16",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        _mostrar_reel_idx()

    def ejecutar_flujo_1_clic() -> None:
        api_k = obtener_gemini_api_key()
        if not api_k:
            messagebox.showinfo(
                "Configura tu API Key Gratuita (1 vez)",
                "Primero ingresa tu clave gratuita de Google AI Studio en Ajustes.",
            )
            abrir_ventana_ajustes()
            return

        es_modo_canales = "Canales" in modo_fuente_var.get()
        if es_modo_canales and not lista_canales:
            messagebox.showwarning(
                "Sin canales cargados",
                "Agrega al menos un canal de YouTube arriba (pegando su link o @nombre y tocando '+ Agregar Canal').",
            )
            return

        if not editando_lock.acquire(blocking=False):
            return

        entrada_video = entry_url.get().strip().strip('"')
        voz_elegida = VOCES_DISPONIBLES.get(voz_var.get(), EDGE_VOICE_DEFAULT)
        encuadre_elegido = encuadre_map.get(encuadre_var.get(), "full")
        min_v = MAPA_MIN_VIEWS.get(min_views_var.get(), 1_000_000)
        cant_cola = MAPA_CANTIDAD_TOTAL.get(cantidad_total_var.get(), 2) if es_modo_canales else 1
        horarios_lote_plan = calcular_lista_horarios_actual()
        es_custom_activo = "Personalizado" in modo_contenido_var.get()
        pref_modelo_ia = MAPA_MODELOS_IA.get(modelo_ia_var.get(), "gemini-4-argon")

        modo_priv = "private"
        if "público" in privacidad_var.get().lower() or "publico" in privacidad_var.get().lower():
            modo_priv = "public"
        elif "oculto" in privacidad_var.get().lower():
            modo_priv = "unlisted"

        _mostrar_modo_progreso_activo(True)

        estados_milestones: List[Dict[str, str]] = [
            {"tipo": "pendiente", "texto": f"⏳ Reel {i + 1}: En cola"}
            for i in range(cant_cola)
        ]
        _renderizar_milestones_ui(estados_milestones)
        _actualizar_progreso_ui(1.0, "🚀 Buscando y seleccionando videos...", "#facc15", PURPLE_MAIN)

        def tarea_auto_total() -> None:
            stdout_orig = sys.stdout
            stderr_orig = sys.stderr
            sys.stdout = RedireccionadorSilencioso(cola_logs)
            sys.stderr = RedireccionadorSilencioso(cola_logs)
            links_subidos: List[str] = []
            try:
                from subir_a_youtube import subir_video

                horarios_lote = list(horarios_lote_plan)
                while len(horarios_lote) < cant_cola:
                    horarios_lote.append(None)

                # ==================================================================
                # FASE 1: ELEGIR TODOS LOS VIDEOS DEL LOTE PRIMERO
                # (Si se sube a Todas o Grupo, cada Reel elige video de los canales
                #  guardados en la cuenta a la que va dirigido ese Reel)
                # ==================================================================
                from subir_a_youtube import listar_cuentas_vinculadas
                todas_cuentas_v = listar_cuentas_vinculadas()
                if not todas_cuentas_v:
                    todas_cuentas_v = [{"id": "principal", "nombre": "Canal Principal"}]
                dict_cuentas_v = {str(c.get("id") or "principal"): c for c in todas_cuentas_v}

                modo_c_lote = str(estado_seleccion_cuentas.get("modo") or "una")
                cid_unica = str(estado_seleccion_cuentas.get("cuenta_id") or todas_cuentas_v[0]["id"])
                if modo_c_lote == "todas":
                    cuentas_objetivo_lote = list(todas_cuentas_v)
                elif modo_c_lote == "grupo":
                    g_ids = [g for g in (estado_seleccion_cuentas.get("grupo_ids") or []) if g in dict_cuentas_v]
                    cuentas_objetivo_lote = [dict_cuentas_v[g] for g in g_ids] if g_ids else [dict_cuentas_v.get(cid_unica, todas_cuentas_v[0])]
                else:
                    cuentas_objetivo_lote = [dict_cuentas_v.get(cid_unica, todas_cuentas_v[0])]

                videos_seleccionados: List[Dict[str, object]] = []
                ids_reservados_sesion: List[str] = []

                if es_modo_canales:
                    es_rotacion = "Rotación" in orden_canales_var.get()
                    for idx_sel in range(cant_cola):
                        num_s = idx_sel + 1
                        pref_s = f"[Reel {num_s}/{cant_cola}] " if cant_cola > 1 else ""
                        cuenta_reel_info = cuentas_objetivo_lote[idx_sel % len(cuentas_objetivo_lote)]
                        cid_reel = str(cuenta_reel_info.get("id") or "principal")
                        cnom_reel = str(cuenta_reel_info.get("nombre") or cid_reel)

                        # Usar los canales guardados específicos de esa cuenta (o lista_canales actual como respaldo)
                        canales_de_esta_cuenta = list(canales_por_cuenta.get(cid_reel) or lista_canales)
                        if not canales_de_esta_cuenta:
                            canales_de_esta_cuenta = list(lista_canales)

                        estados_milestones[idx_sel] = {"tipo": "activo", "texto": f"🔍 Reel {num_s}: Eligiendo video..."}
                        copia_ms = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_ms: _renderizar_milestones_ui(cm))

                        canales_intentar: List[str] = []
                        if es_rotacion and canales_de_esta_cuenta:
                            for offset in range(len(canales_de_esta_cuenta)):
                                pos = (estado_rotacion["idx"] + offset) % len(canales_de_esta_cuenta)
                                canales_intentar.append(canales_de_esta_cuenta[pos])
                        else:
                            canales_intentar = list(canales_de_esta_cuenta)
                            random.shuffle(canales_intentar)

                        elegido_info: Optional[Tuple[str, str, int]] = None
                        canal_usado = ""
                        for c_cand in canales_intentar:
                            c_lbl = etiqueta_corta_canal(c_cand)
                            pct_busq = 1.0 + (idx_sel / cant_cola) * 6.0
                            root.after(
                                0,
                                lambda pg=pct_busq, cl=c_lbl, p=pref_s: (
                                    btn_auto_1clic.configure(text=f"⏳  {p}ELIGIENDO SHORT EN {cl.upper()}..."),
                                    _actualizar_progreso_ui(
                                        pg,
                                        f"🔍 {p}Escaneando {cl} buscando Short viral ({min_views_var.get()})...",
                                        "#facc15",
                                        PURPLE_MAIN,
                                    ),
                                ),
                            )
                            res_viral = buscar_short_viral_en_canal(c_cand, min_views=min_v)
                            if res_viral:
                                elegido_info = res_viral
                                canal_usado = c_cand
                                registrar_video_usado(res_viral[0])
                                ids_reservados_sesion.append(res_viral[0])
                                if es_rotacion and c_cand in lista_canales:
                                    estado_rotacion["idx"] = (lista_canales.index(c_cand) + 1) % len(lista_canales)
                                    root.after(0, _guardar_memoria)
                                    root.after(0, renderizar_chips_canales)
                                break

                        if not elegido_info:
                            raise RuntimeError("No se encontraron Shorts nuevos sin usar en los canales cargados.")

                        u_vid, t_vid, v_vid = elegido_info
                        videos_seleccionados.append(
                            {
                                "url": u_vid,
                                "titulo_orig": t_vid,
                                "vistas": v_vid,
                                "canal": etiqueta_corta_canal(canal_usado),
                                "cuenta_id": cid_reel,
                                "cuenta_nombre": cnom_reel,
                            }
                        )
                        estados_milestones[idx_sel] = {"tipo": "pendiente", "texto": f"🎯 Reel {num_s}: Elegido"}
                        copia_ms2 = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_ms2: _renderizar_milestones_ui(cm))
                else:
                    u_manual = entrada_video if entrada_video else str(DEFAULT_VIDEO_INPUT)
                    c0 = cuentas_objetivo_lote[0]
                    videos_seleccionados.append(
                        {
                            "url": u_manual,
                            "titulo_orig": "Video por Link Directo",
                            "vistas": 0,
                            "canal": "Link Manual",
                            "cuenta_id": str(c0.get("id") or "principal"),
                            "cuenta_nombre": str(c0.get("nombre") or "Canal Principal"),
                        }
                    )

                # ==================================================================
                # FASE 1.5 (SOLO SI ESTÁ EN MODO PERSONALIZADO):
                # Mostrar ventana con los links elegidos para escribir Título/Desc/Guión
                # y darle a "Comenzar Edición y Subida Ahora"
                # ==================================================================
                if es_custom_activo:
                    for i_limpiar in range(len(videos_seleccionados)):
                        datos_custom_reels[i_limpiar] = {"titulo": "", "descripcion": "", "guion": ""}
                    ev_modal = threading.Event()
                    res_modal = {"confirmado": False}
                    root.after(
                        0,
                        lambda: (
                            btn_auto_1clic.configure(text="✍️  PERSONALIZA TUS REELS EN LA VENTANA..."),
                            _actualizar_progreso_ui(
                                8.0,
                                "✍️ Videos elegidos: revisa los links y personaliza Título/Descripción/Guión...",
                                CYAN_ACCENT,
                                PURPLE_MAIN,
                            ),
                            _abrir_ventana_personalizar_lote(videos_seleccionados, ev_modal, res_modal),
                        ),
                    )
                    ev_modal.wait()
                    if not res_modal.get("confirmado"):
                        def _on_cancel() -> None:
                            _actualizar_progreso_ui(0.0, "⏹ Operación cancelada antes de editar.", TEXT_MUTED, PURPLE_MAIN)
                            _mostrar_modo_progreso_activo(False)

                        root.after(0, _on_cancel)
                        return

                # ==================================================================
                # FASE 2: DESCARGAR, CREAR GUIÓN (IA O CUSTOM), RENDERIZAR Y SUBIR
                # ==================================================================
                for idx_lote, info_sel in enumerate(videos_seleccionados):
                    num_actual = idx_lote + 1
                    pref_lote = f"[Reel {num_actual}/{cant_cola}] " if cant_cola > 1 else ""
                    sched_actual = horarios_lote[idx_lote] if idx_lote < len(horarios_lote) else None
                    sched_str = sched_actual if sched_actual else "no"
                    url_descargar = str(info_sel.get("url") or "")
                    titulo_orig = str(info_sel.get("titulo_orig") or "")
                    vistas_orig = int(info_sel.get("vistas") or 0)

                    base_pct_reel = (idx_lote / cant_cola) * 100.0
                    ancho_pct_reel = 100.0 / cant_cola

                    def _set_subprogreso(frac_interna: float, msg_est: str, col_est: str = "#facc15") -> None:
                        pct_g = base_pct_reel + (max(0.0, min(1.0, frac_interna)) * ancho_pct_reel)
                        root.after(
                            0,
                            lambda pg=pct_g, m=msg_est, c=col_est: _actualizar_progreso_ui(pg, m, c, PURPLE_MAIN),
                        )

                    def _actualizar_milestone_actual(tipo_m: str, texto_corto: str) -> None:
                        estados_milestones[idx_lote] = {"tipo": tipo_m, "texto": texto_corto}
                        copia_m = [dict(x) for x in estados_milestones]
                        root.after(0, lambda cm=copia_m: _renderizar_milestones_ui(cm))

                    posible_local = Path(url_descargar)
                    if posible_local.exists() and posible_local.is_file():
                        ruta_video_usar = posible_local
                    else:
                        _actualizar_milestone_actual("activo", f"📥 Reel {num_actual}: Descargando...")
                        _set_subprogreso(
                            0.12,
                            f"📥 {pref_lote}Descargando '{titulo_orig[:38]}...' ({vistas_orig:,} vistas)"
                            if vistas_orig > 0
                            else f"📥 {pref_lote}Descargando video de YouTube en máxima calidad...",
                        )
                        ruta_video_usar = descargar_video_youtube(url_descargar)
                        registrar_video_usado(url_descargar)

                    # Verificar si el usuario personalizó Título / Descripción / Guión para este Reel
                    custom_data = datos_custom_reels[idx_lote] if idx_lote < len(datos_custom_reels) else {}
                    c_tit = custom_data.get("titulo", "").strip() if es_custom_activo else ""
                    c_desc = custom_data.get("descripcion", "").strip() if es_custom_activo else ""
                    c_guion = custom_data.get("guion", "").strip() if es_custom_activo else ""

                    guion_ya_listo = False
                    if es_custom_activo and c_guion:
                        _actualizar_milestone_actual("activo", f"✍️ Reel {num_actual}: Guión propio...")
                        _set_subprogreso(0.26, f"✍️ {pref_lote}Aplicando tu guión y título personalizados...")
                        guion_ya_listo = _aplicar_custom_a_guion_txt(
                            idx_reel=idx_lote,
                            ruta_video=ruta_video_usar,
                            custom_tit=c_tit,
                            custom_desc=c_desc,
                            custom_guion=c_guion,
                            sched_str=sched_str,
                            modo_priv="privado" if modo_priv == "private" else modo_priv,
                        )

                    if not guion_ya_listo:
                        _actualizar_milestone_actual("activo", f"🧠 Reel {num_actual}: Creando guión IA...")
                        root.after(
                            0,
                            lambda p=pref_lote: btn_auto_1clic.configure(
                                text=f"⏳  {p}CREANDO GUIÓN VIRAL CON IA..."
                            ),
                        )
                        _set_subprogreso(
                            0.22,
                            f"🧠 {pref_lote}Analizando video completo y contexto real con IA ({pref_modelo_ia})...",
                        )
                        generar_guion_con_gemini_flash(
                            ruta_video=ruta_video_usar,
                            api_key=api_k,
                            schedule_str=sched_str,
                            modo_privacidad="privado" if modo_priv == "private" else modo_priv,
                            contexto_titulo_orig=titulo_orig,
                            modelo_preferido=pref_modelo_ia,
                        )
                        if es_custom_activo and (c_tit or c_desc):
                            _sobreescribir_campos_custom_en_guion_txt(c_tit, c_desc)

                    _actualizar_milestone_actual("activo", f"🎬 Reel {num_actual}: Editando 60 FPS...")
                    root.after(
                        0,
                        lambda p=pref_lote: btn_auto_1clic.configure(
                            text=f"⏳  {p}RENDERIZANDO SHORT CON GPU..."
                        ),
                    )

                    def _cb_edicion(pct_edit: float, txt_edit: str) -> None:
                        # Mapea 0..100% de la edición al tramo 0.30 .. 0.88 del Reel actual
                        frac_interna = 0.30 + (max(0.0, min(100.0, pct_edit)) / 100.0) * 0.58
                        _set_subprogreso(frac_interna, f"{pref_lote}{txt_edit}", CYAN_ACCENT)

                    ruta_final = asyncio.run(
                        editar_video_con_guion(
                            ruta_video=ruta_video_usar,
                            ruta_guion=DEFAULT_GUION_TXT,
                            voz_override=voz_elegida,
                            modo_encuadre_override=encuadre_elegido,
                            progreso_cb=_cb_edicion,
                        )
                    )
                    ultimo_video_generado[0] = ruta_final

                    # Cuenta de YouTube asignada a este Reel en el lote
                    id_cuenta_usar = str(info_sel.get("cuenta_id") or estado_seleccion_cuentas.get("cuenta_id") or "principal")
                    nombre_cuenta_subida = str(info_sel.get("cuenta_nombre") or id_cuenta_usar)

                    _actualizar_milestone_actual("activo", f"🚀 Reel {num_actual}: Subiendo a {nombre_cuenta_subida[:16]}...")
                    root.after(
                        0,
                        lambda p=pref_lote, nc=nombre_cuenta_subida[:18]: btn_auto_1clic.configure(
                            text=f"⏳  {p}SUBIENDO A {nc.upper()}..."
                        ),
                    )
                    _set_subprogreso(
                        0.92,
                        f"🚀 {pref_lote}Subiendo y programando Short en '{nombre_cuenta_subida}'...",
                        "#c084fc",
                    )

                    vid_id = subir_video(
                        ruta_video=ruta_final,
                        titulo=c_tit if (es_custom_activo and c_tit) else None,
                        descripcion=c_desc if (es_custom_activo and c_desc) else None,
                        estado_privacidad=modo_priv,
                        publish_at=sched_actual,
                        ruta_guion=DEFAULT_GUION_TXT,
                        cuenta_id=id_cuenta_usar,
                    )
                    incrementar_cuota_diaria(video_id=vid_id)
                    root.after(0, refrescar_barra_cuota)
                    url_short = f"https://youtube.com/shorts/{vid_id}"
                    links_subidos.append(url_short)

                    _actualizar_milestone_actual("subido", f"✅ Reel {num_actual}: ¡Subido!")
                    _set_subprogreso(
                        1.0,
                        f"✅ {pref_lote}Reel {num_actual} subido con éxito ({sched_actual or modo_priv.upper()})",
                        GREEN_ACCENT,
                    )

                # Si se programaron varios días, actualizar la fecha recordada al último día usado
                if horarios_lote and horarios_lote[-1]:
                    ultima_f = str(horarios_lote[-1]).split(" ")[0]
                    fecha_elegida_var.set(ultima_f)
                    root.after(
                        0,
                        lambda uf=ultima_f: (
                            btn_calendario.configure(text=_formatear_boton_fecha(uf)),
                            refrescar_plan_ui(),
                        ),
                    )

                def _on_ok() -> None:
                    txt_fin = (
                        f"✅ 100% — ¡Se subieron todos los Reels ({len(links_subidos)}/{cant_cola}) con éxito!"
                        if cant_cola > 1
                        else "✅ 100% — ¡Se subió el Reel a YouTube con éxito!"
                    )
                    _actualizar_progreso_ui(100.0, txt_fin, GREEN_ACCENT, GREEN_ACCENT)
                    root.after(2800, lambda: _mostrar_modo_progreso_activo(False) if not editando_lock.locked() else None)

                root.after(0, _on_ok)
            except Exception as exc:
                def _on_err(err_msg: str = str(exc)) -> None:
                    lbl_estado.configure(text=f"❌ Error: {err_msg}", text_color="#ef4444")
                    barra_progreso_proceso.configure(progress_color="#ef4444")
                    root.after(4500, lambda: _mostrar_modo_progreso_activo(False) if not editando_lock.locked() else None)

                root.after(0, _on_err)
            finally:
                sys.stdout = stdout_orig
                sys.stderr = stderr_orig
                editando_lock.release()

        threading.Thread(target=tarea_auto_total, daemon=True).start()

    btn_auto_1clic.configure(command=ejecutar_flujo_1_clic)
    root.after(200, vaciar_cola_logs)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg1 = sys.argv[1].strip()
        if arg1.lower() == "--auto" and len(sys.argv) > 2:
            url_auto = sys.argv[2].strip()
            sched_auto = sys.argv[3].strip() if len(sys.argv) > 3 else "auto"
            priv_auto = sys.argv[4].strip() if len(sys.argv) > 4 else "private"
            v_desc = descargar_video_youtube(url_auto)
            generar_guion_con_gemini_flash(v_desc, obtener_gemini_api_key(), schedule_str=sched_auto, modo_privacidad=priv_auto)
            r_out = asyncio.run(editar_video_con_guion(v_desc, DEFAULT_GUION_TXT))
            from subir_a_youtube import subir_video
            subir_video(r_out, estado_privacidad=priv_auto, publish_at=sched_auto if sched_auto != "auto" else None, ruta_guion=DEFAULT_GUION_TXT)
        else:
            guion_arg = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_GUION_TXT
            if arg1.startswith("http://") or arg1.startswith("https://") or "youtube.com" in arg1 or "youtu.be" in arg1:
                video_descargado = descargar_video_youtube(arg1)
                asyncio.run(editar_video_con_guion(video_descargado, guion_arg))
            else:
                video_arg = Path(arg1).resolve()
                asyncio.run(editar_video_con_guion(video_arg, guion_arg))
    else:
        # Instancia única con Mutex de Windows: si la app ya está corriendo en segundo plano
        # (por haberla cerrado con la X mientras editaba), le envía la señal para volver a
        # mostrar esa misma ventana con su barra de progreso intacta en lugar de abrir otra vacía.
        _mutex_handle = None
        try:
            import ctypes
            _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MateoEditorShortsStudioSingleInstance")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                TEMP_DIR.mkdir(parents=True, exist_ok=True)
                (TEMP_DIR / "mostrar_ventana.signal").write_text("1", encoding="utf-8")
                sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            pass
        iniciar_aplicacion_gui()
