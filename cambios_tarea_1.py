ARCHIVO = "shorts_engine/youtube_manager.py"
CAMBIOS = [
    (
        '    cmd = [\n        *cmd_base,\n        *args_js,\n        "--remote-components", "ejs:github",\n        "--write-info-json",\n        "-f", "bv*+ba/best",\n        "--merge-output-format", "mp4",\n        "-S", "res:1080,fps:60,br",\n        "-o", "video_input.%(ext)s",\n        url_limpia,\n    ]',
        '    cmd = [\n        *cmd_base,\n        *args_js,\n        "--remote-components", "ejs:github",\n        "--write-info-json",\n        "-f", "bv*+ba/best",\n        "--merge-output-format", "mp4",\n        "-S", "res:1080,fps:60,br",\n        "--concurrent-fragments", "8",\n        "--buffer-size", "64K",\n        "--socket-timeout", "12",\n        "-o", "video_input.%(ext)s",\n        url_limpia,\n    ]'
    ),
    (
        '    cmd = [\n        *cmd_base,\n        "--flat-playlist",\n        "--dump-json",\n        "--playlist-end",\n        str(max_escanear),\n        url_shorts,\n    ]',
        '    cmd = [\n        *cmd_base,\n        "--flat-playlist",\n        "--dump-json",\n        "--socket-timeout", "10",\n        "--extractor-args", "youtubetab:approximate_date",\n        "--playlist-end",\n        str(max_escanear),\n        url_shorts,\n    ]'
    ),
]
