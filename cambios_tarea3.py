ARCHIVO = "shorts_engine/video_render.py"
CAMBIOS = [
    (
        """    datos_segmentos = []
    archivos_audio_seg: List[Path] = []
    n_segs = max(1, len(config.segmentos))

    # 2. Generar voz IA ajustada a la duración real 1.0x de cada segmento, subtítulos y mezcla de SFX
    nom_voz_corta = config.voz_narrador.split("-")[-1].replace("Neural", "")
    for idx, (seg, (total_frames_seg, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales)):
        sfx_label = f" + SFX ({'+'.join(seg.sfx_lista)})" if seg.sfx_lista else ""
        _notificar_prog(
            0.05 + 0.30 * (idx / float(n_segs)),
            f"Síntesis vocal ({nom_voz_corta}){sfx_label} (bloque {idx + 1}/{n_segs})...",
        )
        sfx_str = "+".join(seg.sfx_lista) if seg.sfx_lista else "-"
        info_seg = (
            f"{seg.t_inicio_video:.1f}s-{seg.t_fin_video:.1f}s | efecto={seg.efecto_visual} | "
            f"sfx={sfx_str} | emoji={seg.emoji or '-'} | flecha={seg.flecha or '-'} | circulo={seg.circulo or '-'}"
        )
        print(f"[+] Segmento [{idx + 1}/{len(config.segmentos)}] ({info_seg}): {seg.texto_voz}")

        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        dur_voz, palabras_sub, ini_voz, fin_voz = await generar_voz_y_timestamps_segmento(
            seg.texto_voz,
            ruta_mp3,
            voz_edge=config.voz_narrador,
            dur_objetivo_seg=dur_seg_exacta,
        )

        ruta_voz_wav = ruta_mp3.with_suffix(".wav")
        rms_env = calcular_envolvente_rms(ruta_voz_wav, FPS)

        ruta_mix_wav = TEMP_DIR / f"{seg.id_segmento}_mix.wav"
        tiene_overlay_pop = bool(seg.emoji or seg.flecha or seg.circulo)
        gestor_sfx.mezclar_audio_segmento(
            ruta_voz_wav=ruta_voz_wav,
            duracion_total_seg=dur_seg_exacta,
            sfx_lista=seg.sfx_lista,
            tiene_emoji_o_flecha=tiene_overlay_pop,
            ruta_salida_wav=ruta_mix_wav,
            permitir_cola_voz=(idx == len(config.segmentos) - 1),
        )
        archivos_audio_seg.append(ruta_mix_wav)
        datos_segmentos.append([seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env])""",
        """    datos_segmentos = []
    archivos_audio_seg: List[Path] = []
    n_segs = max(1, len(config.segmentos))

    # 2. Generar voz IA en PARALELO para todos los segmentos (asyncio.gather)
    # Esto reduce el tiempo de TTS de ~12s en serie a ~2s en paralelo.
    nom_voz_corta = config.voz_narrador.split("-")[-1].replace("Neural", "")
    _notificar_prog(0.05, f"Síntesis vocal paralela ({nom_voz_corta}) para {n_segs} bloques...")

    async def _generar_voz_segmento(idx: int, seg, dur_seg_exacta: float):
        if cancelar_check and cancelar_check():
            raise InterruptedError("TTS cancelado.")
        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        sfx_str = "+".join(seg.sfx_lista) if seg.sfx_lista else "-"
        info_seg = (
            f"{seg.t_inicio_video:.1f}s-{seg.t_fin_video:.1f}s | efecto={seg.efecto_visual} | "
            f"sfx={sfx_str} | emoji={seg.emoji or '-'} | flecha={seg.flecha or '-'} | circulo={seg.circulo or '-'}"
        )
        print(f"[+] TTS [{idx + 1}/{n_segs}] ({info_seg}): {seg.texto_voz}")
        dur_voz, palabras_sub, ini_voz, fin_voz = await generar_voz_y_timestamps_segmento(
            seg.texto_voz,
            ruta_mp3,
            voz_edge=config.voz_narrador,
            dur_objetivo_seg=dur_seg_exacta,
        )
        return idx, palabras_sub

    # Lanzar todos los TTS en paralelo
    tareas_tts = [
        _generar_voz_segmento(idx, seg, dur_seg_exacta)
        for idx, (seg, (_, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales))
    ]
    resultados_tts = await asyncio.gather(*tareas_tts)
    # resultados_tts: lista de (idx, palabras_sub) ordenada por asyncio.gather (misma que la lista original)
    palabras_por_seg = {idx: palabras for idx, palabras in resultados_tts}

    # Mezclar SFX en serie (sin latencia de red) y armar datos_segmentos
    for idx, (seg, (total_frames_seg, dur_seg_exacta)) in enumerate(zip(config.segmentos, tiempos_reales)):
        if cancelar_check and cancelar_check():
            raise InterruptedError("Edición cancelada por el usuario.")
        _notificar_prog(
            0.05 + 0.30 * (idx / float(n_segs)),
            f"Mezcla SFX (bloque {idx + 1}/{n_segs})...",
        )
        palabras_sub = palabras_por_seg[idx]
        ruta_mp3 = TEMP_DIR / f"{seg.id_segmento}.mp3"
        ruta_voz_wav = ruta_mp3.with_suffix(".wav")
        rms_env = calcular_envolvente_rms(ruta_voz_wav, FPS)

        ruta_mix_wav = TEMP_DIR / f"{seg.id_segmento}_mix.wav"
        tiene_overlay_pop = bool(seg.emoji or seg.flecha or seg.circulo)
        gestor_sfx.mezclar_audio_segmento(
            ruta_voz_wav=ruta_voz_wav,
            duracion_total_seg=dur_seg_exacta,
            sfx_lista=seg.sfx_lista,
            tiene_emoji_o_flecha=tiene_overlay_pop,
            ruta_salida_wav=ruta_mix_wav,
            permitir_cola_voz=(idx == len(config.segmentos) - 1),
        )
        archivos_audio_seg.append(ruta_mix_wav)
        datos_segmentos.append([seg, total_frames_seg, dur_seg_exacta, palabras_sub, rms_env])""",
    ),
]
