"""
shorts_engine/thumbnail_picker.py

Selector heurístico de alto CTR para capturar y exportar automáticamente
el mejor fotograma del Short como portada / miniatura viral en JPEG de alta calidad.
100% NumPy + OpenCV estándar (Sin SciPy, sin PyTorch).
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np


class SelectorPortadaViral:
    """
    Evaluador heurístico de alto CTR para seleccionar y exportar automáticamente
    el mejor fotograma del Short como `portada_[nombre].jpg`.
    """

    def __init__(self, num_candidatos: int = 14):
        self.num_candidatos = num_candidatos
        self.face_cascade = None
        self.eye_cascade = None
        if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            base_haar = cv2.data.haarcascades
            ruta_face = base_haar + "haarcascade_frontalface_default.xml"
            ruta_eye = base_haar + "haarcascade_eye.xml"
            try:
                if Path(ruta_face).exists():
                    clf = cv2.CascadeClassifier(ruta_face)
                    if not clf.empty():
                        self.face_cascade = clf
                if Path(ruta_eye).exists():
                    clf_e = cv2.CascadeClassifier(ruta_eye)
                    if not clf_e.empty():
                        self.eye_cascade = clf_e
            except Exception:
                self.face_cascade = None
                self.eye_cascade = None

    def evaluar_fotograma(self, frame_bgr: np.ndarray) -> Dict[str, float]:
        """Calcula el puntaje compuesto de calidad visual y atractivo de miniatura."""
        h, w = frame_bgr.shape[:2]
        # Escalar a altura 640px para evaluación consistente y rápida (~2.5 ms por foto)
        escala = 640.0 / float(h)
        w_eval = max(180, int(round(w * escala)))
        img = cv2.resize(frame_bgr, (w_eval, 640), interpolation=cv2.INTER_AREA)

        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 1. DESCARTAR FRAMES MUERTOS (Negros, blancos quemados o casi uniformes)
        luma_media = float(np.mean(gris))
        std_luma = float(np.std(gris))
        if luma_media < 22.0 or luma_media > 238.0 or std_luma < 14.0:
            return {"score_total": 0.0, "nitidez": 0.0, "exposicion": 0.0, "rostro": 0.0}

        # 2. NITIDEZ PONDERADA AL CENTRO (Descarta Motion Blur)
        lap_completo = cv2.Laplacian(gris, cv2.CV_64F)
        roi_central = lap_completo[120:520, int(w_eval * 0.15) : int(w_eval * 0.85)]
        var_centro = float(np.var(roi_central))
        var_global = float(np.var(lap_completo))
        # Normalización logarítmica para que un ruido extremo no infle el score infinitamente
        score_nitidez = min(100.0, float(np.log1p(var_centro * 0.75 + var_global * 0.25) * 14.5))

        # 3. RANGO DINÁMICO Y EXPOSICIÓN (Óptimo alrededor de Luma = 128 y alto rango P95-P5)
        rango_p95_p5 = float(np.percentile(gris, 95) - np.percentile(gris, 5))
        calidad_brillo = float(np.exp(-0.5 * ((luma_media - 125.0) / 55.0) ** 2))
        score_exposicion = min(100.0, (rango_p95_p5 / 200.0) * 60.0 + calidad_brillo * 40.0)

        # 4. VIBRANCIA DE COLOR (Canal S de HSV)
        sat_media = float(np.mean(hsv[:, :, 1]))
        score_color = min(100.0, (sat_media / 145.0) * 100.0)

        # 5. DETECCIÓN DE ROSTRO + VERIFICACIÓN DE OJOS ABIERTOS (Anti-Parpadeo)
        score_rostro = 0.0
        if self.face_cascade is not None:
            try:
                rostros = self.face_cascade.detectMultiScale(
                    gris, scaleFactor=1.15, minNeighbors=5, minSize=(int(w_eval * 0.16), int(w_eval * 0.16))
                )

                if len(rostros) > 0:
                    areas = [rw * rh for (_, _, rw, rh) in rostros]
                    idx_max = int(np.argmax(areas))
                    rx, ry, rw, rh = rostros[idx_max]

                    roi_cara_gris = gris[ry : ry + rh, rx : rx + rw]
                    nitidez_cara = float(np.var(cv2.Laplacian(roi_cara_gris, cv2.CV_64F)))

                    if nitidez_cara > 35.0:
                        score_rostro += 45.0
                        if self.eye_cascade is not None:
                            mitad_sup_cara = roi_cara_gris[0 : int(rh * 0.62), :]
                            ojos = self.eye_cascade.detectMultiScale(
                                mitad_sup_cara, scaleFactor=1.1, minNeighbors=4, minSize=(int(rw * 0.14), int(rh * 0.10))
                            )
                            if len(ojos) >= 2:
                                score_rostro += 45.0
                            elif len(ojos) == 1:
                                score_rostro += 15.0
                            else:
                                score_rostro -= 20.0

                        yc_cara_norm = (ry + rh * 0.5) / 640.0
                        if 0.20 <= yc_cara_norm <= 0.65:
                            score_rostro += 10.0
            except Exception:
                score_rostro = 0.0

        if self.face_cascade is not None:
            score_total = (
                score_nitidez * 0.35
                + score_exposicion * 0.20
                + score_color * 0.15
                + max(0.0, score_rostro) * 0.30
            )
        else:
            # Si no hay detector facial en el entorno, redistribuir pesos
            score_total = (
                score_nitidez * 0.50
                + score_exposicion * 0.30
                + score_color * 0.20
            )

        return {
            "score_total": round(score_total, 2),
            "nitidez": round(score_nitidez, 1),
            "exposicion": round(score_exposicion, 1),
            "rostro": round(score_rostro, 1),
        }

    def extraer_mejor_portada(
        self,
        ruta_video_renderizado: str,
        ruta_salida_jpg: str,
        calidad_jpg: int = 96,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Escanea `num_candidatos` fotogramas del video final (o fuente), elige el de mayor
        puntaje viral y lo guarda en disco con compresión JPEG de alta calidad.
        """
        cap = cv2.VideoCapture(str(ruta_video_renderizado))
        if not cap.isOpened():
            return False, {"error": "No se pudo abrir el video"}

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0

        if total_frames < 1:
            cap.release()
            return False, {"error": "Video sin fotogramas"}

        # Muestrear entre el 6% y el 92% del video para evitar fades de entrada/salida
        idx_inicio = int(total_frames * 0.06)
        idx_fin = max(idx_inicio + 1, int(total_frames * 0.92))
        indices_candidatos = np.linspace(idx_inicio, idx_fin, self.num_candidatos, dtype=int)

        mejor_frame: Optional[np.ndarray] = None
        mejor_info: Dict[str, Any] = {"score_total": -1.0}

        for idx in np.unique(indices_candidatos):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            metricas = self.evaluar_fotograma(frame)
            if metricas["score_total"] > mejor_info["score_total"]:
                mejor_frame = frame.copy()
                mejor_info = {
                    **metricas,
                    "frame_idx": int(idx),
                    "timestamp_seg": round(int(idx) / fps, 2),
                }

        cap.release()

        if mejor_frame is None:
            return False, {"error": "Ningún fotograma superó el filtro de calidad"}

        # Pequeño realce final de micro-contraste (Unsharp Mask sutil) para destacar en el feed de Shorts
        blur_suave = cv2.GaussianBlur(mejor_frame, (0, 0), sigmaX=1.2)
        portada_final = cv2.addWeighted(mejor_frame, 1.12, blur_suave, -0.12, 0)

        salida = Path(ruta_salida_jpg)
        salida.parent.mkdir(parents=True, exist_ok=True)
        exito = cv2.imwrite(
            str(salida),
            portada_final,
            [int(cv2.IMWRITE_JPEG_QUALITY), calidad_jpg],
        )
        return bool(exito), mejor_info
