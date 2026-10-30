# -*- coding: utf-8 -*-
import re
import customtkinter as ctk
from typing import List, Dict, Callable, Optional, Any

# =====================================================================
# CATÁLOGO OFICIAL Y 9 CUADRANTES PRECISOS DEL MOTOR
# =====================================================================
LISTA_EFECTOS = [
    "ninguno", "zoom_impacto", "zoom_in", "zoom_out", "flash",
    "temblor", "alerta_roja", "brillo_epico", "blanco_negro", "spotlight"
]

LISTA_SFX = [
    "ninguno", "crowd_shocked", "whoosh", "riser_suction", "vine_boom",
    "metal_pipe", "heartbeat_fast", "record_scratch", "suspense_hit", "ding",
    "good_idea", "cash_ting", "punch", "boxing_bell", "camera_flash",
    "camera_shooter", "cartoon_laugh", "kids_yeyy", "party_horn",
    "awww", "error", "xp_Error", "fart", "click", "pop"
]

LISTA_EMOJIS = [
    "ninguno",
    "sorprendido:derecha", "sorprendido:izquierda", "sorprendido:centro",
    "risa:derecha", "risa:izquierda",
    "fiesta:derecha", "fiesta:izquierda",
    "diablo:derecha", "diablo:izquierda",
    "enojo:derecha", "enojo:izquierda",
    "lloro:derecha", "lloro:izquierda",
    "sueno:derecha", "sueno:izquierda",
    "calavera:derecha", "calavera:izquierda", "calavera:centro",
    "fuego:derecha", "fuego:izquierda",
    "ojos:derecha", "ojos:izquierda", "ojos:arriba_der", "ojos:arriba_izq",
    "cerebro:derecha", "cerebro:izquierda"
]

LISTA_FLECHAS = [
    "ninguna", "ninguno",
    "centro", "arriba", "abajo", "izquierda", "derecha",
    "arriba_izq", "arriba_der", "abajo_izq", "abajo_der",
    "auto"
]

LISTA_CIRCULOS = [
    "ninguno",
    "centro:medio", "centro:grande", "centro:chico",
    "arriba:medio", "arriba:grande", "arriba:chico",
    "abajo:medio", "abajo:grande", "abajo:chico",
    "izquierda:medio", "izquierda:grande", "izquierda:chico",
    "derecha:medio", "derecha:grande", "derecha:chico",
    "arriba_izq:medio", "arriba_der:medio",
    "abajo_izq:medio", "abajo_der:medio"
]


def seg_a_mmss(seg: float) -> str:
    seg = max(0.0, round(seg * 2) / 2)
    m = int(seg // 60)
    s = seg % 60
    if abs(s - round(s)) < 0.05:
        return f"{m:02d}:{int(round(s)):02d}"
    return f"{m:02d}:{s:04.1f}"


def mmss_a_seg(texto: str) -> float:
    try:
        p = str(texto).strip().split(":")
        if len(p) == 2:
            return int(p[0]) * 60 + float(p[1])
        elif len(p) == 1:
            return float(p[0])
        elif len(p) == 3:
            return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    except Exception:
        return 0.0
    return 0.0


def _extraer_frame_pil(ruta_video, t_seg: float, w: int = 270, h: int = 480):
    """Extrae un fotograma exacto del video a t_seg y lo devuelve redimensionado en PIL.Image."""
    if not ruta_video:
        return None
    try:
        from pathlib import Path
        import cv2
        from PIL import Image
        p = Path(ruta_video)
        if not p.exists():
            return None
        cap = cv2.VideoCapture(str(p))
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t_seg) * 1000.0))
        ret, frame_bgr = cap.read()
        cap.release()
        if not ret or frame_bgr is None:
            return None
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb).resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return None


