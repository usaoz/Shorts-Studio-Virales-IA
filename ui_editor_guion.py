import customtkinter as ctk
from typing import List, Dict, Callable

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

# 9 Cuadrantes nativos soportados por shorts_engine/vision_tracker.py
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


class BloqueGuionCard(ctk.CTkFrame):
    """Tarjeta interactiva ultra-optimizada con Lazy Loading y liberación real de widgets."""

    def __init__(
        self,
        master,
        index: int,
        datos: Dict,
        on_change: Callable,
        on_time_shift: Callable,
        on_add_below: Callable,
        on_delete: Callable,
        mostrar_assets_inicial: bool = False
    ):
        super().__init__(master, fg_color="#181B26", corner_radius=10, border_width=1, border_color="#2A3147")
        self.index = index
        self.datos = datos
        self.on_change = on_change
        self.on_time_shift = on_time_shift
        self.on_add_below = on_add_below
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
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#313952", corner_radius=6, width=32, height=24,
            text_color="#f8fafc"
        )
        badge.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(top_frame, text="⏱️", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 2))

        self.entry_t_ini = ctk.CTkEntry(top_frame, width=58, height=26, justify="center")
        self.entry_t_ini.insert(0, seg_a_mmss(self.datos["t_ini"]))
        self.entry_t_ini.pack(side="left", padx=2)
        self.entry_t_ini.bind("<FocusOut>", self._manual_time_edit)

        ctk.CTkLabel(top_frame, text="→", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=2)

        self.entry_t_fin = ctk.CTkEntry(top_frame, width=58, height=26, justify="center")
        self.entry_t_fin.insert(0, seg_a_mmss(self.datos["t_fin"]))
        self.entry_t_fin.pack(side="left", padx=2)
        self.entry_t_fin.bind("<FocusOut>", self._manual_time_edit)

        btn_menos = ctk.CTkButton(
            top_frame, text="-0.5s", width=42, height=24, fg_color="#22283A", hover_color="#333D59",
            command=lambda: self.on_time_shift(self.index, -0.5)
        )
        btn_menos.pack(side="left", padx=(6, 2))

        btn_mas = ctk.CTkButton(
            top_frame, text="+0.5s", width=42, height=24, fg_color="#22283A", hover_color="#333D59",
            command=lambda: self.on_time_shift(self.index, +0.5)
        )
        btn_mas.pack(side="left", padx=2)

        self.lbl_duracion = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8"
        )
        self.lbl_duracion.pack(side="left", padx=(8, 6))

        self.lbl_semaforo = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1E3A2F", corner_radius=6, padx=8, pady=2
        )
        self.lbl_semaforo.pack(side="left", padx=6)

        btn_del = ctk.CTkButton(
            top_frame, text="🗑", width=28, height=24, fg_color="#6C252E", hover_color="#9E2A3B",
            command=lambda: self.on_delete(self.index)
        )
        btn_del.pack(side="right", padx=(4, 0))

        btn_add = ctk.CTkButton(
            top_frame, text="＋ Bloque", width=68, height=24, fg_color="#1e3a5f", hover_color="#2a5285",
            command=lambda: self.on_add_below(self.index)
        )
        btn_add.pack(side="right", padx=4)

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
        self.btn_toggle_card_assets.pack(side="right", padx=4)

        # ---------------- FILA 2: CONTENEDOR DE ASSETS (LAZY LOAD) ----------------
        if self.mostrar_assets:
            self._asegurar_assets_frame()

        # ---------------- FILA 3: VOICEOVER / TEXTO DE NARRACIÓN ----------------
        vo_frame = ctk.CTkFrame(self, fg_color="transparent")
        vo_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
        vo_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            vo_frame, text="🎙️ Voz:", font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=0, padx=(0, 6), sticky="w")

        self.entry_texto = ctk.CTkEntry(
            vo_frame, height=32, font=ctk.CTkFont(size=13),
            placeholder_text="Escribe aquí el texto del voiceover con signos ¡!..."
        )
        self.entry_texto.insert(0, str(self.datos.get("texto", "")))
        self.entry_texto.grid(row=0, column=1, sticky="ew")
        self.entry_texto.bind("<KeyRelease>", self._on_texto_edit)

    def _asegurar_assets_frame(self):
        """Instancia los 6 selectores solo cuando el usuario abre los assets."""
        if self._assets_creados:
            return
        self._assets_creados = True

        self.assets_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.assets_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        self.opt_efecto = self._crear_selector(
            self.assets_frame, "🎥 Efecto", LISTA_EFECTOS, self.datos.get("efecto", "ninguno"), width=118
        )

        sfx_partes = [s.strip() for s in str(self.datos.get("sfx", "")).split("+") if s.strip()]
        sfx1_val = sfx_partes[0] if len(sfx_partes) >= 1 else "ninguno"
        sfx2_val = sfx_partes[1] if len(sfx_partes) >= 2 else "ninguno"

        self.opt_sfx1 = self._crear_selector(
            self.assets_frame, "🔊 SFX 1", LISTA_SFX, sfx1_val, width=118
        )
        self.opt_sfx2 = self._crear_selector(
            self.assets_frame, "➕ SFX 2", LISTA_SFX, sfx2_val, width=112
        )

        self.opt_emoji = self._crear_selector(
            self.assets_frame, "😎 Emoji", LISTA_EMOJIS, self.datos.get("emoji", "ninguno"), width=135
        )

        self.opt_flecha = self._crear_selector(
            self.assets_frame, "🏹 Flecha", LISTA_FLECHAS, self.datos.get("flecha", "ninguna"), width=95
        )

        self.opt_circulo = self._crear_selector(
            self.assets_frame, "⭕ Círculo", LISTA_CIRCULOS, self.datos.get("circulo", "ninguno"), width=120
        )

    def _destruir_assets_frame(self):
        """Guarda los valores seleccionados y destruye los OptionMenu para liberar el event loop."""
        if self._assets_creados and hasattr(self, "assets_frame"):
            self._sincronizar_estado()
            try:
                self.assets_frame.destroy()
            except Exception:
                pass
        self._assets_creados = False

    def _toggle_assets_local(self):
        self.mostrar_assets = not self.mostrar_assets
        if self.mostrar_assets:
            self._asegurar_assets_frame()
            self.btn_toggle_card_assets.configure(text="▲ Ocultar", fg_color="#3B4261")
        else:
            self._destruir_assets_frame()
            self.btn_toggle_card_assets.configure(text="🎛️ Assets", fg_color="#22283A")

    def _crear_selector(self, parent, label_txt: str, opciones: List[str], valor_actual: str, width: int):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(box, text=label_txt, font=ctk.CTkFont(size=11), text_color="#BAC2DE").pack(anchor="w")
        lista_final = list(opciones)
        val_clean = str(valor_actual or "").strip()
        if val_clean and val_clean not in lista_final:
            lista_final.insert(0, val_clean)
        opt = ctk.CTkOptionMenu(
            box, values=lista_final, width=width, height=26,
            fg_color="#22283A", button_color="#333D59",
            font=ctk.CTkFont(size=11),
            command=lambda _: self._sincronizar_estado()
        )
        opt.set(val_clean if val_clean else lista_final[0])
        opt.pack()
        return opt

    def _manual_time_edit(self, _event=None):
        try:
            t_ini = mmss_a_seg(self.entry_t_ini.get())
            t_fin = max(t_ini + 0.5, mmss_a_seg(self.entry_t_fin.get()))
            self.datos["t_ini"] = t_ini
            self.datos["t_fin"] = t_fin
            self.entry_t_ini.delete(0, "end")
            self.entry_t_ini.insert(0, seg_a_mmss(t_ini))
            self.entry_t_fin.delete(0, "end")
            self.entry_t_fin.insert(0, seg_a_mmss(t_fin))
            self._actualizar_semaforo_palabras()
            self._sincronizar_estado()
        except Exception:
            pass

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
        if self._assets_creados:
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

        self.datos["texto"] = self.entry_texto.get().strip()
        self.on_change()


