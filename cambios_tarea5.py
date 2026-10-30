"""
Script de cambios para TAREA 5: Bypass compresión IA <12 MB en gemini_ia.py
Uso: python tools/reemplazar.py cambios_tarea5.py
"""
ARCHIVO = "shorts_engine/gemini_ia.py"
CAMBIOS = [
    (
        '    dur_seg, w_v, h_v, _ = obtener_info_video(ruta_video)\n'
        '    TEMP_DIR.mkdir(parents=True, exist_ok=True)\n'
        '    ruta_low = TEMP_DIR / "video_analisis_ia.mp4"\n'
        '    if ruta_low.exists():\n'
        '        try:\n'
        '            ruta_low.unlink()\n'
        '        except OSError:\n'
        '            pass\n'
        '\n'
        '    filtro_escala = "scale=360:640:flags=fast_bilinear,fps=4" if (h_v >= w_v) else "scale=640:360:flags=fast_bilinear,fps=4"\n'
        '    res = subprocess.run(\n'
        '        [\n'
        '            "ffmpeg", "-y",\n'
        '            "-i", str(ruta_video),\n'
        '            "-vf", filtro_escala,\n'
        '            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",\n'
        '            "-c:a", "aac", "-b:a", "48k",\n'
        '            str(ruta_low),\n'
        '        ],',
        '    dur_seg, w_v, h_v, _ = obtener_info_video(ruta_video)\n'
        '\n'
        '    # Bypass: si el video original ya pesa menos de 12 MB, no re-codificar.\n'
        '    # El 95% de los Shorts de 15-40s pesan 3-9 MB, evitamos 3-5 segundos de FFmpeg innecesario.\n'
        '    try:\n'
        '        peso_original = ruta_video.stat().st_size\n'
        '        if peso_original <= 12 * 1024 * 1024:\n'
        '            return ruta_video.read_bytes(), dur_seg\n'
        '    except Exception:\n'
        '        pass\n'
        '\n'
        '    TEMP_DIR.mkdir(parents=True, exist_ok=True)\n'
        '    ruta_low = TEMP_DIR / "video_analisis_ia.mp4"\n'
        '    if ruta_low.exists():\n'
        '        try:\n'
        '            ruta_low.unlink()\n'
        '        except OSError:\n'
        '            pass\n'
        '\n'
        '    filtro_escala = "scale=360:640:flags=fast_bilinear,fps=4" if (h_v >= w_v) else "scale=640:360:flags=fast_bilinear,fps=4"\n'
        '    res = subprocess.run(\n'
        '        [\n'
        '            "ffmpeg", "-y",\n'
        '            "-i", str(ruta_video),\n'
        '            "-vf", filtro_escala,\n'
        '            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "32",\n'
        '            "-c:a", "aac", "-b:a", "48k",\n'
        '            str(ruta_low),\n'
        '        ],',
    ),
]
