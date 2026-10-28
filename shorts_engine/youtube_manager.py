# -*- coding: utf-8 -*-
import datetime as _dt
import json
import shutil
import os
import random
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from .config import (
    BASE_DIR, DEFAULT_VIDEO_INPUT, WIN_NO_WINDOW, WIN_STARTUPINFO
)

# ==============================================================================
# 9. DESCARGA CON YT-DLP E INTERFAZ GRÁFICA COMPLETA (APLICACIÓN DE ESCRITORIO)
# ==============================================================================
ULTIMA_INFO_YTDLP: Dict[str, str] = {"titulo": "", "descripcion": ""}


def descargar_video_youtube(url: str) -> Path:
    """
    Descarga el video o Short de YouTube usando yt-dlp en formato MP4 compatible
    y guarda su título/descripción original (`--write-info-json`) para que la IA
    entienda siempre el contexto real exacto de lo que ocurre en el video.
    """
    url_limpia = url.strip()
    if not url_limpia:
        raise ValueError("La URL del video de YouTube está vacía.")

    ULTIMA_INFO_YTDLP["titulo"] = ""
    ULTIMA_INFO_YTDLP["descripcion"] = ""

    for existente in BASE_DIR.glob("video_input.*"):
        try:
            existente.unlink()
        except OSError:
            pass

    ejecutable_ytdlp = shutil.which("yt-dlp")
    if ejecutable_ytdlp:
        cmd_base = [ejecutable_ytdlp]
    else:
        cmd_base = [sys.executable, "-m", "yt_dlp"]

    args_js = ["--js-runtimes", "node"] if shutil.which("node") else []

    cmd = [
        *cmd_base,
        *args_js,
        "--remote-components", "ejs:github",
        "--write-info-json",
        "-f", "bv*+ba/best",
        "--merge-output-format", "mp4",
        "-S", "res:1080,fps:60,br",
        "-o", "video_input.%(ext)s",
        url_limpia,
    ]

    print("=" * 78)
    print(f"[*] Descargando video de YouTube con yt-dlp: {url_limpia}")
    print("=" * 78)

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=WIN_NO_WINDOW,
        startupinfo=WIN_STARTUPINFO,
    )
    if proc.stdout:
        for linea in proc.stdout:
            linea_s = linea.rstrip()
            if linea_s:
                print(f"[yt-dlp] {linea_s}")
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp terminó con código {proc.returncode}. Verifica que el link de YouTube sea válido.")

    info_json_path = BASE_DIR / "video_input.info.json"
    if info_json_path.exists():
        try:
            datos_info = json.loads(info_json_path.read_text(encoding="utf-8", errors="replace"))
            ULTIMA_INFO_YTDLP["titulo"] = str(datos_info.get("title") or "").strip()
            ULTIMA_INFO_YTDLP["descripcion"] = str(datos_info.get("description") or "").strip()[:500]
        except Exception:
            pass

    ruta_res: Optional[Path] = None
    if DEFAULT_VIDEO_INPUT.exists():
        ruta_res = DEFAULT_VIDEO_INPUT
    else:
        descargados = [p for p in sorted(BASE_DIR.glob("video_input.*")) if not p.name.endswith(".json")]
        if descargados:
            ruta_res = descargados[0]

    if ruta_res is not None:
        try:
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,bit_rate,r_frame_rate",
                "-of", "json",
                str(ruta_res),
            ]
            res_p = subprocess.run(
                cmd_probe,
                capture_output=True,
                text=True,
                check=False,
                creationflags=WIN_NO_WINDOW,
                startupinfo=WIN_STARTUPINFO,
            )
            if res_p.returncode == 0:
                st = json.loads(res_p.stdout).get("streams", [{}])[0]
                w_dl = int(st.get("width") or 0)
                h_dl = int(st.get("height") or 0)
                br_dl = int(st.get("bit_rate") or 0) // 1000
                fps_dl = st.get("r_frame_rate", "")
                print(f"[+] Video fuente descargado: {w_dl}x{h_dl} @ {fps_dl} ({br_dl} kbps)")
                if min(w_dl, h_dl) < 720:
                    print(f"[!] AVISO: El video en YouTube solo estaba disponible en {w_dl}x{h_dl}. Se reescalará a 1080x1920 con algoritmo Lanczos.")
                else:
                    print(f"[+] Resolución HD confirmada en el video descargado ({w_dl}x{h_dl}).")
        except Exception:
            pass
        return ruta_res

    raise FileNotFoundError("No se encontró el archivo 'video_input.mp4' luego de la descarga.")