class VisualScriptEditor(ctk.CTkFrame):
    """
    Editor Visual Interactivo con Modo Doble:
    1) Modo Rápido (Solo Voz): Ultra liviano, carga en <30ms sin lag ni placeholders negros.
    2) Modo Profundo (Efectos y Assets): Despliega 9 zonas de Flechas/Círculos, SFX dobles y Efectos.
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
        header = ctk.CTkFrame(self, fg_color="#141824", corner_radius=8, border_width=1, border_color="#252B3D")
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="🎬 TÍTULO:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8"
        ).grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")

        self.entry_titulo = ctk.CTkEntry(
            header, height=30, font=ctk.CTkFont(size=13, weight="bold"),
            placeholder_text="Nombre del video / archivo MP4..."
        )
        self.entry_titulo.grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        self.entry_titulo.bind("<KeyRelease>", lambda _: self._actualizar_raw_interno())

        self.btn_toggle_modo = ctk.CTkButton(
            header, text="🎙️ Modo: Solo Voz", width=145, height=28,
            fg_color="#1e3a5f", hover_color="#2a5285",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_modo_profundo
        )
        self.btn_toggle_modo.grid(row=0, column=2, padx=4, pady=8)

        self.btn_toggle_raw = ctk.CTkButton(
            header, text="📝 Texto Crudo", width=115, height=28,
            fg_color="#22283A", hover_color="#333D59",
            font=ctk.CTkFont(size=11),
            command=self._toggle_vista
        )
        self.btn_toggle_raw.grid(row=0, column=3, padx=8, pady=8)

    def _build_body(self):
        self.scroll_cards = ctk.CTkScrollableFrame(self, fg_color="#0e111a", corner_radius=8)
        self.scroll_cards.grid(row=1, column=0, sticky="nsew", padx=4, pady=2)
        self.scroll_cards.grid_columnconfigure(0, weight=1)

        self.raw_textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.raw_textbox.bind("<KeyRelease>", self._on_raw_edited_manually)

    def _toggle_modo_profundo(self):
        self.modo_profundo = not self.modo_profundo
        if self.modo_profundo:
            self.btn_toggle_modo.configure(text="🎛️ Modo: Profundo", fg_color="#6d28d9")
        else:
            self.btn_toggle_modo.configure(text="🎙️ Modo: Solo Voz", fg_color="#1e3a5f")

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
        titulo_detectado = "Short Viral"
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
                    k_clean = k.strip()
                    v_clean = v.strip()
                    if k_clean.upper() == "TITULO_SUPERIOR":
                        titulo_detectado = v_clean
                    else:
                        self.metadatos_ocultos[k_clean.upper()] = v_clean
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

        self.entry_titulo.delete(0, "end")
        self.entry_titulo.insert(0, titulo_detectado)

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
                    c.datos["efecto"] = c.opt_efecto.get()
                    s1 = c.opt_sfx1.get()
                    s2 = c.opt_sfx2.get()
                    if s1 != "ninguno" and s2 != "ninguno" and s1 != s2:
                        c.datos["sfx"] = f"{s1}+{s2}"
                    elif s1 != "ninguno":
                        c.datos["sfx"] = s1
                    elif s2 != "ninguno":
                        c.datos["sfx"] = s2
                    else:
                        c.datos["sfx"] = "ninguno"
                    c.datos["emoji"] = c.opt_emoji.get()
                    c.datos["flecha"] = c.opt_flecha.get()
                    c.datos["circulo"] = c.opt_circulo.get()
            except Exception:
                pass

        titulo = self.entry_titulo.get().strip() or "Short Viral"
        lineas = [f"TITULO_SUPERIOR: {titulo}"]
        for k, v in self.metadatos_ocultos.items():
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
                on_time_shift=self._ajustar_tiempo_cascada,
                on_add_below=self._insertar_bloque_debajo,
                on_delete=self._eliminar_bloque,
                mostrar_assets_inicial=self.modo_profundo
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=5)
            self.cards.append(card)

    def _ajustar_tiempo_cascada(self, idx: int, delta_seg: float):
        if 0 <= idx < len(self.bloques):
            bloque = self.bloques[idx]
            nueva_dur = max(1.0, (bloque["t_fin"] - bloque["t_ini"]) + delta_seg)
            nuevo_fin = bloque["t_ini"] + nueva_dur
            desplazamiento = nuevo_fin - bloque["t_fin"]
            bloque["t_fin"] = nuevo_fin

            for j in range(idx + 1, len(self.bloques)):
                self.bloques[j]["t_ini"] = max(0.0, self.bloques[j]["t_ini"] + desplazamiento)
                self.bloques[j]["t_fin"] = max(
                    self.bloques[j]["t_ini"] + 1.0,
                    self.bloques[j]["t_fin"] + desplazamiento
                )

            self._renderizar_tarjetas()
            self._actualizar_raw_interno()

    def _insertar_bloque_debajo(self, idx: int):
        if 0 <= idx < len(self.bloques):
            t_base = self.bloques[idx]["t_fin"]
            dur_nueva = 4.0
            nuevo = {
                "t_ini": t_base,
                "t_fin": t_base + dur_nueva,
                "efecto": "zoom_in",
                "sfx": "whoosh",
                "emoji": "sorprendido:derecha",
                "flecha": "centro",
                "circulo": "ninguno",
                "texto": "¡Escribe aquí la nueva línea de narración sincronizada!"
            }
            for j in range(idx + 1, len(self.bloques)):
                self.bloques[j]["t_ini"] += dur_nueva
                self.bloques[j]["t_fin"] += dur_nueva

            self.bloques.insert(idx + 1, nuevo)
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
