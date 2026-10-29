# -*- coding: utf-8 -*-
import cv2
import numpy as np
from typing import List, Tuple


class DetectorCortesEscena:
    """
    Escáner ultrarrápido de cambios de plano reales (< 80 ms por minuto de video).
    Usa distancia Bhattacharyya en HSV + grilla espacial Luma con umbral adaptativo MAD.
    """

    def __init__(
        self,
        fps_escaneo: float = 12.0,
        distancia_min_entre_cortes_seg: float = 0.65,
        sensibilidad_mad: float = 4.2,
    ):
        self.fps_escaneo = fps_escaneo
        self.min_dist_seg = distancia_min_entre_cortes_seg
        self.sensibilidad_mad = sensibilidad_mad

    def detectar_cortes(self, ruta_video: str) -> List[float]:
        """
        Retorna una lista ordenada de timestamps en segundos (ej. [1.83, 4.16, 7.50])
        donde ocurren cortes de cámara reales.
        """
        cap = cv2.VideoCapture(str(ruta_video))
        if not cap.isOpened():
            return []

        fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0
        paso = max(1, int(round(fps_orig / self.fps_escaneo)))

        tiempos: List[float] = []
        scores_combinados: List[float] = []

        hist_prev = None
        luma_grid_prev = None
        idx_frame = 0

        while True:
            ret = cap.grab()
            if not ret:
                break

            if idx_frame % paso == 0:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    # Reducir a 160x90 para máxima velocidad en memoria rápida
                    peq = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
                    hsv = cv2.cvtColor(peq, cv2.COLOR_BGR2HSV)

                    # 1. Histograma 2D Hue-Saturation (16x16 bins)
                    hist_curr = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                    cv2.normalize(hist_curr, hist_curr)

                    # 2. Firma estructural de luminancia (grilla 8x8)
                    luma_grid_curr = cv2.resize(hsv[:, :, 2], (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

                    if hist_prev is not None and luma_grid_prev is not None:
                        dist_color = float(cv2.compareHist(hist_prev, hist_curr, cv2.HISTCMP_BHATTACHARYYA))
                        dist_estructura = float(np.mean(np.abs(luma_grid_curr - luma_grid_prev)))
                        score = (dist_color * 0.70) + (dist_estructura * 0.30)

                        tiempos.append(round(idx_frame / fps_orig, 3))
                        scores_combinados.append(score)

                    hist_prev = hist_curr
                    luma_grid_prev = luma_grid_curr

            idx_frame += 1

        cap.release()

        if len(scores_combinados) < 5:
            return []

        arr_scores = np.array(scores_combinados, dtype=np.float32)

        mediana_global = float(np.median(arr_scores))
        mad_global = float(np.median(np.abs(arr_scores - mediana_global))) + 1e-4
        umbral_dinamico = max(0.26, mediana_global + self.sensibilidad_mad * mad_global)

        cortes_detectados: List[float] = []
        ultimo_corte = -999.0

        for i in range(1, len(arr_scores) - 1):
            s_actual = arr_scores[i]
            t_actual = tiempos[i]

            if s_actual >= umbral_dinamico and s_actual > arr_scores[i - 1] and s_actual >= arr_scores[i + 1]:
                if (t_actual - ultimo_corte) >= self.min_dist_seg:
                    cortes_detectados.append(t_actual)
                    ultimo_corte = t_actual

        return cortes_detectados

    @staticmethod
    def ajustar_bloques_guion_a_cortes(
        bloques_tiempos: List[Tuple[float, float]],
        cortes_reales: List[float],
        ventana_imantacion_seg: float = 0.45,
        duracion_min_bloque: float = 1.1,
    ) -> List[Tuple[float, float]]:
        """
        Imanta (Snap) las fronteras de los bloques del guion al corte de cámara real más cercano
        dentro de `ventana_imantacion_seg` (+/- 0.45s), manteniendo la continuidad perfecta.
        """
        if not bloques_tiempos or not cortes_reales:
            return bloques_tiempos

        arr_cortes = np.array(cortes_reales, dtype=np.float64)
        fronteras = [bloques_tiempos[0][0]] + [b[1] for b in bloques_tiempos]

        for i in range(1, len(fronteras) - 1):
            t_orig = fronteras[i]
            distancias = np.abs(arr_cortes - t_orig)
            idx_min = int(np.argmin(distancias))

            if distancias[idx_min] <= ventana_imantacion_seg:
                t_candidato = float(arr_cortes[idx_min])
                if (t_candidato - fronteras[i - 1]) >= duracion_min_bloque and (
                    fronteras[i + 1] - t_candidato
                ) >= duracion_min_bloque:
                    fronteras[i] = round(t_candidato, 3)

        return [(fronteras[i], fronteras[i + 1]) for i in range(len(bloques_tiempos))]


# Alias directo a nivel de módulo
ajustar_bloques_guion_a_cortes = DetectorCortesEscena.ajustar_bloques_guion_a_cortes

