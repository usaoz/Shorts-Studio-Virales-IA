"""Verificacion rapida en 1 comando: compila todo + arranca la GUI sin mostrarla.
Uso:  python tools/verificar.py          (compila + GUI)
      python tools/verificar.py --rapido (solo compila, ~1s)
Sale con codigo 0 si todo OK."""
import os, sys, py_compile, traceback, glob

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)

archivos = ["Editor_Shorts_Studio.py", "subir_a_youtube.py"] + glob.glob("shorts_engine/*.py")
for f in archivos:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"[ERROR SINTAXIS] {e.msg}")
        sys.exit(1)
print(f"[OK] Compilan {len(archivos)} archivos")
if "--rapido" in sys.argv:
    sys.exit(0)

import customtkinter as ctk
errores = []

def _runner(root, *a, **k):
    try:
        root.update(); root.update_idletasks()
    except Exception:
        errores.append(traceback.format_exc())
    finally:
        root.destroy()

ctk.CTk.mainloop = _runner
try:
    import Editor_Shorts_Studio
    Editor_Shorts_Studio.iniciar_aplicacion_gui()
except Exception:
    errores.append(traceback.format_exc())

if errores:
    print("[ERROR GUI]\n" + "\n".join(errores))
    sys.exit(1)
print("[OK] GUI arranca sin errores")
