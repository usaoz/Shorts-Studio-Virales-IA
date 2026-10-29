# -*- coding: utf-8 -*-
from typing import List, Tuple


def construir_filter_complex_master_ebu_r128(
    tiene_musica: bool = True,
    tiene_sfx: bool = True,
    idx_voz: int = 1,
    idx_musica: int = 2,
    idx_sfx: int = 3,
    vol_voz_base: float = 1.35,
    vol_musica_base: float = 0.22,
    vol_sfx_base: float = 0.75,
    lufs_objetivo: float = -14.0,
    true_peak_db: float = -1.0,
) -> Tuple[str, str]:
    """
    Genera la cadena `-filter_complex` de nivel estudio broadcast para FFmpeg.
    Retorna: (cadena_filter_complex, etiqueta_salida_audio) -> ej: ( "...", "[audio_master]" )
    """
    filtros: List[str] = []

    # 1. CADENA DE VOZ (Claridad + Presencia + Compresión Vocal + Split para Sidechain)
    cadena_voz = (
        f"[{idx_voz}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"highpass=f=80,"
        f"equalizer=f=3500:t=q:w=1.2:g=2.0,"
        f"acompressor=threshold=-18dB:ratio=3.2:attack=8:release=120:makeup=2.5dB,"
        f"volume={vol_voz_base:.2f}"
    )

    if tiene_musica:
        cadena_voz += ",asplit=2[voz_mix][voz_sc]"
    else:
        cadena_voz += "[voz_mix]"
    filtros.append(cadena_voz)

    # 2. CADENA DE MÚSICA CON SIDECHAIN DUCKING AUTOMÁTICO
    if tiene_musica:
        cadena_musica = (
            f"[{idx_musica}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"highpass=f=60,equalizer=f=2500:t=q:w=1.5:g=-3.0,"
            f"volume={vol_musica_base:.2f}[mus_pre];"
            f"[mus_pre][voz_sc]sidechaincompress="
            f"threshold=0.025:ratio=5.5:attack=15:release=320:level_sc=1.0[mus_ducked]"
        )
        filtros.append(cadena_musica)

    # 3. CADENA DE SFX (Control de Picos Transitorios)
    if tiene_sfx:
        cadena_sfx = (
            f"[{idx_sfx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={vol_sfx_base:.2f},"
            f"alimiter=limit=0.70:attack=3:release=40:level=disabled[sfx_clean]"
        )
        filtros.append(cadena_sfx)

    # 4. SUMA EN EL BUS MAESTRO
    entradas_mix = ["[voz_mix]"]
    if tiene_musica:
        entradas_mix.append("[mus_ducked]")
    if tiene_sfx:
        entradas_mix.append("[sfx_clean]")

    n_in = len(entradas_mix)
    if n_in > 1:
        pesos = " ".join(["1"] * n_in)
        filtros.append(
            f"{''.join(entradas_mix)}amix=inputs={n_in}:duration=first:dropout_transition=0:"
            f"weights='{pesos}':normalize=0[pre_master]"
        )
    else:
        filtros.append("[voz_mix]anull[pre_master]")

    # 5. MASTERING FINAL EBU R128 (-14.0 LUFS / -1.0 dBTP)
    filtros.append(
        f"[pre_master]loudnorm=I={lufs_objetivo:.1f}:TP={true_peak_db:.1f}:LRA=7.0:linear=true,"
        f"aresample=48000[audio_master]"
    )

    return ";".join(filtros), "[audio_master]"
