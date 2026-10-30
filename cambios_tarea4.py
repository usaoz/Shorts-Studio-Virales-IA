"""
Script de cambios para TAREA 4: Aceleración encoder FFmpeg en video_render.py
Uso: python tools/reemplazar.py cambios_tarea4.py
"""
ARCHIVO = "shorts_engine/video_render.py"
CAMBIOS = [
    (
        '    hilos_cpu = max(4, min(8, CPU_THREADS // 2))\r\n'
        '    args_cpu = [\r\n'
        '        "-c:v", "libx264", "-preset", "fast", "-crf", "18",\r\n'
        '        "-threads", str(hilos_cpu), "-pix_fmt", "yuv420p",\r\n'
        '    ]\r\n'
        '    if forzar_cpu:\r\n'
        '        return ("libx264", args_cpu)',
        '    hilos_cpu = min(16, CPU_THREADS)\r\n'
        '    args_cpu = [\r\n'
        '        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",\r\n'
        '        "-threads", str(hilos_cpu), "-pix_fmt", "yuv420p",\r\n'
        '        "-movflags", "+faststart",\r\n'
        '    ]\r\n'
        '    if forzar_cpu:\r\n'
        '        return ("libx264", args_cpu)',
    ),
    (
        '        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p"]),',
        '        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "19", "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p"]),',
    ),
    (
        '    # Fallback equilibrado por CPU (libx264 preset fast CRF 18)\r\n'
        '    _ENCODER_SELECCIONADO = ("libx264", args_cpu)',
        '    # Fallback CPU ultrafast (libx264 ultrafast CRF 18, todos los hilos)\r\n'
        '    _ENCODER_SELECCIONADO = ("libx264", args_cpu)',
    ),
]
