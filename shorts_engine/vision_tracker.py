# -*- coding: utf-8 -*-
import cv2
import math
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
from .config import (
    WIDTH,
    HEIGHT,
    FPS,
    TEMP_DIR,
    ASSETS_DIR,
    _quitar_acentos,
    parsear_directiva_circulo,
    ObjetivoCirculoIA,
)

# ==============================================================================
# SEGUIMIENTO INTELIGENTE DE OBJETIVOS (GROUNDED-ANCHOR + FORWARD-BACKWARD LK)
# ==============================================================================
class RastreadorObjetivosVideo:
    """
    Motor híbrido de visión artificial de alta precisión para Shorts Studio:
      1) Anclaje semántico por Bounding Box nativo de Gemini (box:[ymin,xmin,ymax,xmax]@t_ancla).
      2) Adquisición morfológica de puntos Shi-Tomasi en el 85% central del núcleo del objeto,
         ponderados con decaimiento Gaussiano para eliminar bordes del fondo.
      3) Flujo Óptico Piramidal Bidireccional de Lucas-Kanade con verificación Forward-Backward
         (fb_err < 1.5 px) y rechazo de outliers por desviación mediana (MAD).
      4) Suavizado Gaussiano 1D cinemático sin dependencias pesadas (puro NumPy).
      5) Fail-Safe automático: si no se detectan puntos consistentes en el núcleo, se aborta
         el círculo para evitar enmarcar fondos vacíos o prendas estáticas.
    """

    ESC_TRACK = 3.0
    W_TR = int(WIDTH // ESC_TRACK)   # 360
    H_TR = int(HEIGHT // ESC_TRACK)  # 640

    ZONAS_NOMINALES: Dict[str, Tuple[float, float, float]] = {
        "centro": (0.50, 0.45, 78.0),
        "izquierda": (0.28, 0.45, 72.0),
        "derecha": (0.72, 0.45, 72.0),
        "arriba": (0.50, 0.26, 72.0),
        "abajo": (0.50, 0.62, 72.0),
        "arriba_izq": (0.28, 0.27, 68.0),
        "arriba_der": (0.72, 0.27, 68.0),
        "abajo_izq": (0.28, 0.60, 68.0),
        "abajo_der": (0.72, 0.60, 68.0),
        "auto": (0.50, 0.45, 240.0),
    }

    @classmethod
    def _preprocesar_gris(cls, frame_rgb: np.ndarray) -> np.ndarray:
        """Redimensiona el cuadro a 360x640 y aplica CLAHE para destacar micro-texturas."""
        pequeno = cv2.resize(frame_rgb, (cls.W_TR, cls.H_TR), interpolation=cv2.INTER_AREA)
        gris = cv2.cvtColor(pequeno, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gris)

    @classmethod
    def _adquirir_puntos_semilla_en_caja(
        cls,
        gris: np.ndarray,
        xc_px: float,
        yc_px: float,
        w_caja_px: float,
        h_caja_px: float,
    ) -> Optional[np.ndarray]:
        """
        Extrae esquinas Shi-Tomasi concentradas en el 85% interno de la caja,
        ponderando puntos cercanos al centroide para evitar bordes externos del fondo.
        """
        h_img, w_img = gris.shape[:2]
        semi_w = max(8.0, (w_caja_px * 0.85) / 2.0)
        semi_h = max(8.0, (h_caja_px * 0.85) / 2.0)

        x1 = int(max(0, round(xc_px - semi_w)))
        y1 = int(max(0, round(yc_px - semi_h)))
        x2 = int(min(w_img, round(xc_px + semi_w)))
        y2 = int(min(h_img, round(yc_px + semi_h)))

        if (x2 - x1) < 6 or (y2 - y1) < 6:
            return None

        mascara = np.zeros_like(gris, dtype=np.uint8)
        mascara[y1:y2, x1:x2] = 255

        pts = cv2.goodFeaturesToTrack(
            gris,
            maxCorners=45,
            qualityLevel=0.04,
            minDistance=3,
            mask=mascara,
            blockSize=5,
            useHarrisDetector=False,
        )

        if pts is None or len(pts) < 3:
            pts = cv2.goodFeaturesToTrack(
                gris,
                maxCorners=30,
                qualityLevel=0.015,
                minDistance=3,
                mask=mascara,
                blockSize=5,
            )

        if pts is None or len(pts) < 3:
            return None

        coords = pts.reshape(-1, 2)
        distancias = np.hypot(coords[:, 0] - xc_px, coords[:, 1] - yc_px)
        radio_max = max(1.0, float(np.hypot(semi_w, semi_h)))
        pesos = np.exp(-0.5 * (distancias / (radio_max * 0.65)) ** 2)

        umbral_peso = np.percentile(pesos, 20)
        coords_filtradas = coords[pesos >= umbral_peso]
        if len(coords_filtradas) < 3:
            coords_filtradas = coords

        return coords_filtradas.reshape(-1, 1, 2).astype(np.float32)

    @classmethod
    def _paso_lk_forward_backward(
        cls,
        gris_prev: np.ndarray,
        gris_curr: np.ndarray,
        pts_prev: np.ndarray,
        lk_params: dict,
        umbral_fb: float = 1.5,
    ) -> np.ndarray:
        """
        Lucas-Kanade de ida (A -> B) y vuelta (B -> A).
        Filtra puntos con error de ciclo superior a umbral_fb y descarta outliers de movimiento.
        """
        if pts_prev is None or len(pts_prev) == 0:
            return np.empty((0, 1, 2), dtype=np.float32)

        pts_next, st1, _ = cv2.calcOpticalFlowPyrLK(gris_prev, gris_curr, pts_prev, None, **lk_params)
        if pts_next is None:
            return np.empty((0, 1, 2), dtype=np.float32)

        pts_back, st2, _ = cv2.calcOpticalFlowPyrLK(gris_curr, gris_prev, pts_next, None, **lk_params)
        if pts_back is None:
            return np.empty((0, 1, 2), dtype=np.float32)

        fb_err = np.linalg.norm(pts_prev.reshape(-1, 2) - pts_back.reshape(-1, 2), axis=1)
        validos = (st1.flatten() == 1) & (st2.flatten() == 1) & (fb_err < umbral_fb)

        pts_buenos = pts_next[validos]
        if len(pts_buenos) < 4:
            return pts_buenos

        desplazamientos = pts_buenos.reshape(-1, 2) - pts_prev[validos].reshape(-1, 2)
        mediana_dx_dy = np.median(desplazamientos, axis=0)
        desviacion = np.linalg.norm(desplazamientos - mediana_dx_dy, axis=1)
        mad = np.median(desviacion) + 1e-4

        coherentes = desviacion <= max(2.2, 3.0 * mad)
        return pts_buenos[coherentes]

    @classmethod
    def _propagar_secuencia_bidireccional(
        cls,
        frames_gris: List[np.ndarray],
        idx_ancla: int,
        pts_semilla: np.ndarray,
        xc_init: float,
        yc_init: float,
        w_caja: float,
        h_caja: float,
        lk_params: dict,
    ) -> List[Tuple[float, float]]:
        n_frames = len(frames_gris)
        trayectoria = [(xc_init, yc_init)] * n_frames

        centro_ancla = np.median(pts_semilla.reshape(-1, 2), axis=0)
        offset_x = xc_init - float(centro_ancla[0])
        offset_y = yc_init - float(centro_ancla[1])

        # 1. HACIA ADELANTE (idx_ancla -> final)
        pts_actuales = pts_semilla.copy()
        ultimo_cx, ultimo_cy = xc_init, yc_init

        for i in range(idx_ancla + 1, n_frames):
            pts_nuevos = cls._paso_lk_forward_backward(frames_gris[i - 1], frames_gris[i], pts_actuales, lk_params)
            if len(pts_nuevos) >= 3:
                mediana = np.median(pts_nuevos.reshape(-1, 2), axis=0)
                ultimo_cx = float(mediana[0]) + offset_x
                ultimo_cy = float(mediana[1]) + offset_y
                pts_actuales = pts_nuevos
                if len(pts_actuales) < 7:
                    reseed = cls._adquirir_puntos_semilla_en_caja(
                        frames_gris[i], ultimo_cx, ultimo_cy, w_caja * 0.85, h_caja * 0.85
                    )
                    if reseed is not None and len(reseed) >= 4:
                        pts_actuales = reseed
                        nueva_med = np.median(pts_actuales.reshape(-1, 2), axis=0)
                        offset_x = ultimo_cx - float(nueva_med[0])
                        offset_y = ultimo_cy - float(nueva_med[1])
            trayectoria[i] = (ultimo_cx, ultimo_cy)

        # 2. HACIA ATRÁS (idx_ancla -> 0)
        pts_actuales = pts_semilla.copy()
        centro_ancla = np.median(pts_semilla.reshape(-1, 2), axis=0)
        offset_x = xc_init - float(centro_ancla[0])
        offset_y = yc_init - float(centro_ancla[1])
        ultimo_cx, ultimo_cy = xc_init, yc_init

        for i in range(idx_ancla - 1, -1, -1):
            pts_nuevos = cls._paso_lk_forward_backward(frames_gris[i + 1], frames_gris[i], pts_actuales, lk_params)
            if len(pts_nuevos) >= 3:
                mediana = np.median(pts_nuevos.reshape(-1, 2), axis=0)
                ultimo_cx = float(mediana[0]) + offset_x
                ultimo_cy = float(mediana[1]) + offset_y
                pts_actuales = pts_nuevos
            trayectoria[i] = (ultimo_cx, ultimo_cy)

        return trayectoria

    @classmethod
    def _suavizar_serie_1d(cls, valores: np.ndarray, sigma: float = 2.5) -> np.ndarray:
        """Suavizado Gaussiano 1D en NumPy puro (sin requerir scipy)."""
        if len(valores) < 5:
            return valores
        rad = max(2, int(math.ceil(sigma * 2.5)))
        k_x = np.arange(-rad, rad + 1, dtype=np.float32)
        kernel = np.exp(-(k_x ** 2) / (2.0 * sigma * sigma))
        kernel /= np.sum(kernel)
        pad_v = np.pad(valores, (rad, rad), mode="edge")
        return np.convolve(pad_v, kernel, mode="valid")

    @classmethod
    def _parsear_punto_base(cls, spec: str) -> Tuple[float, float, float, bool]:
        s = _quitar_acentos(spec.strip().lower())
        for mod in (":grande", ":chico", ":medio", ":pequeno", ":big", ":small"):
            s = s.replace(mod, "")
        s = s.strip()
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
                return x_tr, y_tr, 75.0, True
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

        mov_acum = np.zeros((h, w), dtype=np.float32)
        for i in range(1, len(grises_iniciales)):
            diff = cv2.absdiff(grises_iniciales[i], grises_iniciales[i - 1]).astype(np.float32)
            mov_acum += diff
        if len(grises_iniciales) > 1:
            mov_acum /= float(len(grises_iniciales) - 1)
        mov_norm = mov_acum / (float(np.max(mov_acum)) + 1e-5)

        if rgb_inicial is not None:
            hsv = cv2.cvtColor(rgb_inicial, cv2.COLOR_RGB2HSV).astype(np.float32)
            sat_norm = hsv[:, :, 1] / 255.0
        else:
            sat_norm = np.zeros((h, w), dtype=np.float32)

        gx = cv2.Sobel(g0, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g0, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(gx, gy)
        grad_norm = grad_mag / (float(np.max(grad_mag)) + 1e-5)

        saliencia = cv2.GaussianBlur(mov_norm * 3.20 + sat_norm * 0.18 + grad_norm * 0.95, (17, 17), 0)

        yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
        zona_torso = (xx >= w * 0.35) & (xx <= w * 0.65) & (yy >= h * 0.33) & (yy <= h * 0.52)
        mov_torso = float(np.mean(mov_norm[zona_torso])) if np.any(zona_torso) else 0.0
        if mov_torso < 0.22:
            saliencia[zona_torso] *= 0.30

        peso_zona = np.exp(-(((xx - x_nom) ** 2 + (yy - y_nom) ** 2) / (2.0 * (radio_busq ** 2))))

        limite_y_inf = int(h * 0.76)
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

        peso_sal = 0.75 if es_exacta else 0.92
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
    def calcular_trayectoria(
        cls,
        frames_rgb: List[np.ndarray],
        especificacion: Optional[str],
        t_inicio_seg: float = 0.0,
        t_fin_seg: float = 5.0,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Calcula la trayectoria del objetivo a 60 FPS en coordenadas 1080x1920.
        Soporta Grounding semántico nativo por bounding box, trayectorias continuas
        o seguimiento por optical flow. Si el objetivo es inválido o no existe,
        devuelve None activando el fail-safe para no dibujar círculos erróneos.
        """
        n_frames = len(frames_rgb)
        if n_frames == 0 or not especificacion:
            return None

        spec_clean = _quitar_acentos(str(especificacion).strip().lower())

        # Caso 0: Detección semántica de objeto (Grounding de Gemini)
        if "box:" in spec_clean or "box:[" in spec_clean or ("," in spec_clean and "->" not in spec_clean):
            info_c = parsear_directiva_circulo(especificacion, t_inicio_seg, t_fin_seg)
            if info_c.activo:
                return cls._rastrear_caja_grounding(
                    frames_rgb=frames_rgb,
                    info_c=info_c,
                    t_inicio_seg=t_inicio_seg,
                    t_fin_seg=t_fin_seg,
                )
            if "box:" in spec_clean or "box:[" in spec_clean:
                # Si falló la validación semántica (ej. cayó en torso completo o etiqueta prohibida), descartar círculo
                return None

        # Si se pidió zona vaga para un círculo ("auto", "centro", "medio", etc.), bloquearlo deliberadamente
        if spec_clean in ("auto", "centro", "center", "medio", "middle", "ninguno", "none", "false"):
            return None

        # Caso A: Trayectoria explícita "inicio->fin" (ideal para flechas)
        if "->" in spec_clean:
            p_ini_str, p_fin_str = spec_clean.split("->", 1)
            x0_tr, y0_tr, _, _ = cls._parsear_punto_base(p_ini_str)
            x1_tr, y1_tr, _, _ = cls._parsear_punto_base(p_fin_str)
            xs_full = np.zeros(n_frames, dtype=np.float32)
            ys_full = np.zeros(n_frames, dtype=np.float32)
            for i in range(n_frames):
                u = i / float(max(1, n_frames - 1))
                u_s = u * u * (3.0 - 2.0 * u)
                xs_full[i] = (x0_tr + (x1_tr - x0_tr) * u_s) * cls.ESC_TRACK
                ys_full[i] = (y0_tr + (y1_tr - y0_tr) * u_s) * cls.ESC_TRACK
            return list(zip(xs_full.tolist(), ys_full.tolist()))

        # Caso B: Flecha apuntando a una zona con Optical Flow clásico
        x_nom, y_nom, radio_busq, es_exacta = cls._parsear_punto_base(spec_clean)
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

        tx, ty = cls._adquirir_objetivo_saliente(
            grises[: min(8, len(grises))], rgbs_peq[0], x_nom, y_nom, radio_busq, es_exacta
        )
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
            diff_medio = float(np.mean(cv2.absdiff(g_curr, g_prev)))
            if diff_medio > 26.0:
                new_tx, new_ty = cls._adquirir_objetivo_saliente(
                    grises[k : min(len(grises), k + 5)], rgbs_peq[k], x_nom, y_nom, radio_busq, es_exacta
                )
                tx = 0.60 * tx + 0.40 * new_tx
                ty = 0.60 * ty + 0.40 * new_ty
                pts_activos = cls._extraer_puntos_locales(g_curr, tx, ty, radio=48)
                xs_m.append(tx)
                ys_m.append(ty)
                continue

            if pts_activos is None or len(pts_activos) < 6:
                pts_activos = cls._extraer_puntos_locales(g_prev, tx, ty, radio=48)

            if pts_activos is not None and len(pts_activos) >= 4:
                pts_next, st_f, _ = cv2.calcOpticalFlowPyrLK(g_prev, g_curr, pts_activos, None, **lk_params)
                if pts_next is not None and st_f is not None:
                    p0_v = pts_activos[st_f.reshape(-1) == 1].reshape(-1, 2)
                    p1_v = pts_next[st_f.reshape(-1) == 1].reshape(-1, 2)
                    if len(p1_v) >= 3:
                        deltas = p1_v - p0_v
                        dx = float(np.median(deltas[:, 0]))
                        dy = float(np.median(deltas[:, 1]))
                        tx = float(np.clip(tx + dx * 0.50 + (x_nom - tx) * 0.15, x_nom - 45.0, x_nom + 45.0))
                        ty = float(np.clip(ty + dy * 0.50 + (y_nom - ty) * 0.15, y_nom - 45.0, y_nom + 45.0))
                        pts_activos = p1_v.reshape(-1, 1, 2)

            xs_m.append(tx)
            ys_m.append(ty)

        t_muestras = np.array(indices_muestra, dtype=np.float32)
        t_todos = np.arange(n_frames, dtype=np.float32)
        xs_interp = np.interp(t_todos, t_muestras, np.array(xs_m, dtype=np.float32))
        ys_interp = np.interp(t_todos, t_muestras, np.array(ys_m, dtype=np.float32))

        xs_smooth = cls._suavizar_serie_1d(xs_interp, sigma=3.2)
        ys_smooth = cls._suavizar_serie_1d(ys_interp, sigma=3.2)

        xs_full = np.clip(xs_smooth * cls.ESC_TRACK, 55.0, WIDTH - 55.0)
        ys_full = np.clip(ys_smooth * cls.ESC_TRACK, 65.0, HEIGHT - 180.0)
        return list(zip(xs_full.tolist(), ys_full.tolist()))

    @classmethod
    def _rastrear_caja_grounding(
        cls,
        frames_rgb: List[np.ndarray],
        info_c: ObjetivoCirculoIA,
        t_inicio_seg: float,
        t_fin_seg: float,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Rastrea el objeto anclado semánticamente por la caja de Gemini con
        Forward-Backward LK y cancelación de puntos de fondo.
        """
        n_frames = len(frames_rgb)
        if n_frames == 0:
            return None

        # 1. Preprocesar cuadros a escala de gris mejorada con CLAHE
        frames_gris = [cls._preprocesar_gris(f) for f in frames_rgb]

        # 2. Coordenadas iniciales en espacio de trabajo (360x640)
        xc_tr = (info_c.xc_pct / 100.0) * cls.W_TR
        yc_tr = (info_c.yc_pct / 100.0) * cls.H_TR
        w_caja_tr = (info_c.ancho_pct / 100.0) * cls.W_TR
        h_caja_tr = (info_c.alto_pct / 100.0) * cls.H_TR

        # 3. Índice del frame ancla
        dur_seg = max(0.05, t_fin_seg - t_inicio_seg)
        t_ancla_rel = (info_c.t_ancla - t_inicio_seg) if info_c.t_ancla is not None else (dur_seg * 0.35)
        frac_ancla = max(0.0, min(1.0, t_ancla_rel / dur_seg))
        idx_ancla = int(round(frac_ancla * (n_frames - 1)))

        # 4. Semillas Shi-Tomasi en el núcleo del objeto
        pts_semilla = cls._adquirir_puntos_semilla_en_caja(
            frames_gris[idx_ancla], xc_tr, yc_tr, w_caja_tr, h_caja_tr
        )

        # FAIL-SAFE: Si el objeto no tiene esquinas/texturas suficientes, abortar círculo limpiamente
        if pts_semilla is None or len(pts_semilla) < 3:
            print(f"[*] Objeto no encontrado con claridad para '{info_c.etiqueta}' (círculo omitido por seguridad).")
            return None

        lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )

        # 5. Propagación bidireccional desde el fotograma ancla
        tray_tr = cls._propagar_secuencia_bidireccional(
            frames_gris=frames_gris,
            idx_ancla=idx_ancla,
            pts_semilla=pts_semilla,
            xc_init=xc_tr,
            yc_init=yc_tr,
            w_caja=w_caja_tr,
            h_caja=h_caja_tr,
            lk_params=lk_params,
        )

        # 6. Suavizado 1D cinemático
        xs_tr = np.array([p[0] for p in tray_tr], dtype=np.float32)
        ys_tr = np.array([p[1] for p in tray_tr], dtype=np.float32)
        xs_smooth = cls._suavizar_serie_1d(xs_tr, sigma=2.5)
        ys_smooth = cls._suavizar_serie_1d(ys_tr, sigma=2.5)

        # 7. Escalar a espacio 1080x1920 con márgenes seguros
        xs_full = np.clip(xs_smooth * cls.ESC_TRACK, 55.0, WIDTH - 55.0)
        ys_full = np.clip(ys_smooth * cls.ESC_TRACK, 65.0, HEIGHT - 180.0)

        print(f"[+] Círculo rojo anclado con éxito en '{info_c.etiqueta}' (ancla t={info_c.t_ancla:.1f}s, {len(pts_semilla)} puntos firmes).")
        return list(zip(xs_full.tolist(), ys_full.tolist()))
