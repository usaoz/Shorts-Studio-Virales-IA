"""Mapa del codigo con numeros de linea (siempre actualizado, se genera al vuelo).
Uso:  python tools/mapa.py                 -> secciones + funciones de Editor_Shorts_Studio.py
      python tools/mapa.py buscar <texto>  -> lineas que contienen <texto> (en todo el proyecto)
      python tools/mapa.py widget <nombre> -> donde se crea / configura / empaqueta un widget
Evita leer el archivo completo (4600+ lineas): pedi solo el rango que necesitas."""
import os, re, sys, glob

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RAIZ)
MAIN = "Editor_Shorts_Studio.py"
ARCHIVOS = [MAIN, "subir_a_youtube.py"] + sorted(glob.glob("shorts_engine/*.py"))

def leer(f):
    with open(f, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()

def mapa():
    lineas = leer(MAIN)
    for i, ln in enumerate(lineas, 1):
        s = ln.strip()
        m = re.match(r"(\s*)def (\w+)", ln)
        if m and len(m.group(1)) <= 8:
            print(f"{i:5d}  {'  ' * (len(m.group(1)) // 4)}def {m.group(2)}")
        elif s.startswith("# ") and s.isupper() is False and len(s) > 12 and lineas[i - 2].strip().startswith("# ===="):
            print(f"{i:5d}  ## {s[2:80]}")
        elif re.match(r"\s{4}(\w+) = ctk\.CTk(Button|Frame|OptionMenu|SegmentedButton|Label)\(", ln):
            print(f"{i:5d}      [widget] {ln.strip().split(' =')[0]}")
    for f in ARCHIVOS[1:]:
        defs = [f"{i}:{m.group(1)}" for i, ln in enumerate(leer(f), 1) if (m := re.match(r"(?:async )?def (\w+)", ln))]
        print(f"\n{f}: " + ", ".join(defs))

def buscar(txt, solo=None):
    for f in ARCHIVOS:
        for i, ln in enumerate(leer(f), 1):
            if txt in ln and (solo is None or solo(ln)):
                print(f"{f}:{i}: {ln.strip()[:150]}")

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "buscar":
        buscar(" ".join(sys.argv[2:]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "widget":
        w = sys.argv[2]
        buscar(w, lambda ln: any(k in ln for k in (f"{w} =", f"{w}.pack", f"{w}.grid", f"{w}.configure", f"{w}.pack_forget", f"{w}.grid_remove")))
    else:
        mapa()
