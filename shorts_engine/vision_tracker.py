# -*- coding: utf-8 -*-
import cv2
import math
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
from .config import WIDTH, HEIGHT, FPS, TEMP_DIR, ASSETS_DIR, _quitar_acentos

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



