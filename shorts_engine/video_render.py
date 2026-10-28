# -*- coding: utf-8 -*-
import asyncio
import cv2
import json
import math
import os
import random
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .config import (
    WIDTH, HEIGHT, FPS, CPU_THREADS, WIN_NO_WINDOW, WIN_STARTUPINFO,
    BASE_DIR, ASSETS_DIR, EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, MUSICA_DIR,
    TEMP_DIR, OUTPUT_DIR, ConfigGuion, SegmentoVideoGuion, PalabraSubtitulo,
    MODO_ENCUADRE_DEFAULT, VOLUMEN_VOZ_NARRADOR, VOLUMEN_AUDIO_VIDEO_ORIGINAL,
    VOLUMEN_MUSICA_FONDO, SUBTITLE_OFFSET_SEC, DURACION_CALLOUTS_DEFAULT, _quitar_acentos
)
from .parser_guion import cargar_guion_video
from .subtitulos import renderizar_subtitulos_luminosos, cargar_fuente, asegurar_fuente_mrbeast
from .audio_tts import (
    generar_voz_y_timestamps_segmento, alinear_palabras_con_onda_real, masterizar_voz_estudio_ffmpeg,
    intentar_voz_elevenlabs, GestorAudioSFX
)
from .vision_tracker import RastreadorObjetivosVideo

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

    def dibujar_flecha_outro_like(
        self,
        lienzo: Image.Image,
        t_seg: float,
        dur_seg: float = 1.0,
    ) -> None:
        """
        Dibuja la flecha roja animada apuntando directamente hacia el botón de Like
        de la interfaz móvil de YouTube Shorts (margen derecho, X ≈ 985, Y ≈ 1040)
        con rebote elástico y resplandor neón de alta calidad.
        """
        if self.flecha_base is None:
            return

        if t_seg < 0.12:
            p_in = max(0.0, t_seg / 0.12)
            escala = 0.50 + 0.55 * math.sin(p_in * math.pi * 0.5)
            alpha_f = min(1.0, p_in * 1.5)
        elif t_seg > dur_seg - 0.10:
            p_out = max(0.0, (dur_seg - t_seg) / 0.10)
            escala = 0.85 + 0.15 * p_out
            alpha_f = p_out
        else:
            escala = 1.0
            alpha_f = 1.0

        tam_flecha = max(120, int(round(360 * escala)))
        flecha_scaled = self.flecha_base.resize((tam_flecha, tam_flecha), Image.Resampling.LANCZOS)
        # Rotar 180° para que la punta señale a la derecha (+X) directamente hacia el botón de Like
        flecha_rot = flecha_scaled.rotate(180, resample=Image.Resampling.BICUBIC, expand=True)

        if alpha_f < 0.99:
            r, g, b, a = flecha_rot.split()
            a = a.point(lambda p: int(p * alpha_f))
            flecha_rot = Image.merge("RGBA", (r, g, b, a))

        target_x = 985.0
        target_y = 1040.0
        rebote = 25.0 * abs(math.sin(t_seg * 10.0))
        dist_punta = 15.0 + rebote

        fw, fh = flecha_rot.size
        pos_x = int(round(target_x - fw - dist_punta))
        pos_y = int(round(target_y - fh / 2.0))

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






