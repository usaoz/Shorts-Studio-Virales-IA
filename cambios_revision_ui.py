ARCHIVO = "Editor_Shorts_Studio.py"

CAMBIOS = [
    (
        """        panel_principal = ctk.CTkFrame(win_r, fg_color="transparent")
        panel_principal.pack(fill="both", expand=True, padx=18, pady=16)
        panel_principal.grid_columnconfigure(0, weight=0)
        panel_principal.grid_columnconfigure(1, weight=1)
        panel_principal.grid_rowconfigure(0, weight=1)

        # Columna Izquierda: Reproductor Vertical 9:16
        col_izq = ctk.CTkFrame(
            panel_principal,
            fg_color=CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=CARD_BORDER,
            width=300,
        )
        col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        canvas_video = tk.Canvas(
            col_izq,
            width=270,
            height=480,
            bg="#000000",
            highlightthickness=0,
        )
        canvas_video.pack(padx=14, pady=(12, 6))

        slider_seek = ctk.CTkSlider(
            col_izq,
            from_=0.0,
            to=1.0,
            height=14,
            progress_color=PURPLE_MAIN,
            button_color=CYAN_ACCENT,
            button_hover_color="#38bdf8",
        )
        slider_seek.set(0.0)
        slider_seek.pack(fill="x", padx=14, pady=(0, 4))

        def _fmt_tiempo(s: float) -> str:
            s_int = max(0, int(s))
            m = s_int // 60
            sec = s_int % 60
            return f"{m:02d}:{sec:02d}"

        def _seek_press(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = True

        def _seek_release(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = False
            if player is not None and duracion_total > 0:
                try:
                    player.seek(slider_seek.get() * duracion_total, relative=False)
                    win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        def _on_slider_change(val: float) -> None:
            if arrastrando_slider and duracion_total > 0 and player is not None:
                try:
                    target_pts = float(val) * duracion_total
                    player.seek(target_pts, relative=False)
                    lbl_tiempo.configure(text=f"{_fmt_tiempo(target_pts)} / {_fmt_tiempo(duracion_total)}")
                except Exception:
                    pass

        slider_seek.bind("<Button-1>", _seek_press)
        slider_seek.bind("<ButtonRelease-1>", _seek_release)
        slider_seek.configure(command=_on_slider_change)

        row_ctrl = ctk.CTkFrame(col_izq, fg_color="transparent")
        row_ctrl.pack(fill="x", padx=14, pady=(0, 10))

        btn_play = ctk.CTkButton(
            row_ctrl,
            text="▶",
            width=36,
            height=30,
            corner_radius=8,
            fg_color=INPUT_BG,
            hover_color="#2a3147",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_tiempo = ctk.CTkLabel(
            row_ctrl,
            text="00:00 / 00:00",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        btn_play.pack(side="left", padx=(0, 6))
        lbl_tiempo.pack(side="left")

        slider_vol = ctk.CTkSlider(
            row_ctrl,
            from_=0.0,
            to=1.0,
            width=60,
            height=12,
            number_of_steps=20,
            progress_color=CYAN_ACCENT,
            button_color=CYAN_ACCENT,
        )
        slider_vol.set(1.0)
        lbl_vol = ctk.CTkLabel(row_ctrl, text="🔊", font=ctk.CTkFont(size=12))
        slider_vol.pack(side="right")
        lbl_vol.pack(side="right", padx=(0, 3))

        def _on_vol_change(val: float) -> None:
            if player is not None:
                try:
                    player.set_volume(float(val))
                    v = float(val)
                    lbl_vol.configure(text="🔇" if v == 0 else ("🔉" if v < 0.5 else "🔊"))
                except Exception:
                    pass

        slider_vol.configure(command=_on_vol_change)

        def _toggle_play() -> None:
            nonlocal reproduciendo
            if player is not None:
                try:
                    reproduciendo = not reproduciendo
                    player.set_pause(not reproduciendo)
                    btn_play.configure(text="■" if reproduciendo else "▶")
                    if reproduciendo:
                        win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        btn_play.configure(command=_toggle_play)

        # Columna Derecha: Controles, Decisiones e Información
        col_der = ctk.CTkFrame(panel_principal, fg_color="transparent")
        col_der.grid(row=0, column=1, sticky="nsew")

        top_der = ctk.CTkFrame(col_der, fg_color="transparent")
        top_der.pack(fill="x", pady=(0, 6))

        badge = ctk.CTkFrame(
            top_der,
            fg_color="#1e1b4b",
            corner_radius=10,
            border_width=1,
            border_color=PURPLE_MAIN,
        )
        badge.pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            badge,
            text="MODO REVISIÓN · VIDEO EDITADO" if es_modo_editado else "MODO REVISIÓN PREVIA",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#c084fc",
        ).pack(padx=10, pady=2)

        ctk.CTkLabel(
            top_der,
            text="Video editado listo para publicar" if es_modo_editado else "Tu Short está listo para publicar",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w")

        tit_corto = titulo[:58] + ("..." if len(titulo) > 58 else "")
        ctk.CTkLabel(
            top_der,
            text=f"Título: {tit_corto}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        if url_video_orig and url_video_orig.strip():
            row_link_orig = ctk.CTkFrame(col_der, fg_color="#141a29", corner_radius=10, border_width=1, border_color="#222b42")
            row_link_orig.pack(fill="x", pady=(0, 8))

            ctk.CTkLabel(
                row_link_orig,
                text="🔗 Video Original:",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=CYAN_ACCENT,
            ).pack(side="left", padx=(10, 6), pady=4)

            ent_url_disp = ctk.CTkEntry(
                row_link_orig,
                height=26,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color="#0e1320",
                border_width=0,
                text_color="#93c5fd",
            )
            ent_url_disp.insert(0, url_video_orig.strip())
            ent_url_disp.configure(state="readonly")
            ent_url_disp.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=4)

            def _abrir_url_navegador() -> None:
                import webbrowser
                try:
                    webbrowser.open(url_video_orig.strip())
                except Exception:
                    pass

            def _copiar_url_clip() -> None:
                try:
                    root.clipboard_clear()
                    root.clipboard_append(url_video_orig.strip())
                    btn_copiar_url.configure(text="¡Copiado!")
                    root.after(1400, lambda: btn_copiar_url.configure(text="Copiar"))
                except Exception:
                    pass

            btn_abrir_url = ctk.CTkButton(
                row_link_orig,
                text="Abrir",
                width=46,
                height=22,
                corner_radius=6,
                fg_color="#1e293b",
                hover_color="#334155",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_abrir_url_navegador,
            )
            btn_abrir_url.pack(side="right", padx=(0, 8), pady=4)

            btn_copiar_url = ctk.CTkButton(
                row_link_orig,
                text="Copiar",
                width=50,
                height=22,
                corner_radius=6,
                fg_color="#1e293b",
                hover_color="#334155",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_copiar_url_clip,
            )
            btn_copiar_url.pack(side="right", padx=(0, 4), pady=4)

        # Tarjeta Central: Editor de Guion y Metadatos en Vivo
        card_guion = ctk.CTkFrame(
            col_der,
            fg_color=CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=CARD_BORDER,
        )
        card_guion.pack(fill="both", expand=True, pady=(0, 8))

        row_tit_g = ctk.CTkFrame(card_guion, fg_color="transparent")
        row_tit_g.pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            row_tit_g,
            text="Título y Metadatos:" if es_modo_editado else "Guion y Metadatos (Editable en vivo):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        lbl_ritmo = ctk.CTkLabel(
            row_tit_g,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=GREEN_ACCENT,
        )
        lbl_ritmo.pack(side="right")

        ctk.CTkLabel(
            card_guion,
            text="Modificá el texto, efectos, SFX o timings. Luego re-renderizá o subí directamente:" if not es_modo_editado else "Verificá o editá el título y la descripción antes de publicar en YouTube:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 4))

        txt_guion_box = VisualScriptEditor(
            card_guion,
        )
        txt_guion_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        if ruta_guion.exists():
            try:
                txt_guion_raw = ruta_guion.read_text(encoding="utf-8", errors="replace")
                txt_guion_box.insert("1.0", txt_guion_raw)
                # Validar ritmo a 3.7 palabras/segundo
                en_g = False
                res_r = []
                for ln_g in txt_guion_raw.splitlines():
                    if "[GUION]" in ln_g:
                        en_g = True
                        continue
                    if en_g and "|" in ln_g:
                        partes_g = [x.strip() for x in ln_g.split("|")]
                        if len(partes_g) >= 7 and "-" in partes_g[0] and ":" in partes_g[0]:
                            res_r.append(evaluar_ritmo_bloque(partes_g[0], partes_g[6]))
                if res_r:
                    ok_c = sum(1 for r in res_r if r["estado"] == "OK")
                    col_ritmo = GREEN_ACCENT if ok_c == len(res_r) else "#facc15"
                    lbl_ritmo.configure(
                        text=f"Ritmo: {ok_c}/{len(res_r)} calibrados (3.7 pal/s)",
                        text_color=col_ritmo,
                    )
            except Exception:
                pass

        if not es_modo_editado:
            btn_reeditar = ctk.CTkButton(
                card_guion,
                text="⚡ Re-renderizar Video con Guion Editado",
                command=lambda: _responder("reeditar"),
                height=34,
                corner_radius=10,
                fg_color=PURPLE_MAIN,
                hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#ffffff",
            )
            btn_reeditar.pack(fill="x", padx=12, pady=(0, 8))
        else:
            tam_mb = ""
            try:
                tam_mb = f" · {ruta_video.stat().st_size / (1024 * 1024):.1f} MB"
            except Exception:
                pass
            ctk.CTkLabel(
                card_guion,
                text=f"Archivo: {ruta_video.name}{tam_mb} (video local listo)",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=12, pady=(0, 6))

        # Tarjeta Inferior: Decisiones de Publicación (Subir, Buscar Otro / Siguiente, Descartar)
        card_acciones = ctk.CTkFrame(
            col_der,
            fg_color=CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=CARD_BORDER,
        )
        card_acciones.pack(fill="x")

        btn_subir = ctk.CTkButton(
            card_acciones,
            text="Subir a YouTube",
            command=lambda: _responder("subir"),
            height=38,
            corner_radius=10,
            fg_color=GREEN_ACCENT,
            hover_color="#059669",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#ffffff",
        )
        btn_subir.pack(fill="x", padx=12, pady=(8, 6))

        row_sec = ctk.CTkFrame(card_acciones, fg_color="transparent")
        row_sec.pack(fill="x", padx=12, pady=(0, 8))
        row_sec.grid_columnconfigure((0, 1), weight=1, uniform="sec_btn")

        btn_otro = ctk.CTkButton(
            row_sec,
            text="Siguiente Video" if es_modo_editado else "Buscar Otro Video",
            command=lambda: _responder("buscar_otro"),
            height=32,
            corner_radius=10,
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff",
        )
        btn_otro.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        btn_cancelar = ctk.CTkButton(
            row_sec,
            text="Cancelar Proceso",
            command=lambda: _responder("descartar"),
            height=32,
            corner_radius=10,
            fg_color="#334155",
            hover_color="#dc2626",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff",
        )
        btn_cancelar.grid(row=0, column=1, padx=(4, 0), sticky="ew")""",

        # ── REEMPLAZO: UI limpia estilo pantalla principal ──────────────────
        """        # ── Layout principal ──────────────────────────────────────────────────
        panel_principal = ctk.CTkFrame(win_r, fg_color="transparent")
        panel_principal.pack(fill="both", expand=True, padx=20, pady=16)
        panel_principal.grid_columnconfigure(0, weight=0)
        panel_principal.grid_columnconfigure(1, weight=1)
        panel_principal.grid_rowconfigure(0, weight=1)

        # ── Columna izquierda: reproductor 9:16 ───────────────────────────
        col_izq = ctk.CTkFrame(
            panel_principal,
            fg_color=CARD_BG,
            corner_radius=18,
            border_width=1,
            border_color=CARD_BORDER,
            width=308,
        )
        col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        col_izq.grid_propagate(False)

        canvas_video = tk.Canvas(
            col_izq,
            width=270,
            height=480,
            bg="#000000",
            highlightthickness=0,
        )
        canvas_video.pack(padx=18, pady=(16, 8))

        slider_seek = ctk.CTkSlider(
            col_izq,
            from_=0.0,
            to=1.0,
            height=12,
            progress_color=PURPLE_MAIN,
            button_color=CYAN_ACCENT,
            button_hover_color="#38bdf8",
        )
        slider_seek.set(0.0)
        slider_seek.pack(fill="x", padx=18, pady=(0, 6))

        def _fmt_tiempo(s: float) -> str:
            s_int = max(0, int(s))
            return f"{s_int // 60:02d}:{s_int % 60:02d}"

        def _seek_press(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = True

        def _seek_release(event: Any) -> None:
            nonlocal arrastrando_slider
            arrastrando_slider = False
            if player is not None and duracion_total > 0:
                try:
                    player.seek(slider_seek.get() * duracion_total, relative=False)
                    win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        def _on_slider_change(val: float) -> None:
            if arrastrando_slider and duracion_total > 0 and player is not None:
                try:
                    target_pts = float(val) * duracion_total
                    player.seek(target_pts, relative=False)
                    lbl_tiempo.configure(text=f"{_fmt_tiempo(target_pts)} / {_fmt_tiempo(duracion_total)}")
                except Exception:
                    pass

        slider_seek.bind("<Button-1>", _seek_press)
        slider_seek.bind("<ButtonRelease-1>", _seek_release)
        slider_seek.configure(command=_on_slider_change)

        row_ctrl = ctk.CTkFrame(col_izq, fg_color="transparent")
        row_ctrl.pack(fill="x", padx=18, pady=(0, 14))

        btn_play = ctk.CTkButton(
            row_ctrl, text="▶", width=36, height=30, corner_radius=8,
            fg_color=INPUT_BG, hover_color="#2a3147",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_tiempo = ctk.CTkLabel(
            row_ctrl, text="00:00 / 00:00",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        btn_play.pack(side="left", padx=(0, 8))
        lbl_tiempo.pack(side="left")

        slider_vol = ctk.CTkSlider(
            row_ctrl, from_=0.0, to=1.0, width=54, height=12,
            number_of_steps=20, progress_color=CYAN_ACCENT, button_color=CYAN_ACCENT,
        )
        slider_vol.set(1.0)
        lbl_vol = ctk.CTkLabel(row_ctrl, text="Vol", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_DIM)
        slider_vol.pack(side="right")
        lbl_vol.pack(side="right", padx=(0, 4))

        def _on_vol_change(val: float) -> None:
            if player is not None:
                try:
                    player.set_volume(float(val))
                except Exception:
                    pass

        slider_vol.configure(command=_on_vol_change)

        def _toggle_play() -> None:
            nonlocal reproduciendo
            if player is not None:
                try:
                    reproduciendo = not reproduciendo
                    player.set_pause(not reproduciendo)
                    btn_play.configure(text="■" if reproduciendo else "▶")
                    if reproduciendo:
                        win_r.after(10, _loop_reproductor)
                except Exception:
                    pass

        btn_play.configure(command=_toggle_play)

        # ── Columna derecha ────────────────────────────────────────────────
        col_der = ctk.CTkFrame(panel_principal, fg_color="transparent")
        col_der.grid(row=0, column=1, sticky="nsew")
        col_der.grid_rowconfigure(1, weight=1)
        col_der.grid_columnconfigure(0, weight=1)

        # Header compacto
        hdr = ctk.CTkFrame(col_der, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="x", padx=16, pady=10)

        lbl_estado = ctk.CTkLabel(
            hdr_inner,
            text="Video editado" if es_modo_editado else "Short listo para publicar",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_MAIN,
        )
        lbl_estado.pack(side="left")

        lbl_ritmo = ctk.CTkLabel(
            hdr_inner, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=GREEN_ACCENT,
        )
        lbl_ritmo.pack(side="right")

        tit_corto = titulo[:72] + ("..." if len(titulo) > 72 else "")
        ctk.CTkLabel(
            hdr,
            text=tit_corto,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        if url_video_orig and url_video_orig.strip():
            row_url = ctk.CTkFrame(hdr, fg_color="transparent")
            row_url.pack(fill="x", padx=16, pady=(0, 8))

            ent_url_disp = ctk.CTkEntry(
                row_url, height=24,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color=INPUT_BG, border_color=CARD_BORDER, border_width=1,
                text_color=CYAN_ACCENT,
            )
            ent_url_disp.insert(0, url_video_orig.strip())
            ent_url_disp.configure(state="readonly")
            ent_url_disp.pack(side="left", fill="x", expand=True, padx=(0, 6))

            def _abrir_url_navegador() -> None:
                import webbrowser
                try:
                    webbrowser.open(url_video_orig.strip())
                except Exception:
                    pass

            def _copiar_url_clip() -> None:
                try:
                    root.clipboard_clear()
                    root.clipboard_append(url_video_orig.strip())
                    btn_copiar_url.configure(text="Copiado")
                    root.after(1400, lambda: btn_copiar_url.configure(text="Copiar"))
                except Exception:
                    pass

            ctk.CTkButton(
                row_url, text="Abrir", width=52, height=24, corner_radius=8,
                fg_color=INPUT_BG, hover_color="#2a3147",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_abrir_url_navegador,
            ).pack(side="right", padx=(4, 0))

            btn_copiar_url = ctk.CTkButton(
                row_url, text="Copiar", width=52, height=24, corner_radius=8,
                fg_color=INPUT_BG, hover_color="#2a3147",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                command=_copiar_url_clip,
            )
            btn_copiar_url.pack(side="right")

        # Tarjeta guion (ocupa todo el espacio disponible)
        card_guion = ctk.CTkFrame(
            col_der, fg_color=CARD_BG, corner_radius=18,
            border_width=1, border_color=CARD_BORDER,
        )
        card_guion.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        card_guion.grid_rowconfigure(1, weight=1)
        card_guion.grid_columnconfigure(0, weight=1)

        lbl_guion_tit = ctk.CTkLabel(
            card_guion,
            text="Guion editable" if not es_modo_editado else "Metadatos",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_MAIN,
            anchor="w",
        )
        lbl_guion_tit.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        txt_guion_box = VisualScriptEditor(card_guion)
        txt_guion_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))

        if ruta_guion.exists():
            try:
                txt_guion_raw = ruta_guion.read_text(encoding="utf-8", errors="replace")
                txt_guion_box.insert("1.0", txt_guion_raw)
                en_g = False
                res_r = []
                for ln_g in txt_guion_raw.splitlines():
                    if "[GUION]" in ln_g:
                        en_g = True
                        continue
                    if en_g and "|" in ln_g:
                        partes_g = [x.strip() for x in ln_g.split("|")]
                        if len(partes_g) >= 7 and "-" in partes_g[0] and ":" in partes_g[0]:
                            res_r.append(evaluar_ritmo_bloque(partes_g[0], partes_g[6]))
                if res_r:
                    ok_c = sum(1 for r in res_r if r["estado"] == "OK")
                    lbl_ritmo.configure(
                        text=f"Ritmo {ok_c}/{len(res_r)} OK",
                        text_color=GREEN_ACCENT if ok_c == len(res_r) else "#facc15",
                    )
            except Exception:
                pass

        if not es_modo_editado:
            ctk.CTkButton(
                card_guion,
                text="Re-renderizar con guion editado",
                command=lambda: _responder("reeditar"),
                height=34, corner_radius=10,
                fg_color=PURPLE_MAIN, hover_color=PURPLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#ffffff",
            ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        else:
            tam_mb = ""
            try:
                tam_mb = f" · {ruta_video.stat().st_size / (1024 * 1024):.1f} MB"
            except Exception:
                pass
            ctk.CTkLabel(
                card_guion,
                text=f"{ruta_video.name}{tam_mb}",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_DIM, anchor="w",
            ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 10))

        # Tarjeta de acciones (fija abajo)
        card_acciones = ctk.CTkFrame(
            col_der, fg_color=CARD_BG, corner_radius=18,
            border_width=1, border_color=CARD_BORDER,
        )
        card_acciones.grid(row=2, column=0, sticky="ew")

        btn_subir = ctk.CTkButton(
            card_acciones,
            text="Subir a YouTube",
            command=lambda: _responder("subir"),
            height=40, corner_radius=12,
            fg_color=GREEN_ACCENT, hover_color="#059669",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#ffffff",
        )
        btn_subir.pack(fill="x", padx=16, pady=(12, 8))

        row_sec = ctk.CTkFrame(card_acciones, fg_color="transparent")
        row_sec.pack(fill="x", padx=16, pady=(0, 12))
        row_sec.grid_columnconfigure((0, 1), weight=1, uniform="sec_btn")

        ctk.CTkButton(
            row_sec,
            text="Siguiente Video" if es_modo_editado else "Buscar Otro Video",
            command=lambda: _responder("buscar_otro"),
            height=32, corner_radius=10,
            fg_color=INPUT_BG, hover_color="#1e2538",
            border_width=1, border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff",
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            row_sec,
            text="Cancelar",
            command=lambda: _responder("descartar"),
            height=32, corner_radius=10,
            fg_color=INPUT_BG, hover_color="#7f1d1d",
            border_width=1, border_color="#2a3147",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=1, padx=(4, 0), sticky="ew")""",
    ),
]
