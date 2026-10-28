# -*- coding: utf-8 -*-
import asyncio
import json
import math
import os
import random
import re
import subprocess
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from .config import (
    TEMP_DIR, SFX_DIR, WIN_NO_WINDOW, WIN_STARTUPINFO,
    ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, EDGE_VOICE_DEFAULT,
    EDGE_PITCH_DEFAULT, HAS_EDGE_TTS, PalabraSubtitulo, SUBTITLE_OFFSET_SEC, VOLUMEN_VOZ_NARRADOR, _quitar_acentos
)
if HAS_EDGE_TTS:
    import edge_tts

# ==============================================================================
# 5. MOTOR DE VOZ NEURONAL Y ALINEACIÓN ACÚSTICA EXACTA
# ==============================================================================
def _peso_silabico_palabra(palabra: str) -> float:
    limpia = re.sub(r"[^a-záéíóúüñA-ZÁÉÍÓÚÜÑ0-9]", "", palabra)
    vocales = len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]+", limpia))
    peso = max(1.0, float(vocales) * 0.9 + len(limpia) * 0.12)
    if palabra.endswith((",", "...", ":", ";")):
        peso += 0.85
    elif palabra.endswith(("!", "?", ".")):
        peso += 1.10
    return peso


def detectar_limites_voz_real_wav(ruta_wav: Path) -> Tuple[float, float, float]:
    with wave.open(str(ruta_wav), "r") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        dur_total = n / float(sr)
        audio = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0

    if len(audio) == 0:
        return 0.0, dur_total, dur_total

    win = max(1, int(sr * 0.01))
    n_wins = len(audio) // win
    if n_wins < 2:
        return 0.0, dur_total, dur_total

    recorte = audio[: n_wins * win].reshape(n_wins, win)
    rms = np.sqrt(np.mean(recorte ** 2, axis=1))
    umbral = max(0.012, float(np.max(rms)) * 0.06)

    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        return 0.0, dur_total, dur_total

    ini_seg = max(0.0, float(activos[0]) * 0.01 - 0.02)
    fin_seg = min(dur_total, float(activos[-1] + 1) * 0.01 + 0.03)
    return ini_seg, fin_seg, dur_total