def obtener_info_video(ruta_video: Path) -> Tuple[float, int, int, float]:
    """
    Devuelve (duracion_seg, ancho, alto, fps) exactos del video de entrada.
    """
    if not ruta_video.exists():
        raise FileNotFoundError(f"No se encontró el archivo de video: {ruta_video}")
    w, h, fps, dur = 1080, 1920, 30.0, 0.0
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
                "-of", "json",
                str(ruta_video),
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        if res.returncode == 0 and res.stdout:
            d = json.loads(res.stdout)
            st = d.get("streams", [{}])[0]
            fmt = d.get("format", {})
            w = int(st.get("width") or 1080)
            h = int(st.get("height") or 1920)
            fps_str = str(st.get("r_frame_rate") or "30/1")
            fps = eval(fps_str) if "/" in fps_str else float(fps_str)
            dur = float(st.get("duration") or fmt.get("duration") or 0.0)
    except Exception:
        pass

    if dur <= 0.1 or fps <= 0:
        try:
            cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap = cv2.VideoCapture(str(ruta_video))
            fps = fps or cap.get(cv2.CAP_PROP_FPS) or 30.0
            n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            w = w or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
            h = h or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
            cap.release()
            if dur <= 0.1 and n_frames > 0 and fps > 0:
                dur = float(n_frames) / float(fps)
        except (Exception, SystemError, BaseException):
            pass

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
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={WIDTH}:{HEIGHT},boxblur=24:4,eq=brightness=-0.12[bg_b];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos[fg_s];"
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
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
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
        proc = subprocess.Popen(
            cmd_ff,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
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
        try:
            cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap = cv2.VideoCapture(str(ruta_video))
            fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_ini) * 1000.0)
            max_leer = max(2, int(round(dur_clip * fps_orig)))
            for _ in range(max_leer):
                try:
                    ret, frame_bgr = cap.read()
                except (Exception, SystemError, BaseException):
                    break
                if not ret or frame_bgr is None:
                    break
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                h, w, _ = frame_rgb.shape
                scale = max(WIDTH / float(w), HEIGHT / float(h))
                nw, nh = int(round(w * scale)), int(round(h * scale))
                resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
                x0 = (nw - WIDTH) // 2
                y0 = (nh - HEIGHT) // 2
                frames_raw.append(resized[y0 : y0 + HEIGHT, x0 : x0 + WIDTH].copy())
            cap.release()
        except (Exception, SystemError, BaseException):
            pass

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


