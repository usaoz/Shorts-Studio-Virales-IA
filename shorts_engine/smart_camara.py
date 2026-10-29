# -*- coding: utf-8 -*-
import cv2
import numpy as np
from typing import List, Tuple, Optional


class SmartCamara916:
    """
    Motor de Auto-Framing 9:16 con física de gimbal (Resorte Críticamente Amortiguado),
    Zona Muerta (Deadband) y reseteo instantáneo en cortes de escena.
    100% NumPy + OpenCV estándar (Sin dependencias pesadas).
    """

    def __init__(self, ancho_analisis: int = 320, fps_muestreo: float = 6.0):
        self.ancho_analisis = ancho_analisis
        self.fps_muestreo = fps_muestreo
        self.detector_rostros = None
        if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            ruta_haar = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if Path(ruta_haar).exists():
                try:
                    clf = cv2.CascadeClassifier(ruta_haar)
                    if not clf.empty():
                        self.detector_rostros = clf
                except Exception:
                    self.detector_rostros = None

    @staticmethod
    def _kernel_gaussiano_1d(sigma: float) -> np.ndarray:
        """Reemplazo puro en NumPy para scipy.ndimage.gaussian_filter1d."""
        radio = max(1, int(round(3.0 * sigma)))
        x = np.arange(-radio, radio + 1, dtype=np.float64)
        k = np.exp(-0.5 * (x / sigma) ** 2)
        return k / np.sum(k)

    def _suavizar_array_1d(self, arr: np.ndarray, sigma: float) -> np.ndarray:
        if len(arr) < 3 or sigma <= 0:
            return arr.copy()
        kernel = self._kernel_gaussiano_1d(sigma)
        pad = len(kernel) // 2
        arr_pad = np.pad(arr, (pad, pad), mode="edge")
        return np.convolve(arr_pad, kernel, mode="valid")

    def _detectar_centro_interes_x(
        self, frame_peq: np.ndarray, gris_prev: Optional[np.ndarray]
    ) -> Tuple[float, np.ndarray, float]:
        """
        Retorna: (x_objetivo_normalizado [0..1], gris_actual, score_cambio_escena)
        """
        h, w = frame_peq.shape[:2]
        gris = cv2.cvtColor(frame_peq, cv2.COLOR_BGR2GRAY)

        # 1. Calcular diferencia de histograma para saber si hubo corte de plano brusco
        score_corte = 0.0
        if gris_prev is not None:
            h1 = cv2.calcHist([gris_prev], [0], None, [32], [0, 256])
            h2 = cv2.calcHist([gris], [0], None, [32], [0, 256])
            cv2.normalize(h1, h1)
            cv2.normalize(h2, h2)
            score_corte = float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))

        # 2. Prioridad 1: Detección de rostros (si el detector está disponible)
        if self.detector_rostros is not None:
            try:
                rostros = self.detector_rostros.detectMultiScale(
                    gris, scaleFactor=1.2, minNeighbors=4, minSize=(int(h * 0.12), int(h * 0.12))
                )
                if len(rostros) > 0:
                    areas = [rw * rh for (_, _, rw, rh) in rostros]
                    idx_max = int(np.argmax(areas))
                    rx, ry, rw, rh = rostros[idx_max]
                    xc_rostro = (rx + rw * 0.5) / float(w)
                    return float(np.clip(xc_rostro, 0.0, 1.0)), gris, score_corte
            except Exception:
                pass

        # 3. Prioridad 2: Mapa combinado de Movimiento + Saliencia de Bordes/Saturación
        sobel_x = cv2.Sobel(gris, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gris, cv2.CV_32F, 0, 1, ksize=3)
        mag_bordes = cv2.magnitude(sobel_x, sobel_y)

        hsv = cv2.cvtColor(frame_peq, cv2.COLOR_BGR2HSV).astype(np.float32)
        saturacion = hsv[:, :, 1]

        if gris_prev is not None and score_corte < 0.45:
            diff_mov = cv2.absdiff(gris, gris_prev).astype(np.float32)
        else:
            diff_mov = np.zeros_like(mag_bordes)

        # Ponderar la franja central vertical (donde ocurre la acción útil)
        pesos_y = np.exp(-0.5 * ((np.linspace(-1.0, 1.0, h)) / 0.65) ** 2)[:, np.newaxis]
        mapa_energia = (diff_mov * 2.2 + mag_bordes * 0.35 + saturacion * 0.25) * pesos_y

        # Proyección horizontal (perfil 1D de energía en X)
        perfil_x = np.sum(mapa_energia, axis=0)
        total_e = float(np.sum(perfil_x))
        if total_e < 1e-3:
            return 0.5, gris, score_corte

        umbral_e = np.percentile(perfil_x, 75)
        mascara_top = np.maximum(0.0, perfil_x - umbral_e)
        if np.sum(mascara_top) < 1e-3:
            return 0.5, gris, score_corte

        coords_x = np.linspace(0.0, 1.0, w)
        xc_norm = float(np.sum(coords_x * mascara_top) / np.sum(mascara_top))
        return float(np.clip(xc_norm, 0.0, 1.0)), gris, score_corte

    def calcular_trayectoria_recorte(
        self,
        ruta_video: str,
        fps_salida: float = 60.0,
        ancho_salida_crop: int = 1080,
        alto_salida_crop: int = 1920,
    ) -> Tuple[np.ndarray, int, int]:
        """
        Analiza un video horizontal y devuelve array NumPy con la coordenada `x_top_left`
        exacta para cada fotograma a 60 FPS, junto a (ancho_recorte_nativo, alto_recorte_nativo).
        """
        cap = cv2.VideoCapture(str(ruta_video))
        if not cap.isOpened():
            raise ValueError(f"No se pudo abrir el video para Auto-Framing: {ruta_video}")

        w_orig = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h_orig = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames_orig = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duracion_seg = max(0.1, total_frames_orig / fps_orig)

        h_crop_nativo = h_orig
        w_crop_nativo = int(round(h_orig * (ancho_salida_crop / float(alto_salida_crop))))
        w_crop_nativo = min(w_orig, w_crop_nativo)

        max_x_offset = max(0, w_orig - w_crop_nativo)
        total_frames_60 = max(1, int(round(duracion_seg * fps_salida)))
        if max_x_offset <= 4:
            cap.release()
            return np.full(total_frames_60, max_x_offset // 2, dtype=np.int32), w_crop_nativo, h_crop_nativo

        paso_frames = max(1, int(round(fps_orig / self.fps_muestreo)))
        escala = self.ancho_analisis / float(w_orig)
        h_peq = max(36, int(round(h_orig * escala)))

        tiempos_muestra: List[float] = []
        objetivos_x_norm: List[float] = []
        cortes_flag: List[bool] = []

        gris_prev = None
        idx_f = 0

        while True:
            ret = cap.grab()
            if not ret:
                break
            if idx_f % paso_frames == 0:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    peq = cv2.resize(frame, (self.ancho_analisis, h_peq), interpolation=cv2.INTER_AREA)
                    xc_n, gris_prev, score_corte = self._detectar_centro_interes_x(peq, gris_prev)
                    tiempos_muestra.append(idx_f / fps_orig)
                    objetivos_x_norm.append(xc_n)
                    cortes_flag.append(score_corte > 0.42)
            idx_f += 1

        cap.release()

        if len(tiempos_muestra) < 2:
            return np.full(total_frames_60, max_x_offset // 2, dtype=np.int32), w_crop_nativo, h_crop_nativo

        t_60 = np.linspace(0.0, duracion_seg, total_frames_60)
        target_60 = np.interp(t_60, tiempos_muestra, objetivos_x_norm)

        cortes_60 = np.zeros(total_frames_60, dtype=bool)
        for t_c, es_corte in zip(tiempos_muestra, cortes_flag):
            if es_corte:
                idx_60 = int(np.clip(round(t_c * fps_salida), 0, total_frames_60 - 1))
                cortes_60[idx_60] = True

        # SIMULACIÓN DEL GIMBAL VIRTUAL (Amortiguador Crítico + Deadband)
        dt = 1.0 / fps_salida
        omega = 3.2
        zeta = 1.05
        deadband = 0.08
        vel_max = 0.55

        cam_x = np.zeros(total_frames_60, dtype=np.float64)
        pos_actual = float(target_60[0])
        vel_actual = 0.0
        objetivo_anclado = pos_actual

        for i in range(total_frames_60):
            if cortes_60[i]:
                pos_actual = float(target_60[i])
                vel_actual = 0.0
                objetivo_anclado = pos_actual
            else:
                error_bruto = float(target_60[i]) - objetivo_anclado
                if abs(error_bruto) > deadband:
                    objetivo_anclado += (error_bruto - np.sign(error_bruto) * deadband) * 0.35

                aceleracion = (omega ** 2) * (objetivo_anclado - pos_actual) - (2.0 * zeta * omega * vel_actual)
                vel_actual += aceleracion * dt
                vel_actual = float(np.clip(vel_actual, -vel_max, vel_max))
                pos_actual += vel_actual * dt

            cam_x[i] = np.clip(pos_actual, 0.0, 1.0)

        xc_px = cam_x * w_orig
        x_left = np.round(xc_px - (w_crop_nativo * 0.5)).astype(np.int32)
        x_left = np.clip(x_left, 0, max_x_offset)

        return x_left, w_crop_nativo, h_crop_nativo


# =====================================================================
# COMPILADOR DE TRAYECTORIA 60 FPS -> EXPRESIÓN CROP NATIVA FFMPEG
# =====================================================================

def compilar_trayectoria_a_expresion_ffmpeg(
    x_left_segmento: np.ndarray,
    fps: float = 60.0,
    paso_nodos_frames: int = 12,
) -> str:
    """
    Convierte un sub-vector de coordenadas `x_left` (a 60 FPS) de un segmento de video
    en una expresión matemática C ultrarrápida para el filtro `crop` de FFmpeg.
    Usa interpolación lineal por tramos cada `paso_nodos_frames` (12 frames = 0.2s)
    para mantener el string corto y lograr suavidad sub-píxel idéntica al gimbal.
    """
    n = len(x_left_segmento)
    if n == 0:
        return "0"

    # Si la cámara está en la zona muerta (quieta) durante todo el segmento, usar constante fija
    if int(np.max(x_left_segmento) - np.min(x_left_segmento)) <= 2:
        return str(int(np.round(np.mean(x_left_segmento))))

    indices = list(range(0, n, paso_nodos_frames))
    if indices[-1] != n - 1:
        indices.append(n - 1)

    partes: List[str] = []
    for k in range(len(indices) - 1):
        i0 = indices[k]
        i1 = indices[k + 1]
        x0 = float(x_left_segmento[i0])
        x1 = float(x_left_segmento[i1])
        dn = max(1, i1 - i0)
        pendiente = (x1 - x0) / float(dn)

        if abs(pendiente) < 1e-3:
            tramo_expr = f"{int(round(x0))}"
        else:
            tramo_expr = f"({x0:.1f}+{pendiente:.3f}*(n-{i0}))"

        partes.append(f"if(lt(n,{i1}),{tramo_expr},")

    ultimo_val = f"{int(round(float(x_left_segmento[indices[-1]])))}"
    cierres = ")" * len(partes)
    return "".join(partes) + ultimo_val + cierres


def calcular_trayectoria_x_escalada_1920(
    camara_smart: SmartCamara916,
    ruta_video: str,
    fps_salida: float = 60.0,
    ancho_target: int = 1080,
    alto_target: int = 1920,
) -> Tuple[np.ndarray, int]:
    """
    Ejecuta `SmartCamara916` y convierte las coordenadas al espacio ya escalado a altura 1920
    (ej. 3414x1920 para un video 16:9), devolviendo:
      - `x_left_1920`: array int32 con la coordenada X izquierda (0 .. w_escalado - 1080) para cada frame a 60 FPS.
      - `w_escalado`: el ancho total del video cuando su altura se escala a 1920.
    """
    x_left_nativo, w_crop_nativo, h_crop_nativo = camara_smart.calcular_trayectoria_recorte(
        ruta_video=str(ruta_video),
        fps_salida=fps_salida,
        ancho_salida_crop=ancho_target,
        alto_salida_crop=alto_target,
    )

    factor_escala = float(alto_target) / float(max(1, h_crop_nativo))

    cap = cv2.VideoCapture(str(ruta_video))
    w_orig = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    cap.release()

    w_escalado = int(round(w_orig * factor_escala))
    if w_escalado % 2 != 0:
        w_escalado += 1

    max_x_1920 = max(0, w_escalado - ancho_target)
    x_left_1920 = np.clip(np.round(x_left_nativo * factor_escala), 0, max_x_1920).astype(np.int32)
    return x_left_1920, w_escalado


def transformar_coordenada_global_a_crop_916(
    xc_pct_global: float,
    yc_pct_global: float,
    ancho_pct_global: float,
    alto_pct_global: float,
    x_left_en_frame_ancla: int,
    w_escalado_1920: int,
    ancho_crop: int = 1080,
) -> Tuple[bool, float, float, float, float]:
    """
    Si Gemini analizó el video original completo (16:9) y devolvió un `box:[ymin,xmin,ymax,xmax]`,
    su coordenada `xc_pct_global` está referida al ancho completo (`w_escalado_1920`, ej. 3414px).
    Esta función la traduce al porcentaje exacto dentro de la ventana recortada de 1080px.

    Si el objeto quedó fuera del recorte 9:16, devuelve `visible=False` para cancelar el círculo.
    """
    if w_escalado_1920 <= ancho_crop:
        return True, xc_pct_global, yc_pct_global, ancho_pct_global, alto_pct_global

    x_obj_global_px = (xc_pct_global / 100.0) * w_escalado_1920
    w_obj_global_px = (ancho_pct_global / 100.0) * w_escalado_1920

    x_rel_px = x_obj_global_px - float(x_left_en_frame_ancla)

    # Verificar visibilidad dentro de los 1080px (con margen del 5%)
    if x_rel_px < (ancho_crop * 0.05) or x_rel_px > (ancho_crop * 0.95):
        return False, 50.0, 50.0, 18.0, 18.0

    nuevo_xc_pct = (x_rel_px / float(ancho_crop)) * 100.0
    nuevo_ancho_pct = min(65.0, (w_obj_global_px / float(ancho_crop)) * 100.0)

    return True, float(nuevo_xc_pct), float(yc_pct_global), float(nuevo_ancho_pct), float(alto_pct_global)

