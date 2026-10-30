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


def abrir_dialogo_posicion_pantalla(parent_win, datos_bloque: Dict, on_aplicar: Callable):
    import tkinter as tk
    import re
    win_p = ctk.CTkToplevel(parent_win)
    win_p.title("🎯 Posicionar Círculo y Flechas en Pantalla")
    win_p.geometry("440x600")
    win_p.resizable(False, False)
    win_p.configure(fg_color="#0e111a")
    win_p.transient(parent_win)
    win_p.grab_set()

    tipo_var = ctk.StringVar(value="circulo")
    tam_var = ctk.StringVar(value="medio")
    track_var = ctk.BooleanVar(value=True)

    c_ini = str(datos_bloque.get("circulo", "")).strip()
    f_ini = str(datos_bloque.get("flecha", "")).strip()

    pos_x = 50.0
    pos_y = 45.0

    if f_ini and f_ini not in ("ninguna", "ninguno") and (not c_ini or c_ini in ("ninguno", "ninguna")):
        tipo_var.set("flecha")
    elif f_ini and f_ini not in ("ninguna", "ninguno") and c_ini and c_ini not in ("ninguno", "ninguna"):
        tipo_var.set("ambos")
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

    lbl_coord = ctk.CTkLabel(
        win_p, text=f"🎯 Posición: X: {pos_x:.1f}% | Y: {pos_y:.1f}%",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        text_color="#38bdf8"
    )
    lbl_coord.pack(pady=(12, 6))

    CW, CH = 216, 384
    canvas = tk.Canvas(win_p, width=CW, height=CH, bg="#050811", highlightthickness=1, highlightbackground="#252B3D")
    canvas.pack(pady=4)

    def _redibujar():
        canvas.delete("all")
        canvas.create_line(CW * 0.33, 0, CW * 0.33, CH, fill="#151b28", dash=(2, 2))
        canvas.create_line(CW * 0.66, 0, CW * 0.66, CH, fill="#151b28", dash=(2, 2))
        canvas.create_line(0, CH * 0.33, CW, CH * 0.33, fill="#151b28", dash=(2, 2))
        canvas.create_line(0, CH * 0.66, CW, CH * 0.66, fill="#151b28", dash=(2, 2))
        canvas.create_line(CW * 0.50, 0, CW * 0.50, CH, fill="#1e2638", dash=(4, 4))
        canvas.create_line(0, CH * 0.50, CW, CH * 0.50, fill="#1e2638", dash=(4, 4))

        px = (pos_x / 100.0) * CW
        py = (pos_y / 100.0) * CH

        t = tipo_var.get()
        tam = tam_var.get()
        r_px = 18 if tam == "chico" else (26 if tam == "medio" else 36)

        if t in ("circulo", "ambos"):
            canvas.create_oval(px - r_px, py - r_px, px + r_px, py + r_px, outline="#ef4444", width=3)
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#ef4444", outline="")

        if t in ("flecha", "ambos"):
            fx0 = px + 42
            fy0 = py - 42
            canvas.create_line(fx0, fy0, px + (r_px if t == "ambos" else 4), py - (r_px if t == "ambos" else 4), fill="#f59e0b", width=3, arrow=tk.LAST, arrowshape=(10, 12, 4))

        lbl_coord.configure(text=f"🎯 Posición: X: {pos_x:.1f}% | Y: {pos_y:.1f}%")

    def _on_canvas_click(event):
        nonlocal pos_x, pos_y
        pos_x = max(5.0, min(95.0, (event.x / float(CW)) * 100.0))
        pos_y = max(8.0, min(92.0, (event.y / float(CH)) * 100.0))
        _redibujar()

    canvas.bind("<Button-1>", _on_canvas_click)
    canvas.bind("<B1-Motion>", _on_canvas_click)
    _redibujar()

    f_ctrls = ctk.CTkFrame(win_p, fg_color="transparent")
    f_ctrls.pack(fill="x", padx=18, pady=(8, 4))

    tipo_seg_ini = "⭕ Círculo" if tipo_var.get() == "circulo" else ("↗️ Flecha" if tipo_var.get() == "flecha" else "⭕+↗️ Ambos")
    ctk.CTkSegmentedButton(
        f_ctrls, values=["⭕ Círculo", "↗️ Flecha", "⭕+↗️ Ambos"],
        variable=ctk.StringVar(value=tipo_seg_ini),
        command=lambda v: (tipo_var.set("circulo" if "Círculo" in v else ("flecha" if "Flecha" in v else "ambos")), _redibujar()),
        height=26, corner_radius=8, font=ctk.CTkFont(size=11, weight="bold")
    ).pack(fill="x", pady=2)

    row_opt = ctk.CTkFrame(f_ctrls, fg_color="transparent")
    row_opt.pack(fill="x", pady=4)

    ctk.CTkOptionMenu(
        row_opt, values=["chico", "medio", "grande"], variable=tam_var,
        command=lambda _: _redibujar(), width=95, height=26, corner_radius=6, font=ctk.CTkFont(size=11)
    ).pack(side="left", padx=(0, 8))

    ctk.CTkCheckBox(
        row_opt, text="Seguir objeto (Tracking IA)", variable=track_var,
        font=ctk.CTkFont(size=11, weight="bold"), checkbox_width=18, checkbox_height=18, corner_radius=4
    ).pack(side="left")

    def _guardar_y_cerrar():
        t = tipo_var.get()
        tam = tam_var.get()
        tracking = track_var.get()
        pref = "" if tracking else "fijo:"
        res_circulo = f"{pref}{pos_x:.1f},{pos_y:.1f}:{tam}" if t in ("circulo", "ambos") else "ninguno"
        res_flecha = f"{pref}{pos_x:.1f},{pos_y:.1f}" if t in ("flecha", "ambos") else "ninguna"
        on_aplicar(res_circulo, res_flecha)
        win_p.destroy()

    ctk.CTkButton(
        win_p, text="Aplicar Posición", command=_guardar_y_cerrar,
        corner_radius=10, height=32, fg_color="#10b981", hover_color="#059669",
        text_color="#052e16", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
    ).pack(fill="x", padx=18, pady=(4, 12))


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
        mostrar_assets_inicial: bool = False
    ):
        super().__init__(master, fg_color="#181B26", corner_radius=10, border_width=1, border_color="#2A3147")
        self.index = index
        self.datos = datos
        self.on_change = on_change
        self.on_time_edit = on_time_edit
        self.on_move = on_move
        self.on_delete = on_delete
        self.mostrar_assets = mostrar_assets_inicial
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

        self.lbl_semaforo = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1E3A2F", corner_radius=6, padx=8, pady=2
        )
        self.lbl_semaforo.pack(side="left", padx=4)

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

        btn_pos_rapido = ctk.CTkButton(
            top_frame,
            text="🎯 Posicionar",
            width=88,
            height=24,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._abrir_selector_posicion,
        )
        btn_pos_rapido.pack(side="right", padx=(2, 4))

        self.btn_toggle_card_assets = ctk.CTkButton(
            top_frame,
            text="▲ Ocultar" if self.mostrar_assets else "🎛️ Assets",
            width=68,
            height=24,
            fg_color="#3B4261" if self.mostrar_assets else "#22283A",
            hover_color="#333D59",
            font=ctk.CTkFont(size=11),
            command=self._toggle_assets_local
        )
        self.btn_toggle_card_assets.pack(side="right", padx=2)

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

        # Fila 2: Flecha, Círculo y Botón Posicionar en Pantalla (Interact.)
        row_assets_2 = ctk.CTkFrame(self.assets_frame, fg_color="transparent")
        row_assets_2.pack(fill="x", pady=(0, 2))

        self.opt_flecha = self._crear_selector(
            row_assets_2, "↗️ Flecha (9 Pos)", LISTA_FLECHAS, self.datos.get("flecha", "ninguna"), width=120
        )
        self.opt_circulo = self._crear_selector(
            row_assets_2, "⭕ Círculo (9 Pos)", LISTA_CIRCULOS, self.datos.get("circulo", "ninguno"), width=130
        )

        f_btn_pos = ctk.CTkFrame(row_assets_2, fg_color="transparent")
        f_btn_pos.pack(side="left", padx=(12, 2), pady=(14, 0))
        btn_pos = ctk.CTkButton(
            f_btn_pos,
            text="🎯 Posicionar en Pantalla (Clic/Arrastrar)",
            command=self._abrir_selector_posicion,
            height=26,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        btn_pos.pack()

    def _abrir_selector_posicion(self):
        def _on_aplicar(c_val, f_val):
            self.datos["circulo"] = c_val
            if hasattr(self, "opt_circulo"):
                val_c = list(self.opt_circulo.cget("values"))
                if c_val not in val_c:
                    self.opt_circulo.configure(values=val_c + [c_val])
                self.opt_circulo.set(c_val)

            self.datos["flecha"] = f_val
            if hasattr(self, "opt_flecha"):
                val_f = list(self.opt_flecha.cget("values"))
                if f_val not in val_f:
                    self.opt_flecha.configure(values=val_f + [f_val])
                self.opt_flecha.set(f_val)

            self.on_change()

        abrir_dialogo_posicion_pantalla(self.winfo_toplevel(), self.datos, _on_aplicar)

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

        palabras = [p for p in self.entry_texto.get().strip().split() if p]
        n_pal = len(palabras)
        min_p = max(1, int(round(dur * 3.4)))
        max_p = int(round(dur * 4.0))

        if n_pal < min_p:
            txt = f"⚠️ {n_pal}/{min_p}-{max_p} pal (Corto)"
            bg = "#5C4818"
        elif n_pal > max_p:
            txt = f"🚨 {n_pal}/{min_p}-{max_p} pal (Largo)"
            bg = "#63222A"
        else:
            txt = f"✅ {n_pal}/{min_p}-{max_p} pal (Ritmo OK)"
            bg = "#1D4D38"

        self.lbl_semaforo.configure(text=txt, fg_color=bg)

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

    def __init__(self, master, **kwargs):
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

            partes = [p.strip() for p in l_strip.split("|", 6)]
            if len(partes) >= 7:
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
                    "texto": partes[6]
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
        lineas.append("TIEMPO | EFECTO | SFX | EMOJI | FLECHA | CIRCULO | TEXTO")

        for b in self.bloques:
            t_str = f"{seg_a_mmss(b['t_ini'])} - {seg_a_mmss(b['t_fin'])}"
            fila = (
                f"{t_str} | {b['efecto']} | {b['sfx']} | "
                f"{b['emoji']} | {b['flecha']} | {b['circulo']} | {b['texto']}"
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
                mostrar_assets_inicial=self.modo_profundo
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