# ==============================================================================
# 9.5 POOL DE CANALES VIRALES, HISTORIAL ANTI-REPETIDOS Y CUOTA DE API DIARIA
# ==============================================================================
HISTORIAL_USADOS_FILE = BASE_DIR / "videos_usados.json"
CUOTA_DIARIA_FILE = BASE_DIR / "cuota_api_diaria.json"
MAX_SHORTS_YOUTUBE_DIA = 6  # 10.000 unidades YouTube Data API v3 / 1.600 por subida = 6 Shorts gratis/día


def normalizar_url_canal_shorts(entrada: str) -> str:
    """
    Convierte '@NombreCanal', 'NombreCanal' o cualquier URL de canal de YouTube
    en la URL directa a su pestaña '/shorts'.
    """
    s = entrada.strip().strip('"').rstrip("/")
    if not s:
        return ""
    if s.startswith("@"):
        return f"https://www.youtube.com/{s}/shorts"
    if not s.startswith(("http://", "https://")):
        if "youtube.com" in s or "youtu.be" in s:
            s = "https://" + s
        else:
            return f"https://www.youtube.com/@{s.lstrip('@')}/shorts"
    # Quitar sufijos previos (/videos, /featured, /streams) y asegurar /shorts
    for suf in ("/shorts", "/videos", "/featured", "/streams", "/community", "/playlists"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)]
            break
    return f"{s}/shorts"


def etiqueta_corta_canal(url_canal: str) -> str:
    m = re.search(r"(@[^/?#]+)", url_canal)
    if m:
        return m.group(1)
    partes = [p for p in url_canal.replace("/shorts", "").split("/") if p]
    return partes[-1] if partes else url_canal


