# -*- coding: utf-8 -*-
"""
Módulo de alto rendimiento y utilidades optimizadas para Shorts Studio.
Contiene caché de máscaras, semántica de colores de subtítulos, validación de ritmo
y conteo de palabras (3.7 pal/s), recorte de silencios TTS y micro-color grading.
"""

import os
import re
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# 1. CACHÉ GLOBAL DE MÁSCARAS Y COLORES SEMÁNTICOS
# =====================================================================
_RADIAL_MASK_CACHE = {}

PALABRAS_PELIGRO = {
    "trampa", "peligro", "cuidado", "error", "venganza", "golpe", "caída",
    "mira", "secreto", "falso", "engaño", "engaña", "nunca", "jamás", "peor",
    "destroza", "explosión", "robo", "culpa", "miedo", "terror", "ataque"
}

PALABRAS_EXITO = {
    "victoria", "ganador", "épica", "épico", "genial", "increíble", "dinero",
    "premio", "millones", "fortuna", "perfecta", "perfecto", "logra", "triunfo",
    "maestro", "campeón", "oro", "récord", "inteligente", "astuta", "astuto"
}

def obtener_mascara_radial(h: int, w: int) -> np.ndarray:
    """Devuelve la máscara radial precalculada en float32 (evita np.ogrid en cada frame)."""
    key = (h, w)
    if key not in _RADIAL_MASK_CACHE:
        Y, X = np.ogrid[:h, :w]
        cy, cx = h / 2.0, w / 2.0
        max_dist = np.sqrt(cx**2 + cy**2)
        dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / max_dist
        mask = np.clip((dist - 0.35) / 0.65, 0.0, 1.0).astype(np.float32)
        _RADIAL_MASK_CACHE[key] = mask[:, :, np.newaxis]
    return _RADIAL_MASK_CACHE[key]

def aplicar_alerta_roja_rapida(frame: np.ndarray, t: float) -> np.ndarray:
    """Aplica la viñeta alerta_roja usando la máscara en caché a máxima velocidad."""
    h, w = frame.shape[:2]
    mask = obtener_mascara_radial(h, w)
    pulso = 0.55 + 0.45 * np.sin(t * 10.0)
    intensidad = mask * (0.65 * pulso)

    out = frame.astype(np.float32)
    out[:, :, 0] = out[:, :, 0] * (1.0 - intensidad[:, :, 0]) + 255.0 * intensidad[:, :, 0]
    out[:, :, 1] = out[:, :, 1] * (1.0 - intensidad[:, :, 0] * 0.85)
    out[:, :, 2] = out[:, :, 2] * (1.0 - intensidad[:, :, 0] * 0.85)
    return np.clip(out, 0, 255).astype(np.uint8)

def obtener_color_semantico(palabra: str, idx_global: int) -> tuple:
    """Determina el color RGBA de la palabra activa según su semántica viral."""
    limpia = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ]', '', palabra).lower()
    if limpia in PALABRAS_PELIGRO:
        return (255, 45, 45, 255)   # Rojo Neón (Peligro / Tensión)
    if limpia in PALABRAS_EXITO:
        return (0, 255, 102, 255)   # Verde Vibrante (Éxito / Premio)
    if "!" in palabra or "¡" in palabra or "?" in palabra or "¿" in palabra:
        return (255, 230, 0, 255)   # Amarillo MrBeast
    return (255, 230, 0, 255) if idx_global % 2 == 0 else (0, 245, 255, 255)


# =====================================================================
# 2. VALIDADOR DE RITMO Y CONTEO DE PALABRAS (3.7 PALABRAS / SEG)
# =====================================================================
def parsear_segundos_rango(rango_str: str) -> float:
    """Convierte '00:00 - 00:05' en la duración en segundos (ej. 5.0)."""
    try:
        partes = rango_str.split("-")
        def a_seg(mm_ss):
            p = mm_ss.strip().split(":")
            return int(p[0]) * 60 + float(p[1])
        return max(0.5, a_seg(partes[1]) - a_seg(partes[0]))
    except Exception:
        return 5.0

def evaluar_ritmo_bloque(rango_tiempo: str, texto: str) -> dict:
    """
    Evalúa si el bloque cumple la regla de 3.7 palabras/segundo.
    Retorna dict con: palabras, duracion, pps, estado ('OK', 'CORTO', 'LARGO'), etiqueta.
    """
    dur = parsear_segundos_rango(rango_tiempo)
    palabras_lista = [p for p in texto.strip().split() if p]
    n_pal = len(palabras_lista)
    pps = n_pal / dur if dur > 0 else 0.0

    # Rangos ideales según duración (base 3.7 pal/seg)
    min_ideal = max(1, int(round(dur * 3.4)))
    max_ideal = int(round(dur * 4.0))

    if n_pal < min_ideal:
        estado = "CORTO"
        icono = "⚠️ Corto"
    elif n_pal > max_ideal:
        estado = "LARGO"
        icono = "🚨 Largo"
    else:
        estado = "OK"
        icono = "✅ OK"

    etiqueta = f"{n_pal} pal ({pps:.1f}/s) {icono}"
    return {
        "palabras": n_pal,
        "duracion": dur,
        "pps": round(pps, 2),
        "min_ideal": min_ideal,
        "max_ideal": max_ideal,
        "estado": estado,
        "etiqueta": etiqueta
    }


# =====================================================================
# 3. LIMPIEZA DE SILENCIOS TTS Y AJUSTE PRECISO DE AUDIO CON FFMPEG
# =====================================================================
def recortar_silencios_tts(input_audio: str, output_audio: str, ffmpeg_exe: str = "ffmpeg") -> bool:
    """
    Elimina los silencios muertos al inicio y al final que deja edge-tts
    para que los bloques se encadenen sin pausas artificiales.
    """
    try:
        filtro = (
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-42dB,"
            "areverse"
        )
        cmd = [
            ffmpeg_exe, "-y", "-i", input_audio,
            "-af", filtro,
            output_audio
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(output_audio) and os.path.getsize(output_audio) > 512
    except Exception:
        return False


# =====================================================================
# 4. MICRO-COLOR GRADING RÁPIDO (ANTI-REUSED CONTENT Y MAYOR IMPACTO)
# =====================================================================
_LUT_CONTRASTE = np.clip((np.arange(256, dtype=np.float32) - 128.0) * 1.06 + 130.0, 0, 255).astype(np.uint8)

def realzar_frame_viral(frame: np.ndarray) -> np.ndarray:
    """Aplica una tabla LUT instantánea (+6% contraste y brillo sutil) en <0.6ms con SIMD."""
    try:
        import cv2
        return cv2.LUT(frame, _LUT_CONTRASTE)
    except Exception:
        return _LUT_CONTRASTE[frame]
