# -*- coding: utf-8 -*-
import os
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from .config import (
    WIDTH, HEIGHT, FONTS_DIR, PalabraSubtitulo, SegmentoVideoGuion
)

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