def alinear_palabras_con_onda_real(
    texto: str,
    ruta_wav: Path,
    palabras_edge: List[PalabraSubtitulo],
) -> List[PalabraSubtitulo]:
    ini_voz, fin_voz, dur_total = detectar_limites_voz_real_wav(ruta_wav)
    dur_hablada = max(0.25, fin_voz - ini_voz)

    if palabras_edge:
        primero = palabras_edge[0].inicio_seg
        ultimo = palabras_edge[-1].fin_seg
        rango_raw = max(0.1, ultimo - primero)
        escala = dur_hablada / rango_raw
        calibradas: List[PalabraSubtitulo] = []
        for p in palabras_edge:
            t0 = ini_voz + (p.inicio_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t1 = ini_voz + (p.fin_seg - primero) * escala + SUBTITLE_OFFSET_SEC
            t0 = max(0.0, t0)
            t1 = max(t0 + 0.08, min(dur_total, t1))
            if calibradas and t0 > calibradas[-1].fin_seg and (t0 - calibradas[-1].fin_seg) < 0.18:
                calibradas[-1].fin_seg = t0
            calibradas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
        return calibradas

    tokens = texto.split()
    if not tokens:
        return []
    pesos = [_peso_silabico_palabra(tok) for tok in tokens]
    suma_pesos = sum(pesos)
    cursor = ini_voz
    resultado: List[PalabraSubtitulo] = []
    for tok, peso in zip(tokens, pesos):
        dur_p = (peso / suma_pesos) * dur_hablada
        t0 = max(0.0, cursor + SUBTITLE_OFFSET_SEC)
        t1 = min(dur_total, cursor + dur_p + SUBTITLE_OFFSET_SEC)
        destaque = tok.startswith("*") and tok.endswith("*")
        tok_limpio = tok.strip("*")
        resultado.append(
            PalabraSubtitulo(
                texto=tok_limpio,
                inicio_seg=t0,
                fin_seg=max(t0 + 0.08, t1),
                forzar_destaque=destaque,
            )
        )
        cursor += dur_p
    return resultado


_REEMPLAZOS_FONETICOS_TTS = [
    (r"\*", ""),
    (r"\bPCs\b", "PC"),
    (r"\bpcs\b", "PC"),
    (r"\bRoblox\b", "Róblox"),
    (r"\broblox\b", "Róblox"),
    (r"\bRobux\b", "Róbux"),
    (r"\brobux\b", "Róbux"),
    (r"\bShorts\b", "Shórts"),
    (r"\bshorts\b", "shórts"),
    (r"\bShort\b", "Shórt"),
    (r"\bshort\b", "shórt"),
    (r"\bpros\b", "prós"),
    (r"\bPros\b", "Prós"),
    (r"\bPROS\b", "PRÓS"),
    (r"\bpro\b", "pró"),
    (r"\bPro\b", "Pró"),
    (r"\bPRO\b", "PRÓ"),
    (r"\bsuvs\b", "súbs"),
    (r"\bsubs\b", "súbs"),
]

_PALABRAS_HYPE_YOUTUBER = {
    "mira", "mirá", "miren", "increíble", "imposible", "locura", "pero", "ahora",
    "suscríbete", "suscribite", "comenta", "comentá", "like", "secreto", "nunca",
    "jamás", "épico", "épica", "ganar", "perder", "cuidado", "rápido", "estafa",
}


def _normalizar_fonetica_youtuber(texto: str) -> str:
    res = texto
    for patron, reemplazo in _REEMPLAZOS_FONETICOS_TTS:
        res = re.sub(patron, reemplazo, res)
    return res


def _dividir_clausulas_expresivas(texto: str) -> List[str]:
    partes = re.split(r"(?<=[!?.])\s+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


def _prosodia_dinamica_clausula(
    clausula: str,
    idx: int,
    total: int,
    palabras_por_seg_objetivo: Optional[float] = None,
) -> Tuple[str, str, str, float]:
    es_exclamacion = "!" in clausula or "¡" in clausula
    es_pregunta = "?" in clausula or "¿" in clausula
    palabras_low = set(re.findall(r"[a-záéíóúüñ]+", clausula.lower()))
    tiene_hype = bool(palabras_low & _PALABRAS_HYPE_YOUTUBER)
    pitch = EDGE_PITCH_DEFAULT

    # Adaptamos la velocidad base de síntesis al número de palabras que debe decir en este tramo real del video.
    # Las pausas entre oraciones se mantienen mínimas (narración de corrido, sin huecos de silencio).
    ajuste_vel = 0
    pausa_extra = 0.0
    if palabras_por_seg_objetivo is not None:
        if palabras_por_seg_objetivo < 2.6:
            ajuste_vel = -10
        elif palabras_por_seg_objetivo < 3.2:
            ajuste_vel = -5
        elif palabras_por_seg_objetivo > 3.9:
            # Si la IA escribió una línea larga para este bloque, aumentamos el ritmo proporcionalmente
            ajuste_vel = min(42, int(round((palabras_por_seg_objetivo - 3.5) * 12.0)))
            pausa_extra = -0.01

    if es_exclamacion:
        if idx == 0:
            r_num = max(0, 14 + ajuste_vel)
            return f"+{r_num}%", pitch, "+8%", max(0.015, 0.030 + pausa_extra)
        elif idx == total - 1:
            r_num = max(0, 15 + ajuste_vel)
            return f"+{r_num}%", pitch, "+10%", max(0.015, 0.030 + pausa_extra)
        else:
            r_num = max(0, 16 + ajuste_vel)
            return f"+{r_num}%", pitch, "+6%", max(0.015, 0.030 + pausa_extra)
    elif es_pregunta:
        r_num = max(0, 13 + ajuste_vel)
        return f"+{r_num}%", pitch, "+6%", max(0.015, 0.035 + pausa_extra)
    else:
        base_n = 13 if tiene_hype else 11
        r_num = max(0, base_n + ajuste_vel)
        return f"+{r_num}%", pitch, "+0%", max(0.015, 0.035 + pausa_extra)


def _recortar_silencio_clausula_pcm(
    pcm_float: np.ndarray,
    sr: int = 44100,
) -> Tuple[np.ndarray, float, float]:
    if len(pcm_float) == 0:
        return pcm_float, 0.0, 0.0
    win = max(1, int(sr * 0.005))
    n_wins = len(pcm_float) // win
    if n_wins < 2:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    rms = np.sqrt(np.mean(pcm_float[: n_wins * win].reshape(n_wins, win) ** 2, axis=1))
    umbral = max(0.007, float(np.max(rms)) * 0.03)
    activos = np.where(rms > umbral)[0]
    if len(activos) == 0:
        dur = len(pcm_float) / float(sr)
        return pcm_float, 0.0, dur

    pad_ini = int(sr * 0.016)
    pad_fin = int(sr * 0.024)
    i0 = max(0, int(activos[0]) * win - pad_ini)
    i1 = min(len(pcm_float), int(activos[-1] + 1) * win + pad_fin)
    recortado = pcm_float[i0:i1].copy()

    fade_len = min(int(sr * 0.008), len(recortado) // 4)
    if fade_len > 1:
        recortado[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        recortado[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    return recortado, i0 / float(sr), len(recortado) / float(sr)


def _construir_cadena_atempo(factor: float) -> str:
    """
    Construye filtros `atempo` encadenados para FFmpeg manteniendo el tono natural de la voz.
    """
    f = float(np.clip(factor, 0.55, 3.2))
    if abs(f - 1.0) <= 0.012:
        return ""
    partes: List[str] = []
    while f > 2.0:
        partes.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        partes.append("atempo=0.5")
        f /= 0.5
    partes.append(f"atempo={f:.4f}")
    return ",".join(partes) + ","


def masterizar_voz_estudio_ffmpeg(
    ruta_entrada: Path,
    ruta_wav_salida: Path,
    factor_atempo: float = 1.0,
) -> None:
    prefijo_tempo = _construir_cadena_atempo(factor_atempo)
    filtro_audio = (
        f"{prefijo_tempo}"
        "highpass=f=80,"
        "equalizer=f=135:width_type=o:width=1.1:g=2.4,"
        "equalizer=f=320:width_type=o:width=1.2:g=-1.2,"
        "equalizer=f=3150:width_type=o:width=1.3:g=-2.2,"
        "equalizer=f=5200:width_type=o:width=1.5:g=1.6,"
        "treble=g=2.0:f=8200,"
        "acompressor=threshold=-19dB:ratio=2.5:attack=10:release=110:makeup=5.2dB,"
        "alimiter=limit=0.98"
    )
    res = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(ruta_entrada),
            "-af", filtro_audio,
            "-ar", "44100", "-ac", "1",
            str(ruta_wav_salida),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=WIN_NO_WINDOW,
        startupinfo=WIN_STARTUPINFO,
    )
    if res.returncode != 0 or not ruta_wav_salida.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(ruta_entrada), "-ar", "44100", "-ac", "1", str(ruta_wav_salida)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=WIN_NO_WINDOW,
            startupinfo=WIN_STARTUPINFO,
        )


def intentar_voz_elevenlabs(texto: str, ruta_mp3: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = json.dumps({
        "text": _normalizar_fonetica_youtuber(texto),
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.32,
            "similarity_boost": 0.82,
            "style": 0.68,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            datos = resp.read()
            if len(datos) > 1000:
                ruta_mp3.write_bytes(datos)
                return True
    except Exception:
        pass
    return False


async def generar_voz_y_timestamps_segmento(
    texto: str,
    ruta_audio_salida: Path,
    voz_edge: str = EDGE_VOICE_DEFAULT,
    dur_objetivo_seg: Optional[float] = None,
) -> Tuple[float, List[PalabraSubtitulo], float, float]:
    palabras_raw: List[PalabraSubtitulo] = []
    genero_audio = False
    ruta_wav = ruta_audio_salida.with_suffix(".wav")
    if ruta_audio_salida.exists():
        ruta_audio_salida.unlink()
    if ruta_wav.exists():
        ruta_wav.unlink()

    if ELEVENLABS_API_KEY:
        genero_audio = intentar_voz_elevenlabs(texto, ruta_audio_salida)
        if genero_audio:
            masterizar_voz_estudio_ffmpeg(ruta_audio_salida, ruta_wav)

    if not genero_audio and HAS_EDGE_TTS:
        try:
            clausulas_orig = _dividir_clausulas_expresivas(texto)
            if not clausulas_orig:
                clausulas_orig = [texto.strip()]

            total_palabras_seg = max(1, len(texto.split()))
            pps_obj = (total_palabras_seg / dur_objetivo_seg) if (dur_objetivo_seg and dur_objetivo_seg > 0.5) else None

            sr = 44100
            bloques_pcm: List[np.ndarray] = []
            cursor_seg = 0.0

            for c_idx, cl_orig in enumerate(clausulas_orig):
                cl_tts = _normalizar_fonetica_youtuber(cl_orig)
                rate_c, pitch_c, vol_c, pausa_post = _prosodia_dinamica_clausula(
                    cl_orig, c_idx, len(clausulas_orig), palabras_por_seg_objetivo=pps_obj
                )
                tmp_mp3 = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.mp3"
                tmp_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_c{c_idx}.wav"
                palabras_clausula: List[PalabraSubtitulo] = []

                # Nota crítica: En edge_tts >= 7.3 con voces Multilingual (como GiuseppeMultilingualNeural),
                # pasar un rate != "+0%" en SSML junto con boundary="WordBoundary" hace que el servidor de
                # Microsoft cierre el stream con NoAudioReceived (0 bytes). Por eso sintetizamos siempre a
                # rate="+0%" en Edge-TTS y aplicamos toda la aceleración exacta con el filtro `atempo` de
                # FFmpeg en `masterizar_voz_estudio_ffmpeg`, logrando 100% de fiabilidad sin perder ninguna frase.
                intentos_tts = [
                    (voz_edge, "+0%", pitch_c, vol_c, True),
                    (voz_edge, "+0%", "+0Hz", "+0%", False),
                    ("es-AR-TomasNeural", "+0%", "+0Hz", "+0%", True),
                    ("es-MX-JorgeNeural", "+0%", "+0Hz", "+0%", False),
                ]
                for v_try, r_try, p_try, vol_try, usar_wb in intentos_tts:
                    palabras_clausula = []
                    if tmp_mp3.exists():
                        try:
                            tmp_mp3.unlink()
                        except OSError:
                            pass
                    try:
                        if usar_wb:
                            communicate = edge_tts.Communicate(
                                cl_tts,
                                v_try,
                                rate=r_try,
                                pitch=p_try,
                                volume=vol_try,
                                boundary="WordBoundary",
                            )
                        else:
                            communicate = edge_tts.Communicate(
                                cl_tts,
                                v_try,
                                rate=r_try,
                                pitch=p_try,
                                volume=vol_try,
                            )
                        with open(tmp_mp3, "wb") as audio_file:
                            async for chunk in communicate.stream():
                                ctype = chunk.get("type")
                                if ctype == "audio":
                                    audio_file.write(chunk["data"])
                                elif ctype == "WordBoundary":
                                    ini = chunk["offset"] / 10_000_000.0
                                    dur = chunk["duration"] / 10_000_000.0
                                    palabras_clausula.append(
                                        PalabraSubtitulo(
                                            texto=chunk["text"],
                                            inicio_seg=ini,
                                            fin_seg=ini + max(dur, 0.08),
                                        )
                                    )
                        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 200:
                            break
                    except Exception as err_clause:
                        print(f"[!] Reintentando cláusula TTS ({v_try}): {err_clause}")
                        continue

                if tmp_mp3.exists() and tmp_mp3.stat().st_size > 0:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", str(sr), "-ac", "1", str(tmp_wav)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        creationflags=WIN_NO_WINDOW,
                        startupinfo=WIN_STARTUPINFO,
                    )
                if tmp_wav.exists() and tmp_wav.stat().st_size > 0:
                    with wave.open(str(tmp_wav), "r") as wf_c:
                        pcm_c = (
                            np.frombuffer(wf_c.readframes(wf_c.getnframes()), dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )
                    pcm_rec, offset_rec, dur_rec = _recortar_silencio_clausula_pcm(pcm_c, sr)

                    if "!" in cl_orig or "¡" in cl_orig:
                        progreso_c = np.linspace(0.0, 1.0, len(pcm_rec), dtype=np.float32)
                        env_punch = 1.0 + 0.09 * np.exp(-progreso_c * 3.2) + 0.05 * np.sin(progreso_c * math.pi)
                        pcm_rec = pcm_rec * env_punch

                    tokens_orig = cl_orig.split()
                    if palabras_clausula:
                        t_first = palabras_clausula[0].inicio_seg
                        t_last = palabras_clausula[-1].fin_seg
                        span_raw = max(0.08, t_last - t_first)
                        escala_c = max(0.10, dur_rec - 0.02) / span_raw
                        for w_i, p_w in enumerate(palabras_clausula):
                            tok_o = tokens_orig[w_i] if w_i < len(tokens_orig) else p_w.texto
                            destaque = tok_o.startswith("*") and tok_o.endswith("*")
                            txt_mostrar = tok_o.strip("*")
                            t0 = cursor_seg + max(0.0, (p_w.inicio_seg - t_first) * escala_c)
                            t1 = cursor_seg + min(dur_rec, max(0.08, (p_w.fin_seg - t_first) * escala_c))
                            palabras_raw.append(
                                PalabraSubtitulo(
                                    texto=txt_mostrar,
                                    inicio_seg=t0,
                                    fin_seg=max(t0 + 0.07, t1),
                                    forzar_destaque=destaque,
                                )
                            )

                    bloques_pcm.append(pcm_rec)
                    cursor_seg += dur_rec

                    if c_idx < len(clausulas_orig) - 1:
                        bloques_pcm.append(np.zeros(int(sr * pausa_post), dtype=np.float32))
                        cursor_seg += pausa_post

                for f_tmp in (tmp_mp3, tmp_wav):
                    if f_tmp.exists():
                        try:
                            f_tmp.unlink()
                        except OSError:
                            pass

            if bloques_pcm:
                audio_crudo = np.clip(np.concatenate(bloques_pcm), -0.98, 0.98)
                dur_cruda = len(audio_crudo) / float(sr)

                # Ajuste exacto de tempo (sin cambiar el tono) para que la voz LLENE su tramo real de video
                # de corrido (sin huecos de silencio al final) y nunca lo exceda.
                # Ritmo dinámico, rápido y enérgico para YouTube Shorts:
                # Base de 1.12x para que nunca hable lento. Si el texto necesita más espacio se acelera hasta 1.28x.
                factor_atempo = 1.12
                if dur_objetivo_seg and dur_objetivo_seg > 0.5 and dur_cruda > 0.15:
                    dur_ideal_voz = max(0.35, dur_objetivo_seg - 0.06)
                    factor_atempo = float(np.clip(dur_cruda / dur_ideal_voz, 1.12, 1.28))

                if abs(factor_atempo - 1.0) > 0.012 and palabras_raw:
                    for p_w in palabras_raw:
                        p_w.inicio_seg /= factor_atempo
                        p_w.fin_seg /= factor_atempo

                ruta_crudo_wav = ruta_audio_salida.parent / f"{ruta_audio_salida.stem}_raw.wav"
                with wave.open(str(ruta_crudo_wav), "w") as wf_raw:
                    wf_raw.setnchannels(1)
                    wf_raw.setsampwidth(2)
                    wf_raw.setframerate(sr)
                    wf_raw.writeframes((audio_crudo * 32767).astype(np.int16).tobytes())
                masterizar_voz_estudio_ffmpeg(ruta_crudo_wav, ruta_wav, factor_atempo=factor_atempo)
                if ruta_crudo_wav.exists():
                    try:
                        ruta_crudo_wav.unlink()
                    except OSError:
                        pass
                genero_audio = ruta_wav.exists() and ruta_wav.stat().st_size > 0
        except Exception as e:
            print(f"[!] Error en Edge-TTS: {e}")

    if not ruta_wav.exists() or ruta_wav.stat().st_size == 0:
        # Silencio limpio de emergencia (NUNCA generar tonos/zumbidos graves de 195Hz)
        tokens = texto.split()
        dur_estimada = dur_objetivo_seg if (dur_objetivo_seg and dur_objetivo_seg > 0.5) else max(1.8, len(tokens) * 0.28)
        sr = 44100
        pcm = np.zeros(int(sr * dur_estimada), dtype=np.int16)
        with wave.open(str(ruta_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())

    with wave.open(str(ruta_wav), "r") as wf:
        duracion_real = wf.getnframes() / float(wf.getframerate())

    ini_voz, fin_voz, _ = detectar_limites_voz_real_wav(ruta_wav)
    if palabras_raw and not ELEVENLABS_API_KEY:
        palabras_alineadas: List[PalabraSubtitulo] = []
        for p in palabras_raw:
            t0 = max(0.0, p.inicio_seg + SUBTITLE_OFFSET_SEC)
            t1 = min(duracion_real, max(t0 + 0.07, p.fin_seg + SUBTITLE_OFFSET_SEC))
            if palabras_alineadas and t0 > palabras_alineadas[-1].fin_seg and (t0 - palabras_alineadas[-1].fin_seg) < 0.16:
                palabras_alineadas[-1].fin_seg = t0
            palabras_alineadas.append(
                PalabraSubtitulo(
                    texto=p.texto,
                    inicio_seg=t0,
                    fin_seg=t1,
                    forzar_destaque=p.forzar_destaque,
                )
            )
    else:
        palabras_alineadas = alinear_palabras_con_onda_real(texto, ruta_wav, palabras_raw)

    return duracion_real, palabras_alineadas, ini_voz, fin_voz




# ==============================================================================
# 8. GESTOR DE AUDIO/SFX (.MP3/.WAV) Y PIPELINE DE RENDERIZADO POR SEGMENTO
# ==============================================================================
class GestorAudioSFX:
    """
    Decodifica y cachea todos los archivos de `sfx/` (.mp3, .MP3, .wav, .ogg) usando FFmpeg,
    recorta silencios muertos al inicio/final para sincronización instantánea y normaliza
    sus picos para una mezcla profesional junto a la voz IA.
    """

    def __init__(self, sfx_dir: Path, sr: int = 44100):
        self.sfx_dir = sfx_dir
        self.sr = sr
        self.cache_pcm: Dict[str, np.ndarray] = {}
        self._cargar_todos_los_sfx()

    def _cargar_todos_los_sfx(self) -> None:
        if not self.sfx_dir.exists():
            return
        for archivo in sorted(self.sfx_dir.glob("*.*")):
            if archivo.suffix.lower() not in (".mp3", ".wav", ".ogg", ".m4a"):
                continue
            clave = _quitar_acentos(archivo.stem.strip().lower())
            try:
                res = subprocess.run(
                    [
                        "ffmpeg", "-v", "error",
                        "-i", str(archivo),
                        "-f", "s16le", "-ac", "1", "-ar", str(self.sr), "-",
                    ],
                    capture_output=True,
                    check=False,
                    creationflags=WIN_NO_WINDOW,
                    startupinfo=WIN_STARTUPINFO,
                )
                if res.returncode != 0 or len(res.stdout) < 100:
                    continue
                pcm = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                peak = float(np.max(np.abs(pcm)))
                if peak < 1e-4:
                    continue

                # Recortar silencio muerto inicial y final (ej. xp_Error o riser_suction)
                umbral = max(0.008, peak * 0.045)
                activos = np.where(np.abs(pcm) > umbral)[0]
                if len(activos) > 0:
                    pad_ini = int(self.sr * 0.012)
                    pad_fin = int(self.sr * 0.040)
                    i0 = max(0, int(activos[0]) - pad_ini)
                    i1 = min(len(pcm), int(activos[-1]) + pad_fin)
                    pcm = pcm[i0:i1].copy()

                # Normalizar pico a 0.85 para consistencia entre efectos
                pcm = pcm * (0.85 / peak)

                # Fade-out suave en los últimos 25ms
                fade_n = min(int(self.sr * 0.025), len(pcm) // 4)
                if fade_n > 2:
                    pcm[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

                self.cache_pcm[clave] = pcm
            except Exception:
                continue

        print(f"[*] Efectos de sonido (SFX) cargados ({len(self.cache_pcm)}): {sorted(self.cache_pcm.keys())}")

    def obtener_pcm(self, nombre_sfx: str) -> Optional[np.ndarray]:
        clave = _quitar_acentos(nombre_sfx.strip().lower())
        return self.cache_pcm.get(clave)

    def mezclar_audio_segmento(
        self,
        ruta_voz_wav: Path,
        duracion_total_seg: float,
        sfx_lista: List[str],
        tiene_emoji_o_flecha: bool,
        ruta_salida_wav: Path,
    ) -> None:
        n_total = int(round(duracion_total_seg * self.sr))
        mezcla = np.zeros(n_total, dtype=np.float32)

        with wave.open(str(ruta_voz_wav), "r") as wf:
            voz_pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            n_copy = min(n_total, len(voz_pcm))
            voz_fuerte = np.tanh(voz_pcm[:n_copy] * VOLUMEN_VOZ_NARRADOR)
            mezcla[:n_copy] += voz_fuerte

        # Superponer los SFX solicitados (con ligero escalonamiento si hay más de uno)
        for idx_s, nombre_sfx in enumerate(sfx_lista):
            sfx_pcm = self.obtener_pcm(nombre_sfx)
            if sfx_pcm is None or len(sfx_pcm) == 0:
                continue
            offset_samples = int(round(idx_s * 0.14 * self.sr))
            if offset_samples >= n_total:
                continue
            n_disp = min(n_total - offset_samples, len(sfx_pcm))
            # Limitar duración máxima de SFX muy largos para no ensuciar toda la frase
            max_samples_sfx = int(round(2.4 * self.sr))
            n_usar = min(n_disp, max_samples_sfx)
            bloque_sfx = sfx_pcm[:n_usar].copy()
            if n_usar < len(sfx_pcm) and n_usar > 400:
                bloque_sfx[-400:] *= np.linspace(1.0, 0.0, 400, dtype=np.float32)

            ganancia_sfx = 0.34 if idx_s == 0 else 0.28
            mezcla[offset_samples : offset_samples + n_usar] += bloque_sfx * ganancia_sfx

        # Si aparece un emoji o flecha y no se pidió 'pop', añadir un sutil pop acústico a los 60ms
        if tiene_emoji_o_flecha and "pop" not in sfx_lista:
            pop_pcm = self.obtener_pcm("pop")
            if pop_pcm is not None:
                off_pop = int(round(0.06 * self.sr))
                n_pop = min(max(0, n_total - off_pop), len(pop_pcm))
                if n_pop > 0:
                    mezcla[off_pop : off_pop + n_pop] += pop_pcm[:n_pop] * 0.18

        mezcla = np.clip(mezcla, -0.98, 0.98)
        pcm_out = (mezcla * 32767).astype(np.int16)
        with wave.open(str(ruta_salida_wav), "w") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(self.sr)
            wf_out.writeframes(pcm_out.tobytes())