def abrir_dialogo_posicion_pantalla(
    parent_win,
    datos_bloque: Dict,
    on_aplicar: Callable,
    ruta_video: Optional[Any] = None,
    on_preview_live: Optional[Callable] = None,
):
    import tkinter as tk
    import re
    import math
    from PIL import Image, ImageTk

    win_p = ctk.CTkToplevel(parent_win)
    win_p.title("🎯 Posicionar Círculo, Flechas y Altura de Texto")
    win_p.geometry("390x860")
    win_p.minsize(360, 780)
    win_p.resizable(False, True)
    win_p.configure(fg_color="#0e111a")
    win_p.transient(parent_win)
    win_p.grab_set()

    t_ini = float(datos_bloque.get("t_ini", 0.0))
    t_fin = float(datos_bloque.get("t_fin", 4.0))

    img_pil_ini = _extraer_frame_pil(ruta_video, t_ini)
    img_pil_fin = _extraer_frame_pil(ruta_video, max(t_ini, t_fin - 0.1))

    photo_ini = ImageTk.PhotoImage(img_pil_ini) if img_pil_ini else None
    photo_fin = ImageTk.PhotoImage(img_pil_fin) if img_pil_fin else None
    frame_activo = [photo_ini]

    tipo_var = ctk.StringVar(value="circulo")
    tam_var = ctk.StringVar(value="medio")
    track_var = ctk.BooleanVar(value=True)
    rot_var = ctk.DoubleVar(value=315.0)

    # Altura inicial de subtítulos (por defecto 70%)
    alt_raw = str(datos_bloque.get("altura", "70%")).strip().lower()
    alt_val = 70.0
    if "arriba" in alt_raw:
        alt_val = 30.0
    elif "medio" in alt_raw or "centro" in alt_raw:
        alt_val = 50.0
    elif "muy_abajo" in alt_raw or "fondo" in alt_raw:
        alt_val = 82.0
    elif "abajo" in alt_raw:
        alt_val = 70.0
    else:
        m_a = re.search(r"(\d+(?:\.\d+)?)", alt_raw)
        if m_a:
            v_n = float(m_a.group(1))
            alt_val = (v_n / 1920.0 * 100.0) if v_n > 100.0 else v_n
    alt_val = max(15.0, min(85.0, alt_val))
    altura_var = ctk.DoubleVar(value=alt_val)

    c_ini = str(datos_bloque.get("circulo", "")).strip()
    f_ini = str(datos_bloque.get("flecha", "")).strip()

    pos_x = 50.0
    pos_y = 45.0

    tiene_c = c_ini and c_ini.lower() not in ("ninguno", "ninguna", "none", "no")
    tiene_f = f_ini and f_ini.lower() not in ("ninguno", "ninguna", "none", "no")

    if tiene_c and tiene_f:
        tipo_var.set("ambos")
    elif tiene_f:
        tipo_var.set("flecha")
    elif tiene_c:
        tipo_var.set("circulo")
    else:
        tipo_var.set("circulo")

    m_c = re.search(r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)", c_ini or f_ini)
    if m_c:
        pos_x = float(m_c.group(1))
        pos_y = float(m_c.group(2))
    if ":chico" in c_ini:
        tam_var.set("chico")
    elif ":grande" in c_ini:
        tam_var.set("grande")
    if "fijo:" in c_ini or "static:" in c_ini or "fijo:" in f_ini or "static:" in f_ini:
        track_var.set(False)

    m_rot = re.search(r"@(\d+(?:\.\d+)?)", f_ini)
    if m_rot:
        try:
            rot_var.set(float(m_rot.group(1)) % 360.0)
        except Exception:
            pass

    hdr_frame = ctk.CTkFrame(win_p, fg_color="transparent")
    hdr_frame.pack(fill="x", padx=16, pady=(8, 2))

    lbl_coord = ctk.CTkLabel(
        hdr_frame, text=f"🎯 Objetivo: X: {pos_x:.1f}% | Y: {pos_y:.1f}%",
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        text_color="#38bdf8"
    )
    lbl_coord.pack(side="left")

    if on_preview_live is not None:
        try:
            on_preview_live("seek", t_ini, "", "", 0)
        except Exception:
            pass

    if photo_ini or photo_fin:
        def _seleccionar_frame(op: str):
            if "Inicio" in op or f"{t_ini:.1f}" in op:
                frame_activo[0] = photo_ini
                if on_preview_live is not None:
                    try:
                        on_preview_live("seek", t_ini, "", "", 0)
                    except Exception:
                        pass
            else:
                frame_activo[0] = photo_fin if photo_fin else photo_ini
                if on_preview_live is not None:
                    try:
                        on_preview_live("seek", t_fin, "", "", 0)
                    except Exception:
                        pass
            _redibujar()

        btn_toggle_frame = ctk.CTkSegmentedButton(
            hdr_frame,
            values=[f"◀ {t_ini:.1f}s", f"▶ {t_fin:.1f}s"],
            command=_seleccionar_frame,
            width=110, height=22, font=ctk.CTkFont(size=10, weight="bold"),
            selected_color="#1d4ed8", selected_hover_color="#1e40af",
        )
        btn_toggle_frame.set(f"◀ {t_ini:.1f}s")
        btn_toggle_frame.pack(side="right")

    # Canvas de 270x480 (Exactamente idéntico al reproductor de video 9:16)
    CW, CH = 270, 480
    canvas = tk.Canvas(win_p, width=CW, height=CH, bg="#050811", highlightthickness=1, highlightbackground="#252B3D")
    canvas.pack(pady=4)

    def _redibujar():
        canvas.delete("all")

        # 1. Fotograma real de fondo
        if frame_activo[0] is not None:
            canvas.create_image(0, 0, image=frame_activo[0], anchor="nw", tags="bg_video")
        else:
            canvas.create_rectangle(0, 0, CW, CH, fill="#050811", outline="")

        # 2. Guías sutiles de composición
        dash_col = "#2a3754" if frame_activo[0] is None else "#334155"
        canvas.create_line(CW * 0.33, 0, CW * 0.33, CH, fill=dash_col, dash=(2, 3))
        canvas.create_line(CW * 0.66, 0, CW * 0.66, CH, fill=dash_col, dash=(2, 3))
        canvas.create_line(0, CH * 0.33, CW, CH * 0.33, fill=dash_col, dash=(2, 3))
        canvas.create_line(0, CH * 0.66, CW, CH * 0.66, fill=dash_col, dash=(2, 3))

        # 3. Guía visual y caja de subtítulos a la altura elegida
        alt_pct = altura_var.get()
        lbl_alt_val.configure(text=f"📏 Altura Subtítulos (Y): {alt_pct:.0f}%")
        sub_y = (alt_pct / 100.0) * CH

        canvas.create_line(0, sub_y, CW, sub_y, fill="#10b981", dash=(4, 3), width=1.5)

        snippet = str(datos_bloque.get("texto", "")).strip()
        if len(snippet) > 26:
            snippet = snippet[:24] + "..."
        if not snippet:
            snippet = f"Subtítulos ({alt_pct:.0f}%)"

        bw, bh = 210, 24
        bx0 = (CW - bw) // 2
        by0 = sub_y - (bh // 2)
        canvas.create_rectangle(bx0 - 1, by0 - 1, bx0 + bw + 1, by0 + bh + 1, fill="#000000", outline="#10b981", width=1.5)
        canvas.create_rectangle(bx0, by0, bx0 + bw, by0 + bh, fill="#0a1926", outline="")
        canvas.create_text(CW // 2, sub_y, text=f"💬 {snippet}", fill="#38bdf8", font=("Segoe UI", 8, "bold"))

        # 4. Círculo y Flecha
        px = (pos_x / 100.0) * CW
        py = (pos_y / 100.0) * CH

        t = tipo_var.get()
        tam = tam_var.get()
        r_px = 22 if tam == "chico" else (32 if tam == "medio" else 44)

        if t in ("circulo", "ambos"):
            canvas.create_oval(px - r_px - 2, py - r_px - 2, px + r_px + 2, py + r_px + 2, outline="#000000", width=5)
            canvas.create_oval(px - r_px, py - r_px, px + r_px, py + r_px, outline="#ef4444", width=3)
            canvas.create_line(px - 8, py, px + 8, py, fill="#000000", width=3)
            canvas.create_line(px - 8, py, px + 8, py, fill="#38bdf8", width=1.5)
            canvas.create_line(px, py - 8, px, py + 8, fill="#000000", width=3)
            canvas.create_line(px, py - 8, px, py + 8, fill="#38bdf8", width=1.5)
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#38bdf8", outline="#000000", width=1)

        if t in ("flecha", "ambos"):
            rad = math.radians(rot_var.get())
            dist_flecha = 60
            fx0 = px + dist_flecha * math.cos(rad)
            fy0 = py + dist_flecha * math.sin(rad)
            gap_c = (r_px + 4) if t == "ambos" else 0
            tip_x = px + gap_c * math.cos(rad)
            tip_y = py + gap_c * math.sin(rad)

            canvas.create_line(fx0, fy0, tip_x, tip_y, fill="#000000", width=7, arrow=tk.LAST, arrowshape=(18, 20, 8))
            canvas.create_line(fx0, fy0, tip_x, tip_y, fill="#f59e0b", width=3.5, arrow=tk.LAST, arrowshape=(15, 17, 6))
            canvas.create_oval(tip_x - 5, tip_y - 5, tip_x + 5, tip_y + 5, outline="#000000", width=3)
            canvas.create_oval(tip_x - 5, tip_y - 5, tip_x + 5, tip_y + 5, outline="#38bdf8", width=1.5)
            canvas.create_oval(tip_x - 2, tip_y - 2, tip_x + 2, tip_y + 2, fill="#38bdf8", outline="")

        if t == "circulo":
            lbl_coord.configure(text=f"🎯 Centro Círculo: X: {pos_x:.1f}% | Y: {pos_y:.1f}%")
        elif t == "flecha":
            lbl_coord.configure(text=f"🎯 Punta Flecha: X: {pos_x:.1f}% | Y: {pos_y:.1f}%")
        elif t == "ambos":
            lbl_coord.configure(text=f"🎯 Objetivo: X: {pos_x:.1f}% | Y: {pos_y:.1f}%")
        else:
            lbl_coord.configure(text="Sin señalar")

        lbl_rot_val.configure(text=f"🔄 Ángulo Flecha: {rot_var.get():.0f}°")

        if on_preview_live is not None:
            try:
                on_preview_live(pos_x, pos_y, t, tam, rot_var.get(), alt_pct)
            except Exception:
                pass

    def _on_canvas_click(event):
        nonlocal pos_x, pos_y
        pos_x = max(5.0, min(95.0, (event.x / float(CW)) * 100.0))
        pos_y = max(6.0, min(94.0, (event.y / float(CH)) * 100.0))
        _redibujar()

    canvas.bind("<Button-1>", _on_canvas_click)
    canvas.bind("<B1-Motion>", _on_canvas_click)

    f_ctrls = ctk.CTkFrame(win_p, fg_color="transparent")
    f_ctrls.pack(fill="x", padx=16, pady=(4, 2))

    tipo_seg_ini = "⭕ Círculo" if tipo_var.get() == "circulo" else ("↗️ Flecha" if tipo_var.get() == "flecha" else ("⭕+↗️ Ambos" if tipo_var.get() == "ambos" else "❌ Ninguno"))
    ctk.CTkSegmentedButton(
        f_ctrls, values=["⭕ Círculo", "↗️ Flecha", "⭕+↗️ Ambos", "❌ Ninguno"],
        variable=ctk.StringVar(value=tipo_seg_ini),
        command=lambda v: (tipo_var.set("circulo" if "Círculo" in v else ("flecha" if "Flecha" in v else ("ambos" if "Ambos" in v else "ninguno"))), _redibujar()),
        height=26, corner_radius=8, font=ctk.CTkFont(size=11, weight="bold")
    ).pack(fill="x", pady=2)

    row_opt = ctk.CTkFrame(f_ctrls, fg_color="transparent")
    row_opt.pack(fill="x", pady=2)

    ctk.CTkOptionMenu(
        row_opt, values=["chico", "medio", "grande"], variable=tam_var,
        command=lambda _: _redibujar(), width=90, height=24, corner_radius=6, font=ctk.CTkFont(size=11)
    ).pack(side="left", padx=(0, 8))

    ctk.CTkCheckBox(
        row_opt, text="Seguir objeto (Tracking IA)", variable=track_var,
        font=ctk.CTkFont(size=11, weight="bold"), checkbox_width=18, checkbox_height=18, corner_radius=4
    ).pack(side="left")

    f_rot = ctk.CTkFrame(f_ctrls, fg_color="transparent")
    f_rot.pack(fill="x", pady=(2, 2))

    lbl_rot_val = ctk.CTkLabel(
        f_rot, text=f"🔄 Ángulo Flecha: {rot_var.get():.0f}°",
        font=ctk.CTkFont(size=11, weight="bold"), text_color="#fbbf24"
    )
    lbl_rot_val.pack(anchor="w")

    slider_rot = ctk.CTkSlider(
        f_rot, from_=0.0, to=360.0, number_of_steps=72, variable=rot_var,
        command=lambda _: _redibujar(), height=14, progress_color="#f59e0b", button_color="#f59e0b"
    )
    slider_rot.pack(fill="x", pady=1)

    row_presets_rot = ctk.CTkFrame(f_rot, fg_color="transparent")
    row_presets_rot.pack(fill="x")
    for nom_btn, deg_val in [("↖", 315.0), ("↑", 270.0), ("↗", 225.0), ("→", 180.0), ("↘", 135.0), ("↓", 90.0), ("↙", 45.0), ("←", 0.0)]:
        ctk.CTkButton(
            row_presets_rot, text=nom_btn, width=28, height=20, corner_radius=5,
            fg_color="#1e2436", hover_color="#2d354d", font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda d=deg_val: (rot_var.set(d), slider_rot.set(d), _redibujar())
        ).pack(side="left", padx=1)

    # Control de Altura de Subtítulos
    f_alt = ctk.CTkFrame(f_ctrls, fg_color="transparent")
    f_alt.pack(fill="x", pady=(4, 2))

    lbl_alt_val = ctk.CTkLabel(
        f_alt, text=f"📏 Altura Subtítulos (Y): {altura_var.get():.0f}%",
        font=ctk.CTkFont(size=11, weight="bold"), text_color="#10b981"
    )
    lbl_alt_val.pack(anchor="w")

    slider_alt = ctk.CTkSlider(
        f_alt, from_=15.0, to=85.0, number_of_steps=70, variable=altura_var,
        command=lambda _: _redibujar(), height=14, progress_color="#10b981", button_color="#10b981"
    )
    slider_alt.pack(fill="x", pady=1)

    row_presets_alt = ctk.CTkFrame(f_alt, fg_color="transparent")
    row_presets_alt.pack(fill="x")
    for nom_btn, alt_p in [("Arriba (30%)", 30.0), ("Medio (50%)", 50.0), ("Abajo (70%)", 70.0), ("Fondo (82%)", 82.0)]:
        ctk.CTkButton(
            row_presets_alt, text=nom_btn, height=22, corner_radius=5,
            fg_color="#1e2436", hover_color="#2d354d", font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda v=alt_p: (altura_var.set(v), slider_alt.set(v), _redibujar())
        ).pack(side="left", padx=2, expand=True, fill="x")

    _redibujar()

    def _al_cerrar():
        if on_preview_live is not None:
            try:
                on_preview_live(None, None, "", "", 0, None)
            except Exception:
                pass
        win_p.destroy()

    def _guardar_y_cerrar():
        t = tipo_var.get()
        tam = tam_var.get()
        tracking = track_var.get()
        pref = "" if tracking else "fijo:"
        rot_val = int(round(rot_var.get())) % 360
        res_circulo = f"{pref}{pos_x:.1f},{pos_y:.1f}:{tam}" if t in ("circulo", "ambos") else "ninguno"
        res_flecha = f"{pref}{pos_x:.1f},{pos_y:.1f}@{rot_val}" if t in ("flecha", "ambos") else "ninguna"
        res_altura = f"{int(round(altura_var.get()))}%"
        on_aplicar(res_circulo, res_flecha, res_altura)
        _al_cerrar()

    win_p.protocol("WM_DELETE_WINDOW", _al_cerrar)

    ctk.CTkButton(
        win_p, text="Aplicar Posición y Altura", command=_guardar_y_cerrar,
        corner_radius=10, height=32, fg_color="#10b981", hover_color="#059669",
        text_color="#052e16", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
    ).pack(fill="x", padx=16, pady=(4, 10))


class BloqueGuionCard(ctk.CTkFrame):
    """Tarjeta interactiva con edición de tiempos manual sincronizada y controles de reordenamiento."""

    def __init__(
        self,
        master,
        index: int,
        datos: Dict,
        on_change: Callable,
        on_time_edit: Callable,
        on_move: Callable,
        on_delete: Callable,
        mostrar_assets_inicial: bool = False,
        ruta_video: Optional[Any] = None,
        on_preview_live: Optional[Callable] = None,
    ):
        super().__init__(master, fg_color="#181B26", corner_radius=10, border_width=1, border_color="#2A3147")
        self.index = index
        self.datos = datos
        self.on_change = on_change
        self.on_time_edit = on_time_edit
        self.on_move = on_move
        self.on_delete = on_delete
        self.mostrar_assets = mostrar_assets_inicial
        self.ruta_video = ruta_video
        self.on_preview_live = on_preview_live
        self._assets_creados = False

        self.grid_columnconfigure(0, weight=1)
        self._build_ui()
        self._actualizar_semaforo_palabras()

    def _build_ui(self):
        # ---------------- FILA 1: TIEMPOS + SEMÁFORO + ACCIONES ----------------
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        badge = ctk.CTkLabel(
            top_frame, text=f"#{self.index + 1}",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#313952", corner_radius=6, width=28, height=24,
            text_color="#f8fafc"
        )
        badge.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(top_frame, text="⏱", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 2))

        self.entry_t_ini = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#101524", border_color="#2a3147"
        )
        self.entry_t_ini.insert(0, seg_a_mmss(self.datos["t_ini"]))
        self.entry_t_ini.pack(side="left", padx=2)
        self.entry_t_ini.bind("<FocusOut>", self._on_ini_edited)
        self.entry_t_ini.bind("<Return>", self._on_ini_edited)

        ctk.CTkLabel(top_frame, text="→", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64748b").pack(side="left", padx=2)

        self.entry_t_fin = ctk.CTkEntry(
            top_frame, width=54, height=24, justify="center",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#101524", border_color="#2a3147"
        )
        self.entry_t_fin.insert(0, seg_a_mmss(self.datos["t_fin"]))
        self.entry_t_fin.pack(side="left", padx=2)
        self.entry_t_fin.bind("<FocusOut>", self._on_fin_edited)
        self.entry_t_fin.bind("<Return>", self._on_fin_edited)

        self.lbl_duracion = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8"
        )
        self.lbl_duracion.pack(side="left", padx=(6, 4))



        # Botones de acción a la derecha
        btn_del = ctk.CTkButton(
            top_frame, text="🗑", width=26, height=24, fg_color="#45121b", hover_color="#881337",
            font=ctk.CTkFont(size=11),
            command=lambda: self.on_delete(self.index)
        )
        btn_del.pack(side="right", padx=(3, 0))

        btn_down = ctk.CTkButton(
            top_frame, text="▼", width=24, height=24, fg_color="#1e2436", hover_color="#2d354d",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, 1)
        )
        btn_down.pack(side="right", padx=2)

        btn_up = ctk.CTkButton(
            top_frame, text="▲", width=24, height=24, fg_color="#1e2436", hover_color="#2d354d",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.on_move(self.index, -1)
        )
        btn_up.pack(side="right", padx=2)

        self.btn_toggle_card_assets = ctk.CTkButton(
            top_frame,
            text="▲ Ocultar" if self.mostrar_assets else "🎛️ Assets",
            width=76,
            height=24,
            fg_color="#3B4261" if self.mostrar_assets else "#22283A",
            hover_color="#333D59",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_assets_local
        )
        self.btn_toggle_card_assets.pack(side="right", padx=4)

        # ---------------- FILA 2: CONTENEDOR DE ASSETS (LAZY LOAD) ----------------
        if self.mostrar_assets:
            self._asegurar_assets_frame()

        # ---------------- FILA 3: VOICEOVER / TEXTO DE NARRACIÓN ----------------
        vo_frame = ctk.CTkFrame(self, fg_color="transparent")
        vo_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
        vo_frame.grid_columnconfigure(0, weight=1)

        self.entry_texto = ctk.CTkEntry(
            vo_frame, height=32, font=ctk.CTkFont(size=13),
            placeholder_text="Escribe aquí el texto del guion con signos ¡!..."
        )
        self.entry_texto.insert(0, str(self.datos.get("texto", "")))
        self.entry_texto.grid(row=0, column=0, sticky="ew")
        self.entry_texto.bind("<KeyRelease>", self._on_texto_edit)

    def _on_fin_edited(self, _event=None):
        try:
            nuevo_fin = mmss_a_seg(self.entry_t_fin.get())
            if nuevo_fin <= self.datos["t_ini"]:
                nuevo_fin = self.datos["t_ini"] + 0.5
            self.datos["t_fin"] = nuevo_fin
            self.entry_t_fin.delete(0, "end")
            self.entry_t_fin.insert(0, seg_a_mmss(nuevo_fin))
            self._actualizar_semaforo_palabras()
            self.on_time_edit(self.index, "fin", nuevo_fin)
        except Exception:
            pass

    def _on_ini_edited(self, _event=None):
        try:
            nuevo_ini = mmss_a_seg(self.entry_t_ini.get())
            if nuevo_ini >= self.datos["t_fin"]:
                nuevo_ini = max(0.0, self.datos["t_fin"] - 0.5)
            self.datos["t_ini"] = nuevo_ini
            self.entry_t_ini.delete(0, "end")
            self.entry_t_ini.insert(0, seg_a_mmss(nuevo_ini))
            self._actualizar_semaforo_palabras()
            self.on_time_edit(self.index, "ini", nuevo_ini)
        except Exception:
            pass

    def _asegurar_assets_frame(self):
        """Instancia los selectores organizados en 2 filas compactas para visibilidad total sin desborde."""
        if self._assets_creados:
            return
        self._assets_creados = True

        self.assets_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.assets_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        # Fila 1: Efecto, SFX 1, SFX 2, Emoji
        row_assets_1 = ctk.CTkFrame(self.assets_frame, fg_color="transparent")
        row_assets_1.pack(fill="x", pady=(0, 4))

        self.opt_efecto = self._crear_selector(
            row_assets_1, "🎥 Efecto", LISTA_EFECTOS, self.datos.get("efecto", "ninguno"), width=118
        )

        sfx_partes = [s.strip() for s in str(self.datos.get("sfx", "")).split("+") if s.strip()]
        sfx1_val = sfx_partes[0] if len(sfx_partes) >= 1 else "ninguno"
        sfx2_val = sfx_partes[1] if len(sfx_partes) >= 2 else "ninguno"

        self.opt_sfx1 = self._crear_selector(
            row_assets_1, "🔊 SFX 1", LISTA_SFX, sfx1_val, width=118
        )
        self.opt_sfx2 = self._crear_selector(
            row_assets_1, "🔊 SFX 2", LISTA_SFX, sfx2_val, width=118
        )
        self.opt_emoji = self._crear_selector(
            row_assets_1, "🎭 Emoji", LISTA_EMOJIS, self.datos.get("emoji", "ninguno"), width=130
        )

        # Fila 2: Botón único para posicionar y badge de estado
        row_assets_2 = ctk.CTkFrame(self.assets_frame, fg_color="transparent")
        row_assets_2.pack(fill="x", pady=(2, 2))

        btn_pos = ctk.CTkButton(
            row_assets_2,
            text="🎯 Posicionar en Pantalla (Clic/Arrastrar)",
            command=self._abrir_selector_posicion,
            height=28,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        btn_pos.pack(side="left", padx=(4, 8))

        self.lbl_pos_status = ctk.CTkLabel(
            row_assets_2,
            text=self._generar_texto_badge_pos(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_pos_status.pack(side="left", padx=4)

        # Fila 3: Editor de altura del texto / subtítulos para esta sección
        row_alt = ctk.CTkFrame(self.assets_frame, fg_color="transparent")
        row_alt.pack(fill="x", pady=(3, 2))

        alt_val_ini = 70.0
        m_a = re.search(r"(\d+(?:\.\d+)?)", str(self.datos.get("altura", "70%")))
        if m_a:
            v_a = float(m_a.group(1))
            alt_val_ini = (v_a / 1920.0 * 100.0) if v_a > 100.0 else v_a
        alt_val_ini = max(15.0, min(85.0, alt_val_ini))
        self.altura_card_var = ctk.DoubleVar(value=alt_val_ini)

        self.lbl_alt_card = ctk.CTkLabel(
            row_alt,
            text=f"📏 Altura Texto: {alt_val_ini:.0f}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981",
        )
        self.lbl_alt_card.pack(side="left", padx=(4, 6))

        def _on_slider_alt_change(val: float):
            alt_int = int(round(val))
            self.datos["altura"] = f"{alt_int}%"
            self.lbl_alt_card.configure(text=f"📏 Altura Texto: {alt_int}%")
            self.on_change()
            if self.on_preview_live is not None:
                try:
                    self.on_preview_live(None, None, "altura_only", None, None, alt_int)
                except Exception:
                    pass

        slider_alt_card = ctk.CTkSlider(
            row_alt,
            from_=15.0, to=85.0, number_of_steps=70,
            variable=self.altura_card_var,
            command=_on_slider_alt_change,
            width=120, height=14,
            progress_color="#10b981", button_color="#10b981"
        )
        slider_alt_card.pack(side="left", padx=(0, 6))

        for nom_p, v_p in [("Arriba (30%)", 30.0), ("Medio (50%)", 50.0), ("Abajo (70%)", 70.0)]:
            def _preset_click(v=v_p):
                self.altura_card_var.set(v)
                _on_slider_alt_change(v)
            ctk.CTkButton(
                row_alt, text=nom_p, width=74, height=22, corner_radius=5,
                fg_color="#1e2436", hover_color="#2d354d", font=ctk.CTkFont(size=10, weight="bold"),
                command=_preset_click
            ).pack(side="left", padx=2)

    def _generar_texto_badge_pos(self) -> str:
        c = str(self.datos.get("circulo", "")).strip()
        f = str(self.datos.get("flecha", "")).strip()
        tiene_c = c and c.lower() not in ("ninguno", "ninguna", "none", "no")
        tiene_f = f and f.lower() not in ("ninguno", "ninguna", "none", "no")
        if tiene_c and tiene_f:
            return f"⭕ Círculo + ↗️ Flecha activos"
        elif tiene_c:
            return f"⭕ Círculo: {c}"
        elif tiene_f:
            return f"↗️ Flecha: {f}"
        return "Sin señalar"

    def _abrir_selector_posicion(self):
        def _on_aplicar(c_val, f_val, a_val):
            self.datos["circulo"] = c_val
            self.datos["flecha"] = f_val
            self.datos["altura"] = a_val
            if hasattr(self, "altura_card_var"):
                m_a = re.search(r"(\d+(?:\.\d+)?)", str(a_val))
                if m_a:
                    self.altura_card_var.set(float(m_a.group(1)))
            if hasattr(self, "lbl_alt_card") and self.lbl_alt_card.winfo_exists():
                self.lbl_alt_card.configure(text=f"📏 Altura Texto: {a_val}")
            if hasattr(self, "lbl_pos_status") and self.lbl_pos_status.winfo_exists():
                self.lbl_pos_status.configure(text=self._generar_texto_badge_pos())
            self.on_change()

        abrir_dialogo_posicion_pantalla(
            self.winfo_toplevel(),
            self.datos,
            _on_aplicar,
            ruta_video=self.ruta_video,
            on_preview_live=self.on_preview_live,
        )

    def _destruir_assets_frame(self):
        """Libera la memoria de Tkinter destruyendo los OptionMenus de la tarjeta."""
        if not self._assets_creados:
            return
        try:
            self._guardar_valores_assets_a_datos()
            self.assets_frame.destroy()
        except Exception:
            pass
        self._assets_creados = False

    def _guardar_valores_assets_a_datos(self):
        if not self._assets_creados:
            return
        try:
            self.datos["efecto"] = self.opt_efecto.get()
            s1 = self.opt_sfx1.get()
            s2 = self.opt_sfx2.get()
            if s1 != "ninguno" and s2 != "ninguno" and s1 != s2:
                self.datos["sfx"] = f"{s1}+{s2}"
            elif s1 != "ninguno":
                self.datos["sfx"] = s1
            elif s2 != "ninguno":
                self.datos["sfx"] = s2
            else:
                self.datos["sfx"] = "ninguno"

            self.datos["emoji"] = self.opt_emoji.get()
            self.datos["flecha"] = self.opt_flecha.get()
            self.datos["circulo"] = self.opt_circulo.get()
        except Exception:
            pass

    def _toggle_assets_local(self):
        self.mostrar_assets = not self.mostrar_assets
        if self.mostrar_assets:
            self._asegurar_assets_frame()
            self.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#3B4261")
        else:
            self._destruir_assets_frame()
            self.btn_toggle_card_assets.configure(text="🎛️ Assets", fg_color="#22283A")
        self.on_change()

    def _crear_selector(self, parent, label: str, lista: List[str], val_actual: str, width: int = 120):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", padx=4, pady=2)
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8").pack(anchor="w")

        val_clean = str(val_actual).strip()
        lista_final = list(lista)
        if val_clean and val_clean not in lista_final:
            lista_final.append(val_clean)

        opt = ctk.CTkOptionMenu(
            f, values=lista_final, width=width, height=24,
            corner_radius=6, font=ctk.CTkFont(size=10),
            command=lambda _: self._sincronizar_estado()
        )
        opt.set(val_clean if val_clean else lista_final[0])
        opt.pack()
        return opt

    def _on_texto_edit(self, _event=None):
        self.datos["texto"] = self.entry_texto.get()
        self._actualizar_semaforo_palabras()
        self.on_change()

    def _actualizar_semaforo_palabras(self):
        dur = max(0.5, self.datos["t_fin"] - self.datos["t_ini"])
        self.lbl_duracion.configure(text=f"({dur:.1f}s)")

    def _sincronizar_estado(self):
        self._guardar_valores_assets_a_datos()
        self.datos["texto"] = self.entry_texto.get().strip()
        self.on_change()


class VisualScriptEditor(ctk.CTkFrame):
    """
    Editor Visual Interactivo de Guiones:
    - Ripple Time bidireccional automático entre bloques.
    - Reordenamiento rápido de bloques con ▲ y ▼.
    - Edición del Título viral real de YouTube con sincronización limpia.
    - Modo Doble: Solo Voz ultra-rápido o Profundo con Assets.
    """

    def __init__(
        self,
        master,
        ruta_video: Optional[Any] = None,
        on_preview_live: Optional[Callable] = None,
        **kwargs
    ):
        self.ruta_video = ruta_video
        self.on_preview_live = on_preview_live
        frame_kwargs = {
            k: v for k, v in kwargs.items()
            if k in ("width", "height", "corner_radius", "border_width", "bg_color", "fg_color", "border_color")
        }
        if "fg_color" not in frame_kwargs:
            frame_kwargs["fg_color"] = "transparent"
        super().__init__(master, **frame_kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.metadatos_ocultos: Dict[str, str] = {
            "MODO_ENCUADRE": "full",
            "VOLUMEN_VIDEO_ORIGINAL": "0",
            "ARCHIVO_SALIDA": "auto"
        }
        self.bloques: List[Dict] = []
        self.cards: List[BloqueGuionCard] = []
        self._modo_raw = False
        self.modo_profundo = False

        self._build_header()
        self._build_body()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="#141824", corner_radius=10, border_width=1, border_color="#252B3D")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)

        self.entry_titulo = ctk.CTkEntry(
            header, height=30, font=ctk.CTkFont(size=12, weight="bold"),
            placeholder_text="Título para YouTube (#shorts)..."
        )
        self.entry_titulo.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="ew")
        self.entry_titulo.bind("<KeyRelease>", lambda _: self._actualizar_raw_interno())

        btn_add = ctk.CTkButton(
            header, text="＋ Nuevo Bloque", width=120, height=28,
            fg_color="#0284c7", hover_color="#0369a1",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._agregar_bloque_arriba
        )
        btn_add.grid(row=0, column=1, padx=4, pady=8)

        self.btn_toggle_raw = ctk.CTkButton(
            header, text="📝 Texto Crudo", width=105, height=28,
            fg_color="#22283A", hover_color="#333D59",
            font=ctk.CTkFont(size=11),
            command=self._toggle_vista
        )
        self.btn_toggle_raw.grid(row=0, column=2, padx=8, pady=8)

    def _build_body(self):
        self.scroll_cards = ctk.CTkScrollableFrame(self, fg_color="#0e111a", corner_radius=8)
        self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        self.scroll_cards.grid_columnconfigure(0, weight=1)

        self.raw_textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.raw_textbox.bind("<KeyRelease>", self._on_raw_edited_manually)

    def _toggle_modo_profundo(self):
        self.modo_profundo = not self.modo_profundo
        if self.modo_profundo:
            self.btn_toggle_modo.configure(text="🎛️ Ver Assets (Todos)", fg_color="#6d28d9")
        else:
            self.btn_toggle_modo.configure(text="🎙️ Solo Voz (Todos)", fg_color="#1e3a5f")

        for c in self.cards:
            c.mostrar_assets = self.modo_profundo
            if self.modo_profundo:
                c._asegurar_assets_frame()
                c.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#3B4261")
            else:
                c._destruir_assets_frame()
                c.btn_toggle_card_assets.configure(text="🎛️ Assets", fg_color="#22283A")

    def _toggle_vista(self):
        self._modo_raw = not self._modo_raw
        if self._modo_raw:
            self._actualizar_raw_interno()
            self.scroll_cards.grid_remove()
            self.raw_textbox.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
            self.btn_toggle_raw.configure(text="🎛️ Vista Tarjetas")
        else:
            texto_actual = self.raw_textbox.get("1.0", "end").strip()
            self.cargar_desde_texto(texto_actual)
            self.raw_textbox.grid_remove()
            self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
            self.btn_toggle_raw.configure(text="📝 Texto Crudo")

    def _on_raw_edited_manually(self, _event=None):
        pass

    def cargar_desde_texto(self, raw_script: str):
        self.raw_textbox.delete("1.0", "end")
        self.raw_textbox.insert("1.0", raw_script)

        self.bloques.clear()
        titulo_yt = ""
        titulo_sup = ""
        en_guion = False

        for linea in raw_script.splitlines():
            l_strip = linea.strip()
            if not l_strip:
                continue
            if l_strip.startswith("[GUION]"):
                en_guion = True
                continue
            if not en_guion:
                if ":" in l_strip:
                    k, v = l_strip.split(":", 1)
                    k_clean = k.strip().upper()
                    v_clean = v.strip()
                    if k_clean == "TITULO_YOUTUBE":
                        titulo_yt = v_clean
                    elif k_clean == "TITULO_SUPERIOR":
                        titulo_sup = v_clean
                    else:
                        self.metadatos_ocultos[k_clean] = v_clean
                continue

            if l_strip.upper().startswith("TIEMPO") or "|" not in l_strip:
                continue

            partes = [p.strip() for p in l_strip.split("|")]
            # Soporta 8 columnas (con ALTURA) o 7 columnas (compatibilidad)
            def _es_alt(s: str) -> bool:
                s_c = s.strip().lower()
                return s_c in ("arriba", "medio", "centro", "abajo", "muy_abajo", "fondo") or bool(re.match(r"^(y:)?\d{1,4}%?$", s_c))

            if len(partes) >= 8 and _es_alt(partes[6]):
                rango_t = partes[0].split("-")
                t_ini = mmss_a_seg(rango_t[0]) if len(rango_t) > 0 else 0.0
                t_fin = mmss_a_seg(rango_t[1]) if len(rango_t) > 1 else t_ini + 4.0
                if t_fin <= t_ini:
                    t_fin = t_ini + 4.0
                self.bloques.append({
                    "t_ini": t_ini,
                    "t_fin": t_fin,
                    "efecto": partes[1],
                    "sfx": partes[2],
                    "emoji": partes[3],
                    "flecha": partes[4],
                    "circulo": partes[5],
                    "altura": partes[6],
                    "texto": " | ".join(partes[7:]).strip()
                })
            elif len(partes) >= 7:
                rango_t = partes[0].split("-")
                t_ini = mmss_a_seg(rango_t[0]) if len(rango_t) > 0 else 0.0
                t_fin = mmss_a_seg(rango_t[1]) if len(rango_t) > 1 else t_ini + 4.0
                if t_fin <= t_ini:
                    t_fin = t_ini + 4.0
                self.bloques.append({
                    "t_ini": t_ini,
                    "t_fin": t_fin,
                    "efecto": partes[1],
                    "sfx": partes[2],
                    "emoji": partes[3],
                    "flecha": partes[4],
                    "circulo": partes[5],
                    "altura": "70%",
                    "texto": " | ".join(partes[6:]).strip()
                })

        # Mostrar el título real viral de YouTube
        titulo_mostrar = titulo_yt or titulo_sup or "Short Viral"
        self.entry_titulo.delete(0, "end")
        self.entry_titulo.insert(0, titulo_mostrar)

        if not self.bloques:
            self.bloques.append({
                "t_ini": 0.0, "t_fin": 4.0,
                "efecto": "zoom_impacto", "sfx": "crowd_shocked",
                "emoji": "sorprendido:derecha", "flecha": "centro",
                "circulo": "ninguno", "texto": ""
            })

        self._renderizar_tarjetas()
        self._actualizar_raw_interno()

    def exportar_a_texto(self) -> str:
        if self._modo_raw:
            return self.raw_textbox.get("1.0", "end").strip()

        for c in self.cards:
            try:
                c.datos["t_ini"] = mmss_a_seg(c.entry_t_ini.get())
                c.datos["t_fin"] = max(c.datos["t_ini"] + 0.5, mmss_a_seg(c.entry_t_fin.get()))
                c.datos["texto"] = c.entry_texto.get().strip()
                if c._assets_creados:
                    c._guardar_valores_assets_a_datos()
            except Exception:
                pass

        titulo_editado = self.entry_titulo.get().strip() or "Short Viral"
        tit_sup_limpio = re.sub(r'[^A-Za-z0-9_ -]', '', titulo_editado).strip()[:40] or "Short_Viral"

        lineas = [
            f"TITULO_SUPERIOR: {tit_sup_limpio}",
            f"TITULO_YOUTUBE: {titulo_editado}"
        ]
        for k, v in self.metadatos_ocultos.items():
            if k not in ("TITULO_SUPERIOR", "TITULO_YOUTUBE"):
                lineas.append(f"{k}: {v}")

        lineas.append("")
        lineas.append("[GUION]")
        lineas.append("TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | ALTURA | TEXTO")

        for b in self.bloques:
            t_str = f"{seg_a_mmss(b['t_ini'])} - {seg_a_mmss(b['t_fin'])}"
            alt_val = b.get("altura", "70%") or "70%"
            fila = (
                f"{t_str} | {b['efecto']} | {b['sfx']} | "
                f"{b['emoji']} | {b['flecha']} | {b['circulo']} | {alt_val} | {b['texto']}"
            )
            lineas.append(fila)

        return "\n".join(lineas)

    def _actualizar_raw_interno(self):
        if getattr(self, "_actualizando_raw", False):
            return
        self._actualizando_raw = True
        try:
            if not self._modo_raw:
                texto = self.exportar_a_texto()
                self.raw_textbox.delete("1.0", "end")
                self.raw_textbox.insert("1.0", texto)
        finally:
            self._actualizando_raw = False

    def _renderizar_tarjetas(self):
        for c in self.cards:
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()

        for idx, b in enumerate(self.bloques):
            card = BloqueGuionCard(
                self.scroll_cards,
                index=idx,
                datos=b,
                on_change=self._actualizar_raw_interno,
                on_time_edit=self._on_block_time_edited,
                on_move=self._mover_bloque,
                on_delete=self._eliminar_bloque,
                mostrar_assets_inicial=self.modo_profundo,
                ruta_video=self.ruta_video,
                on_preview_live=self.on_preview_live,
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
            self.cards.append(card)

    def _on_block_time_edited(self, idx: int, campo: str, nuevo_seg: float):
        """Efecto dominó (Ripple Time): sincroniza el fin de un bloque con el inicio del siguiente."""
        if 0 <= idx < len(self.bloques):
            if campo == "fin":
                self.bloques[idx]["t_fin"] = nuevo_seg
                if idx + 1 < len(self.bloques):
                    sig = self.bloques[idx + 1]
                    dur_sig = max(0.5, sig["t_fin"] - sig["t_ini"])
                    sig["t_ini"] = nuevo_seg
                    if sig["t_fin"] <= sig["t_ini"]:
                        sig["t_fin"] = sig["t_ini"] + dur_sig
                    if idx + 1 < len(self.cards):
                        c_sig = self.cards[idx + 1]
                        c_sig.entry_t_ini.delete(0, "end")
                        c_sig.entry_t_ini.insert(0, seg_a_mmss(sig["t_ini"]))
                        c_sig.entry_t_fin.delete(0, "end")
                        c_sig.entry_t_fin.insert(0, seg_a_mmss(sig["t_fin"]))
                        c_sig._actualizar_semaforo_palabras()
            elif campo == "ini":
                self.bloques[idx]["t_ini"] = nuevo_seg
                if idx > 0:
                    ant = self.bloques[idx - 1]
                    ant["t_fin"] = nuevo_seg
                    if idx - 1 < len(self.cards):
                        c_ant = self.cards[idx - 1]
                        c_ant.entry_t_fin.delete(0, "end")
                        c_ant.entry_t_fin.insert(0, seg_a_mmss(nuevo_seg))
                        c_ant._actualizar_semaforo_palabras()

            self._actualizar_raw_interno()

    def _mover_bloque(self, idx: int, direccion: int):
        target = idx + direccion
        if 0 <= idx < len(self.bloques) and 0 <= target < len(self.bloques):
            self.bloques[idx], self.bloques[target] = self.bloques[target], self.bloques[idx]
            # Reencadenar tiempos desde 00:00 conservando la duración de cada bloque
            t_curr = 0.0
            for b in self.bloques:
                d = max(0.5, b["t_fin"] - b["t_ini"])
                b["t_ini"] = t_curr
                b["t_fin"] = t_curr + d
                t_curr += d

            self._renderizar_tarjetas()
            self._actualizar_raw_interno()

    def _agregar_bloque_arriba(self):
        t_base = self.bloques[-1]["t_fin"] if self.bloques else 0.0
        dur_nueva = 4.0
        nuevo = {
            "t_ini": t_base,
            "t_fin": t_base + dur_nueva,
            "efecto": "zoom_in",
            "sfx": "whoosh",
            "emoji": "sorprendido:derecha",
            "flecha": "centro",
            "circulo": "ninguno",
            "texto": "¡Escribe aquí la nueva narración sincronizada!"
        }
        self.bloques.append(nuevo)
        self._renderizar_tarjetas()
        self._actualizar_raw_interno()

    def _eliminar_bloque(self, idx: int):
        if len(self.bloques) <= 1:
            return
        if 0 <= idx < len(self.bloques):
            eliminado = self.bloques.pop(idx)
            dur = eliminado["t_fin"] - eliminado["t_ini"]
            for j in range(idx, len(self.bloques)):
                self.bloques[j]["t_ini"] = max(0.0, self.bloques[j]["t_ini"] - dur)
                self.bloques[j]["t_fin"] = max(self.bloques[j]["t_ini"] + 1.0, self.bloques[j]["t_fin"] - dur)

            self._renderizar_tarjetas()
            self._actualizar_raw_interno()

    def get(self, index1="1.0", index2="end") -> str:
        return self.exportar_a_texto()

    def insert(self, index, text: str):
        self.cargar_desde_texto(text)

    def delete(self, index1="1.0", index2=None):
        self.raw_textbox.delete("1.0", "end")
        self.bloques.clear()
        for c in self.cards:
            try:
                c.destroy()
            except Exception:
                pass
        self.cards.clear()
        try:
            self.entry_titulo.delete(0, "end")
        except Exception:
            pass
