import sys, time, re
sys.path.insert(0, r"D:\YOUTUBE SHORTS")
from pathlib import Path
from google import genai
from google.genai import types
from shorts_engine.gemini_ia import generar_mosaico_video, generar_video_compacto_ia, PROMPT_COMPACTO_INTERNO

key = Path(r"D:\YOUTUBE SHORTS\gemini_api_key.txt").read_text(encoding="utf-8").strip()
vid = Path(r"D:\YOUTUBE SHORTS\video_input.mp4")
jpg, dur = generar_mosaico_video(vid)
vb, _ = generar_video_compacto_ia(vid)
d = max(5, int(round(dur)))
prompt = PROMPT_COMPACTO_INTERNO + f"\nDuración total: {d} segundos. Bloques de 5s de 00:00 a 00:{d:02d}. ESTADO_PUBLICACION: privado. SCHEDULE: no. PARA_NINOS: no. Entrega ÚNICAMENTE el bloque de guion:"
parts = [types.Part.from_bytes(data=vb, mime_type="video/mp4"), types.Part.from_bytes(data=jpg, mime_type="image/jpeg"), prompt]
cli = genai.Client(api_key=key)
for m in sys.argv[1:]:
    t = time.time()
    try:
        r = cli.models.generate_content(model=m, contents=parts)
        txt = r.text or ""
        bloques = len(re.findall(r"^\s*\d{1,2}[:\.]\d{2}\s*-", txt, re.M))
        print(f"=== {m}: {time.time()-t:.1f}s | [GUION]={'[GUION]' in txt} | bloques={bloques} | dur={d}s")
        print(txt[:1400])
    except Exception as e:
        print(f"=== {m}: ERROR {str(e)[:300]}")
