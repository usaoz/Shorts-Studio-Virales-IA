ARCHIVO = "Editor_Shorts_Studio.py"

CAMBIOS = [
    (
        """        aplicar_icono_ventana(win)

        def _mostrar_ajustes():
            win.update_idletasks()
            win.deiconify()
            win.lift()
            win.focus_force()
            win.grab_set()

        win.after(1, _mostrar_ajustes)

    def finalizar_app_completamente""",
        """        aplicar_icono_ventana(win)
        win.update_idletasks()
        win.deiconify()
        win.lift()
        win.focus_force()
        win.grab_set()

    def finalizar_app_completamente""",
    ),
]
