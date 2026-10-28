"""Reemplazo seguro de bloques de texto (alternativa robusta a editores que fallan por CRLF/espacios).
Uso:  python tools/reemplazar.py cambios.py
Donde cambios.py define:  ARCHIVO = "Editor_Shorts_Studio.py"
                          CAMBIOS = [("texto viejo exacto", "texto nuevo"), ...]
- Normaliza CRLF -> compara en LF y conserva el fin de linea original.
- Si un bloque no aparece EXACTAMENTE 1 vez, aborta SIN escribir nada y dice cual fallo."""
import os, sys, runpy

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = runpy.run_path(sys.argv[1])
ruta = os.path.join(RAIZ, cfg["ARCHIVO"])
raw = open(ruta, "rb").read().decode("utf-8")
crlf = "\r\n" in raw
txt = raw.replace("\r\n", "\n")
for n, (viejo, nuevo) in enumerate(cfg["CAMBIOS"], 1):
    viejo = viejo.replace("\r\n", "\n")
    c = txt.count(viejo)
    if c != 1:
        print(f"[ABORTADO] Cambio #{n}: aparece {c} veces (debe ser 1). Inicio: {viejo[:80]!r}")
        sys.exit(1)
    txt = txt.replace(viejo, nuevo.replace("\r\n", "\n"))
if crlf:
    txt = txt.replace("\n", "\r\n")
open(ruta, "wb").write(txt.encode("utf-8"))
print(f"[OK] {len(cfg['CAMBIOS'])} cambio(s) aplicados en {cfg['ARCHIVO']}")
