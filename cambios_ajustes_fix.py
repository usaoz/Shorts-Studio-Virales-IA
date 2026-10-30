ARCHIVO = "Editor_Shorts_Studio.py"

CAMBIOS = [
    # Revertir: sacar CTkScrollableFrame, volver cards a win directo, mantener solo deiconify diferido
    (
        """    def abrir_ventana_ajustes() -> None:
        win = ctk.CTkToplevel(root)
        win.withdraw()
        win.title("Ajustes y Herramientas")
        win.geometry("600x720")
        win.resizable(False, True)
        win.configure(fg_color=BG_DARK)
        win.transient(root)

        # Scroll para evitar placeholders negros en pantallas pequeñas
        _sc = ctk.CTkScrollableFrame(win, fg_color=BG_DARK, scrollbar_button_color="#2a3147", scrollbar_button_hover_color="#3b4a6b")
        _sc.pack(fill="both", expand=True)

        # 1. Tarjeta de Modo de Trabajo, Título/Guión (IA vs Manual), Acción Final y Selección de Canales
        card_modo = ctk.CTkFrame(_sc, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_modo.pack(fill="x", padx=24, pady=(18, 8))""",
        """    def abrir_ventana_ajustes() -> None:
        win = ctk.CTkToplevel(root)
        win.withdraw()
        win.title("Ajustes y Herramientas")
        win.geometry("600x820")
        win.resizable(False, False)
        win.configure(fg_color=BG_DARK)
        win.transient(root)

        # 1. Tarjeta de Modo de Trabajo, Título/Guión (IA vs Manual), Acción Final y Selección de Canales
        card_modo = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_modo.pack(fill="x", padx=24, pady=(18, 8))""",
    ),
    # card_cfg _sc -> win
    (
        """        card_cfg = ctk.CTkFrame(_sc, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_cfg.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(
            card_cfg,
            text="Voz del Narrador IA",""",
        """        card_cfg = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_cfg.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(
            card_cfg,
            text="Voz del Narrador IA",""",
    ),
    # card_api _sc -> win
    (
        """        card_api = ctk.CTkFrame(_sc, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_api.pack(fill="x", padx=24, pady=(0, 10))""",
        """        card_api = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_api.pack(fill="x", padx=24, pady=(0, 10))""",
    ),
    # card_tools _sc -> win
    (
        """        card_tools = ctk.CTkFrame(_sc, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_tools.pack(fill="x", padx=24, pady=(0, 12))""",
        """        card_tools = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card_tools.pack(fill="x", padx=24, pady=(0, 12))""",
    ),
]