def cargar_videos_usados() -> Set[str]:
    if HISTORIAL_USADOS_FILE.exists():
        try:
            datos = json.loads(HISTORIAL_USADOS_FILE.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                return set(str(x) for x in datos)
        except Exception:
            pass
    return set()


def registrar_video_usado(video_id_o_url: str) -> None:
    usados = cargar_videos_usados()
    vid = video_id_o_url.strip()
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", vid)
    if m:
        usados.add(m.group(1))
    else:
        usados.add(vid)
    try:
        HISTORIAL_USADOS_FILE.write_text(json.dumps(sorted(usados), indent=2), encoding="utf-8")
    except Exception:
        pass


def _fecha_cuota_pacifico_iso() -> str:
    """
    La cuota de YouTube Data API v3 se reinicia todos los días a las 00:00 Pacific Time (UTC-7/UTC-8).
    """
    import datetime as _dt
    tz_pt = _dt.timezone(_dt.timedelta(hours=-7))
    return _dt.datetime.now(tz_pt).strftime("%Y-%m-%d")


def _cargar_datos_cuota_raw() -> Dict[str, object]:
    if CUOTA_DIARIA_FILE.exists():
        try:
            return json.loads(CUOTA_DIARIA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def obtener_max_shorts_pool_dia() -> Tuple[int, int]:
    """
    Devuelve `(max_shorts_dia_total, cantidad_proyectos_api)` según cuántos archivos
    `client_secrets*.json` únicos haya cargados en el Pool (`apis_google/` + principal).
    Cada proyecto de Google Cloud aporta 6 Shorts gratis por día.
    """
    try:
        from subir_a_youtube import listar_archivos_credenciales_pool
        n_apis = max(1, len(listar_archivos_credenciales_pool()))
    except Exception:
        n_apis = 1
    return n_apis * MAX_SHORTS_YOUTUBE_DIA, n_apis


def obtener_estado_cuota_diaria() -> Tuple[int, int, float]:
    """
    Devuelve (usados_hoy, disponibles_restantes, porcentaje_disponible_0_a_1).
    Se reinicia automáticamente cada nuevo día de cuota (Pacific Time), escala con
    la cantidad de proyectos API cargados en el Pool (6 Shorts x N APIs) y excluye
    los videos que fueron subidos ayer pero programados para salir hoy.
    """
    import datetime as _dt
    max_total, _ = obtener_max_shorts_pool_dia()
    hoy_pt = _fecha_cuota_pacifico_iso()
    hoy_local = _dt.date.today().strftime("%Y-%m-%d")
    d = _cargar_datos_cuota_raw()
    usados_hoy = 0
    if d.get("fecha") in (hoy_pt, hoy_local):
        ids_hoy = d.get("ids_subidos_hoy")
        if isinstance(ids_hoy, list):
            usados_hoy = max(int(d.get("subidos", 0)), len(ids_hoy))
        else:
            usados_hoy = int(d.get("subidos", 0))
    restantes = max(0, max_total - usados_hoy)
    pct_disp = restantes / float(max(1, max_total))
    return usados_hoy, restantes, pct_disp


def incrementar_cuota_diaria(video_id: Optional[str] = None) -> None:
    """
    Registra que se consumieron 1,600 unidades de cuota HOY al ejecutar `videos.insert`,
    guardando el `video_id` en el historial de subidas para que mañana, cuando el video
    se haga público por programación (`publishAt`), NO se vuelva a descontar como gasto
    de mañana.
    """
    hoy_pt = _fecha_cuota_pacifico_iso()
    d = _cargar_datos_cuota_raw()
    historial: Dict[str, str] = dict(d.get("historial_ids_fecha_subida") or {})
    ids_hoy: List[str] = list(d.get("ids_subidos_hoy") or []) if d.get("fecha") == hoy_pt else []

    usados, _, _ = obtener_estado_cuota_diaria()
    nuevo_usados = usados + 1

    if video_id:
        vid_clean = str(video_id).strip()
        historial[vid_clean] = hoy_pt
        if vid_clean not in ids_hoy:
            ids_hoy.append(vid_clean)
        nuevo_usados = max(nuevo_usados, len(ids_hoy))

    try:
        CUOTA_DIARIA_FILE.write_text(
            json.dumps(
                {
                    "fecha": hoy_pt,
                    "subidos": nuevo_usados,
                    "ids_subidos_hoy": ids_hoy,
                    "historial_ids_fecha_subida": historial,
                    "sincronizado_yt": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def sincronizar_cuota_real_youtube() -> Tuple[int, int, float]:
    """
    Consulta directamente a la API de Google/YouTube los videos del canal para
    contar cuántos tokens se gastaron HOY (en el día de cuota actual, Pacific Time).
    IMPORTANTE:
    - En YouTube, `snippet.publishedAt` dentro de la playlist `uploads` es el momento
      exacto en que el archivo fue SUBIDO a los servidores (momento en que se gastaron
      los tokens), mientras que `status.publishAt` es la fecha futura programada.
    - Además, cruzamos con `historial_ids_fecha_subida`: si un video fue subido ayer
      programado para hoy, queda etiquetado con la fecha de ayer y JAMÁS descuenta
      tokens del día de hoy.
    """
    import datetime as _dt
    tz_pt = _dt.timezone(_dt.timedelta(hours=-7))
    hoy_pt_date = _dt.datetime.now(tz_pt).date()
    hoy_pt_iso = hoy_pt_date.strftime("%Y-%m-%d")

    d_prev = _cargar_datos_cuota_raw()
    historial: Dict[str, str] = dict(d_prev.get("historial_ids_fecha_subida") or {})
    ids_hoy_prev: List[str] = (
        list(d_prev.get("ids_subidos_hoy") or []) if d_prev.get("fecha") == hoy_pt_iso else []
    )
    usados_local, _, _ = obtener_estado_cuota_diaria()

    ids_detectados_hoy: Set[str] = set(ids_hoy_prev)
    try:
        from subir_a_youtube import obtener_servicio_youtube, listar_cuentas_vinculadas
        cuentas_v = listar_cuentas_vinculadas()
        for c_item in cuentas_v:
            cid_chk = str(c_item.get("id") or "principal")
            try:
                yt = obtener_servicio_youtube(cuenta_id=cid_chk)
                ch_resp = yt.channels().list(mine=True, part="contentDetails").execute()
                items_ch = ch_resp.get("items", [])
                if items_ch:
                    uploads_id = items_ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
                    pl_resp = yt.playlistItems().list(
                        playlistId=uploads_id,
                        part="snippet,contentDetails",
                        maxResults=25,
                    ).execute()
                    for it in pl_resp.get("items", []):
                        vid_id = (
                            it.get("contentDetails", {}).get("videoId")
                            or it.get("snippet", {}).get("resourceId", {}).get("videoId")
                            or ""
                        ).strip()
                        if not vid_id:
                            continue

                        # Si ya sabemos que este video se subió en una fecha anterior, NO gasta cuota hoy
                        fecha_conocida = historial.get(vid_id)
                        if fecha_conocida and fecha_conocida != hoy_pt_iso:
                            continue
                        if fecha_conocida == hoy_pt_iso:
                            ids_detectados_hoy.add(vid_id)
                            continue

                        # `snippet.publishedAt` en playlistItems es la fecha/hora de subida del item a la playlist uploads
                        upload_str = it.get("snippet", {}).get("publishedAt") or ""
                        if not upload_str:
                            continue
                        try:
                            dt_utc = _dt.datetime.fromisoformat(upload_str.replace("Z", "+00:00"))
                            dt_pt = dt_utc.astimezone(tz_pt)
                            fecha_item_iso = dt_pt.date().strftime("%Y-%m-%d")
                            historial[vid_id] = fecha_item_iso
                            if dt_pt.date() == hoy_pt_date:
                                ids_detectados_hoy.add(vid_id)
                        except Exception:
                            continue
            except Exception:
                continue

        real_usados = max(usados_local, len(ids_detectados_hoy))
        CUOTA_DIARIA_FILE.write_text(
            json.dumps(
                {
                    "fecha": hoy_pt_iso,
                    "subidos": real_usados,
                    "ids_subidos_hoy": sorted(ids_detectados_hoy),
                    "historial_ids_fecha_subida": historial,
                    "sincronizado_yt": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return obtener_estado_cuota_diaria()


def buscar_short_viral_en_canal(
    url_canal: str,
    min_views: int = 1_000_000,
    max_escanear: int = 45,
    estricto_min_views: bool = True,
) -> Optional[Tuple[str, str, int]]:
    """
    Escanea rápidamente la pestaña /shorts de un canal con yt-dlp (--flat-playlist)
    y devuelve el primer Short NO usado previamente que supere `min_views`.
    Si `estricto_min_views=True` y ningún video supera `min_views`, retorna None para que
    el flujo busque en el siguiente canal disponible.
    Retorna (url_short, titulo, view_count) o None.
    """
    url_shorts = normalizar_url_canal_shorts(url_canal)
    if not url_shorts:
        return None

    usados = cargar_videos_usados()
    ejecutable_ytdlp = shutil.which("yt-dlp")
    cmd_base = [ejecutable_ytdlp] if ejecutable_ytdlp else [sys.executable, "-m", "yt_dlp"]

    cmd = [
        *cmd_base,
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(max_escanear),
        url_shorts,
    ]
    print(f"[*] Escaneando Shorts virales en {etiqueta_corta_canal(url_shorts)} (mínimo {min_views:,} vistas)...")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=28,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )
    except Exception as e:
        print(f"[!] Error al escanear canal {url_shorts}: {e}")
        return None

    candidatos: List[Tuple[str, str, int]] = []
    respaldo_sin_min: List[Tuple[str, str, int]] = []
    for linea in proc.stdout.splitlines():
        linea_s = linea.strip()
        if not linea_s.startswith("{"):
            continue
        try:
            item = json.loads(linea_s)
            vid_id = str(item.get("id") or "").strip()
            if not vid_id or vid_id in usados:
                continue
            vistas = int(item.get("view_count") or 0)
            titulo = str(item.get("title") or vid_id)
            url_v = f"https://www.youtube.com/shorts/{vid_id}"
            if vistas >= min_views:
                candidatos.append((url_v, titulo, vistas))
            else:
                respaldo_sin_min.append((url_v, titulo, vistas))
        except Exception:
            continue

    if candidatos:
        elegido = candidatos[0]
        print(f"[+] Short viral encontrado en {etiqueta_corta_canal(url_shorts)}: '{elegido[1]}' ({elegido[2]:,} vistas) -> {elegido[0]}")
        return elegido

    if estricto_min_views:
        max_v = max([x[2] for x in respaldo_sin_min], default=0)
        print(
            f"[-] Canal {etiqueta_corta_canal(url_shorts)}: ningún Short sin usar alcanzó {min_views:,} vistas "
            f"(el más visto tiene {max_v:,} vistas). Pasando al siguiente canal..."
        )
        return None

    if respaldo_sin_min:
        # Si ningún video reciente superó el umbral pero hay videos sin usar, ordenar por el más visto
        respaldo_sin_min.sort(key=lambda x: x[2], reverse=True)
        mejor = respaldo_sin_min[0]
        print(
            f"[!] Ningún Short reciente superó {min_views:,} vistas; "
            f"eligiendo el más visto disponible ({mejor[2]:,} vistas): '{mejor[1]}'"
        )
        return mejor

    return None


HORARIOS_PICO_OPTIMOS: Dict[int, List[str]] = {
    1: ["19:00"],
    2: ["13:00", "20:00"],
    3: ["12:30", "17:30", "21:00"],
    4: ["11:00", "15:00", "18:30", "21:30"],
    5: ["10:00", "13:00", "16:00", "19:00", "22:00"],
    6: ["09:30", "12:00", "14:30", "17:00", "19:30", "22:00"],
}


def calcular_horarios_inteligentes(
    cantidad_total: int,
    por_dia: int,
    fecha_base_iso: str,
    modo_horario: str = "Horarios Pico",
    hora_inicio: str = "13:00",
    intervalo_hs: int = 8,
) -> List[str]:
    """
    Calcula la agenda exacta ('YYYY-MM-DD HH:MM') para `cantidad_total` Shorts
    respetando un máximo de `por_dia` salidas por fecha y asegurando que NUNCA
    salgan dos videos al mismo tiempo:
    - En modo 'Horarios Pico (Auto)': usa los mejores horarios virales según la
      cantidad diaria elegida (1 a 6 por día).
    - En modo 'Cada X hs (Desde mi Hora)': arranca desde `hora_inicio` y suma
      `intervalo_hs` entre cada Short hasta completar `por_dia` en ese día, pasando
      luego al día siguiente.
    """
    import datetime as _dt
    ahora = _dt.datetime.now()
    limite_minimo = ahora + _dt.timedelta(minutes=12)

    try:
        d_base = _dt.date.fromisoformat(fecha_base_iso)
    except Exception:
        d_base = ahora.date()
    if d_base < ahora.date():
        d_base = ahora.date()

    cantidad_total = max(1, min(18, int(cantidad_total)))
    por_dia = max(1, min(6, int(por_dia)))
    intervalo_hs = max(1, min(24, int(intervalo_hs)))

    slots: List[str] = []

    if "Específ" in modo_horario or "Fijo" in modo_horario or "especif" in modo_horario.lower():
        try:
            partes = hora_inicio.strip().split(":", 1)
            hh_esp = int(partes[0])
            mm_esp = int(partes[1]) if len(partes) > 1 else 0
        except Exception:
            hh_esp, mm_esp = 13, 0
        hh_esp = max(0, min(23, hh_esp))
        mm_esp = max(0, min(59, mm_esp))

        d_cursor = d_base
        guard = 0
        paso_hs = max(1, 24 // por_dia) if por_dia > 1 else 24
        while len(slots) < cantidad_total and guard < 60:
            guard += 1
            dt_base_dia = _dt.datetime(d_cursor.year, d_cursor.month, d_cursor.day, hh_esp, mm_esp)
            for idx_p in range(por_dia):
                dt_cand = dt_base_dia + _dt.timedelta(hours=idx_p * paso_hs)
                if dt_cand > limite_minimo:
                    cand_str = dt_cand.strftime("%Y-%m-%d %H:%M")
                    if not slots or cand_str > slots[-1]:
                        slots.append(cand_str)
                        if len(slots) >= cantidad_total:
                            break
            d_cursor += _dt.timedelta(days=1)
        return slots

    if "Pico" in modo_horario:
        horas_del_dia = HORARIOS_PICO_OPTIMOS.get(por_dia, HORARIOS_PICO_OPTIMOS[2])
        d_cursor = d_base
        guard = 0
        while len(slots) < cantidad_total and guard < 60:
            guard += 1
            for h_str in horas_del_dia:
                hh, mm = [int(x) for x in h_str.split(":", 1)]
                dt_cand = _dt.datetime(d_cursor.year, d_cursor.month, d_cursor.day, hh, mm)
                if dt_cand > limite_minimo:
                    slots.append(dt_cand.strftime("%Y-%m-%d %H:%M"))
                    if len(slots) >= cantidad_total:
                        break
            d_cursor += _dt.timedelta(days=1)
        return slots

    # Modo "Cada X hs (Desde mi Hora)"
    try:
        hh_ini, mm_ini = [int(x) for x in hora_inicio.strip().split(":", 1)]
    except Exception:
        hh_ini, mm_ini = 13, 0

    d_cursor = d_base
    guard = 0
    while len(slots) < cantidad_total and guard < 60:
        guard += 1
        dt_dia_ini = _dt.datetime(d_cursor.year, d_cursor.month, d_cursor.day, hh_ini, mm_ini)
        subidos_en_este_dia = 0
        for idx_en_dia in range(por_dia):
            dt_cand = dt_dia_ini + _dt.timedelta(hours=idx_en_dia * intervalo_hs)
            # Si al sumar horas se pasa al día siguiente, igual es válido y mantiene el espaciado
            if dt_cand > limite_minimo:
                cand_str = dt_cand.strftime("%Y-%m-%d %H:%M")
                if not slots or cand_str > slots[-1]:
                    slots.append(cand_str)
                    subidos_en_este_dia += 1
                    if len(slots) >= cantidad_total:
                        break
        d_cursor += _dt.timedelta(days=1)

    return slots