def detectar_encoder_video(forzar_cpu: bool = False) -> Tuple[str, List[str]]:
    """
    Detecta y prueba qué codificador de video H.264 acelerado por hardware
    (NVIDIA NVENC, AMD AMF o Intel QSV) o CPU (libx264) es compatible
    y funcional en la GPU/sistema actual mediante una prueba real de 1 frame.
    Si forzar_cpu=True, utiliza libx264 equilibrado sin tocar la GPU (ideal al jugar).
    """
    hilos_cpu = max(4, min(8, CPU_THREADS // 2))
    args_cpu = [
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-threads", str(hilos_cpu), "-pix_fmt", "yuv420p",
    ]
    if forzar_cpu:
        return ("libx264", args_cpu)

    global _ENCODER_SELECCIONADO
    if _ENCODER_SELECCIONADO is not None:
        return _ENCODER_SELECCIONADO

    candidatos: List[Tuple[str, List[str]]] = [
        # NVIDIA NVENC (preset p6 alta calidad, 16M bitrate para 1080p)
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p"]),
        # AMD Radeon AMF (modo calidad, 16M bitrate para 1080p)
        ("h264_amf", ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", "16M", "-maxrate", "20M", "-pix_fmt", "yuv420p"]),
        # Intel Quick Sync Video
        ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryslow", "-b:v", "16M", "-maxrate", "20M", "-pix_fmt", "yuv420p"]),
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
            res = subprocess.run(
                cmd_test,
                capture_output=True,
                check=False,
                creationflags=WIN_NO_WINDOW,
                startupinfo=WIN_STARTUPINFO,
            )
            if res.returncode == 0:
                _ENCODER_SELECCIONADO = (nombre, args)
                return _ENCODER_SELECCIONADO
        except Exception:
            continue

    # Fallback equilibrado por CPU (libx264 preset fast CRF 18)
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

    # El último bloque del video jamás debe tener flecha de seguimiento de video,
    # porque el editor agrega automáticamente el Outro de 1 segundo con flecha apuntando al botón de Like.
    if segmentos and segmentos[-1].flecha:
        segmentos[-1].flecha = None


def seleccionar_musica_fondo(tono: Optional[str] = None) -> Optional[Path]:
    """
    Selecciona la pista de música de fondo apropiada según el tono del video:
    - 'triste' / 'sad' / 'drama' -> busca Triste.* en la carpeta /musica
    - 'inspiracional' / 'emotivo' / 'superacion' -> busca Inspiracional.* en la carpeta /musica
    - cualquier otro tono (o por defecto) -> elige aleatoriamente entre los fondos
      (Fondo 1, Fondo 2, Fondo 3, Fondo 4 u otros temas generales en /musica).
    """
    MUSICA_DIR.mkdir(parents=True, exist_ok=True)
    archivos = [
        p for p in MUSICA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".ogg")
    ]
    if not archivos:
        return None

    t_clean = (tono or "").strip().lower()

    # 1. Tono Triste
    if any(k in t_clean for k in ("trist", "sad", "dram", "pena", "llor", "depre")):
        pistas_tristes = [p for p in archivos if "trist" in p.stem.lower() or "sad" in p.stem.lower()]
        if pistas_tristes:
            return random.choice(pistas_tristes)

    # 2. Tono Inspiracional / Emotivo / Superación
    if any(k in t_clean for k in ("inspirac", "motivac", "emotiv", "superac", "epico_final", "triumph")):
        pistas_insp = [p for p in archivos if "inspirac" in p.stem.lower() or "insp" in p.stem.lower()]
        if pistas_insp:
            return random.choice(pistas_insp)

    # 3. Fondos generales (excluir pistas específicas como Triste o Inspiracional a menos que sean las únicas)
    fondos = [
        p for p in archivos
        if "trist" not in p.stem.lower()
        and "sad" not in p.stem.lower()
        and "inspirac" not in p.stem.lower()
        and "insp" not in p.stem.lower()
    ]
    if fondos:
        return random.choice(fondos)

    return random.choice(archivos)


async def editar_video_con_guion(
    ruta_video: Path,
    ruta_guion: Path,
    voz_override: Optional[str] = None,
    modo_encuadre_override: Optional[str] = None,
    progreso_cb: Optional[object] = None,
    cancelar_check: Optional[Callable[[], bool]] = None,
    encoder_override: Optional[str] = None,
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

    for carpeta in [EMOJIS_DIR, FONTS_DIR, FOTOS_DIR, SFX_DIR, MUSICA_DIR, TEMP_DIR, OUTPUT_DIR]:
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

    # 2.5 Generar Outro automático de 1 segundo ("¡Dejá tu like!") con freeze-frame y flecha
    dur_outro_seg = 1.0
    total_frames_outro = int(round(FPS * dur_outro_seg))
    texto_outro_tts = "¡Dejá tu láik!"
    ruta_mp3_outro = TEMP_DIR / "seg_outro_like.mp3"
    ruta_wav_outro = ruta_mp3_outro.with_suffix(".wav")

    # Si la voz configurada es Giuseppe (italiana), usamos Tomás para un llamado nativo en español con energía YouTuber
    voz_outro = config.voz_narrador
    if "it-IT" in str(voz_outro):
        voz_outro = "es-AR-TomasNeural"

    print(f"[*] Generando audio y mezcla para Outro final de 1 segundo (¡Dejá tu like!) con voz {voz_outro}...")
    dur_voz_outro, palabras_sub_outro, _, _ = await generar_voz_y_timestamps_segmento(
        texto_outro_tts,
        ruta_mp3_outro,
        voz_edge=voz_outro,
        dur_objetivo_seg=dur_outro_seg,
    )
    # Asegurar texto limpio y llamativo en los subtítulos de pantalla
    if palabras_sub_outro and len(palabras_sub_outro) >= 3:
        palabras_sub_outro[0].texto = "¡DEJA"
        palabras_sub_outro[1].texto = "TU"
        palabras_sub_outro[2].texto = "LIKE!"
    rms_env_outro = calcular_envolvente_rms(ruta_wav_outro, FPS)
    ruta_mix_outro_wav = TEMP_DIR / "seg_outro_mix.wav"
    gestor_sfx.mezclar_audio_segmento(
        ruta_voz_wav=ruta_wav_outro,
        duracion_total_seg=dur_outro_seg,
        sfx_lista=["pop"],
        tiene_emoji_o_flecha=True,
        ruta_salida_wav=ruta_mix_outro_wav,
    )
    archivos_audio_seg.append(ruta_mix_outro_wav)

    _notificar_prog(0.38, "Masterizando pista de audio final con música de fondo...")

    # 3. Unir el audio maestro de la voz IA + Efectos SFX (el audio original del video descargado se MUTEA completamente)
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

    # 3.5 Selección y mezcla inteligente de Música de Fondo desde /musica según el tono del Short
    ruta_audio_final = TEMP_DIR / "audio_final_combinado.wav"
    dur_total_audio = 0.0
    try:
        with wave.open(str(ruta_voz_maestra), "r") as wf_check:
            dur_total_audio = wf_check.getnframes() / float(wf_check.getframerate())
    except Exception:
        dur_total_audio = dur_video_origen + dur_outro_seg

    tono_efectivo = config.tono_video
    if not tono_efectivo or tono_efectivo in ("auto", "fondo", "neutral"):
        texto_completo = f"{config.titulo_youtube} {config.descripcion_youtube} {' '.join(s.texto_voz for s in config.segmentos)}".lower()
        if any(w in texto_completo for w in ("triste", "tristeza", "llorando", "llorar", "pena", "depresivo", "lamentable", "tragedia")):
            tono_efectivo = "triste"
        elif any(w in texto_completo for w in ("inspiracional", "inspiracion", "motivacion", "superacion", "emotivo", "emocionante", "lagrimas de emocion", "salvar", "rescate")):
            tono_efectivo = "inspiracional"

    pista_musica = seleccionar_musica_fondo(tono_efectivo)

    if pista_musica and pista_musica.exists():
        vol_bgm = max(0.04, min(0.30, getattr(config, "volumen_musica", VOLUMEN_MUSICA_FONDO)))
        fade_start = max(0.5, dur_total_audio - 1.8)
        print(f"[*] Música de fondo elegida: '{pista_musica.name}' (tono: '{tono_efectivo}', volumen: {vol_bgm:.2f}).")
        filter_str = (
            f"[1:a]volume={vol_bgm:.2f},afade=t=out:st={fade_start:.2f}:d=1.8[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=disabled[aout]"
        )
        res_mix = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(ruta_voz_maestra),
                "-stream_loop", "-1", "-i", str(pista_musica),
                "-filter_complex", filter_str,
                "-map", "[aout]",
                "-ar", "44100", "-ac", "1",
                str(ruta_audio_final),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
        if res_mix.returncode != 0 or not ruta_audio_final.exists():
            print("[!] Falló la mezcla de música de fondo, usando narración y SFX limpios.")
            ruta_audio_final = ruta_voz_maestra
        else:
            print(f"[+] Audio final masterizado con éxito (Voz IA + Ruidos/SFX + Música '{pista_musica.stem}').")
    else:
        print("[*] No se encontró pista de música de fondo en /musica, usando narración y SFX limpios.")
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
    forzar_cpu = (encoder_override == "cpu")
    encoder, args_codec = detectar_encoder_video(forzar_cpu=forzar_cpu)

    def _ejecutar_render(enc_actual: str, args_actual: List[str]) -> Path:
        if "amf" in enc_actual:
            tipo_gpu = "Aceleración Hardware AMD Radeon (AMF)"
        elif "nvenc" in enc_actual:
            tipo_gpu = "Aceleración Hardware NVIDIA (NVENC)"
        elif "qsv" in enc_actual:
            tipo_gpu = "Aceleración Hardware Intel (QSV)"
        else:
            tipo_gpu = "Procesador CPU Equilibrado (libx264 fast CRF 18)"
        print(f"[*] Renderizando Short final con {enc_actual} [{tipo_gpu}] ({WIDTH}x{HEIGHT} a {FPS} FPS)...")

        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgb24",
            "-r", str(FPS),
            "-i", "-",
            "-i", str(ruta_audio_final),
            *args_actual,
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-color_range", "tv",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(ruta_mp4_final),
        ]

        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ruta_err_ffmpeg = TEMP_DIR / "ffmpeg_render_error.log"
        f_err = open(ruta_err_ffmpeg, "w", encoding="utf-8", errors="replace")
        proceso_ffmpeg = subprocess.Popen(
            cmd_ffmpeg,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=f_err,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )

        ultimo_frame_lienzo: Optional[Image.Image] = None

        try:
            # 5. Renderizar segmento por segmento con seguimiento de objetivos (Optical Flow) y subtítulos luminosos
            for idx_seg, (seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env) in enumerate(datos_segmentos):
                if cancelar_check and cancelar_check():
                    try:
                        if proceso_ffmpeg and proceso_ffmpeg.stdin:
                            proceso_ffmpeg.stdin.close()
                        proceso_ffmpeg.terminate()
                        f_err.close()
                    except Exception:
                        pass
                    if ruta_mp4_final.exists():
                        try:
                            ruta_mp4_final.unlink()
                        except Exception:
                            pass
                    raise InterruptedError("Edición cancelada por el usuario.")
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
                        try:
                            if proceso_ffmpeg.stdin:
                                proceso_ffmpeg.stdin.close()
                        except Exception:
                            pass
                        proceso_ffmpeg.terminate()
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

                    if idx_seg == len(datos_segmentos) - 1 and f_idx == total_frames_seg - 1:
                        ultimo_frame_lienzo = lienzo.copy()

                    if proceso_ffmpeg.stdin:
                        try:
                            proceso_ffmpeg.stdin.write(lienzo.convert("RGB").tobytes())
                        except OSError as e:
                            try:
                                proceso_ffmpeg.stdin.close()
                            except Exception:
                                pass
                            proceso_ffmpeg.terminate()
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

            # 6. Renderizar Outro automático de 1 segundo (Freeze-Frame + Desenfoque + Flecha al Like + Subtítulo Luminoso)
            if ultimo_frame_lienzo is not None and total_frames_outro > 0:
                _notificar_prog(0.97, "Renderizando outro de 1 segundo (¡Deja tu like!)...")
                print("[*] Renderizando Outro de 1 segundo (Freeze-frame + desenfoque + flecha al Like)...")
                bg_blur = ultimo_frame_lienzo.filter(ImageFilter.GaussianBlur(16))
                oscurecedor = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 95))
                lienzo_base_outro = Image.alpha_composite(bg_blur.convert("RGBA"), oscurecedor)

                for f_idx in range(total_frames_outro):
                    t_seg = f_idx / float(FPS)
                    rms_val = float(rms_env_outro[f_idx]) if f_idx < len(rms_env_outro) else 0.0
                    lienzo_out = lienzo_base_outro.copy()

                    # Flecha Roja al botón de Like de YouTube Shorts (X: 985, Y: 1040)
                    gestor_assets.dibujar_flecha_outro_like(
                        lienzo=lienzo_out,
                        t_seg=t_seg,
                        dur_seg=dur_outro_seg,
                    )

                    # Subtítulo neón animado
                    renderizar_subtitulos_luminosos(
                        lienzo=lienzo_out,
                        palabras=palabras_sub_outro,
                        t_actual=t_seg,
                        nivel_voz_rms=rms_val,
                        y_centro=1340,
                        palabras_verdes_extra={"LIKE!", "LIKE"},
                    )

                    if proceso_ffmpeg.poll() is not None:
                        try:
                            if proceso_ffmpeg.stdin:
                                proceso_ffmpeg.stdin.close()
                        except Exception:
                            pass
                        proceso_ffmpeg.terminate()
                        f_err.flush()
                        f_err.close()
                        err_txt = ""
                        try:
                            err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"FFmpeg se cerró antes de tiempo durante el outro con código {proceso_ffmpeg.returncode}.\n"
                            f"Detalles:\n{err_txt}"
                        )

                    if proceso_ffmpeg.stdin:
                        try:
                            proceso_ffmpeg.stdin.write(lienzo_out.convert("RGB").tobytes())
                        except OSError as e:
                            try:
                                proceso_ffmpeg.stdin.close()
                            except Exception:
                                pass
                            proceso_ffmpeg.terminate()
                            f_err.flush()
                            f_err.close()
                            err_txt = ""
                            try:
                                err_txt = ruta_err_ffmpeg.read_text(encoding="utf-8", errors="replace").strip()
                            except Exception:
                                pass
                            raise RuntimeError(f"Error al enviar frame de outro a FFmpeg ({e}).\nDetalles:\n{err_txt}") from e

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

            return ruta_mp4_final
        finally:
            try:
                if not f_err.closed:
                    f_err.close()
            except Exception:
                pass

    try:
        resultado = _ejecutar_render(encoder, args_codec)
    except Exception as e:
        if isinstance(e, InterruptedError):
            raise
        if encoder != "libx264":
            print(f"[!] Falló la GPU ({encoder}): {e}")
            print("[*] Reintentando renderizado automáticamente con Procesador CPU equilibrado (libx264 fast CRF 18)...")
            _notificar_prog(0.40, "GPU sin memoria (posible juego abierto). Reintentando por CPU equilibrada...")
            if ruta_mp4_final.exists():
                try:
                    ruta_mp4_final.unlink()
                except Exception:
                    pass
            enc_cpu, args_cpu = detectar_encoder_video(forzar_cpu=True)
            resultado = _ejecutar_render(enc_cpu, args_cpu)
        else:
            raise

    _notificar_prog(1.0, "Renderizado 60 FPS completado con éxito.")
    print("=" * 78)
    print(f"[ÉXITO] Short generado y listo en: {resultado}")
    print("=" * 78)
    return resultado


