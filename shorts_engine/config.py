# -*- coding: utf-8 -*-
import os
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
WIN_STARTUPINFO = None
if sys.platform == "win32":
    WIN_STARTUPINFO = subprocess.STARTUPINFO()
    WIN_STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    WIN_STARTUPINFO.wShowWindow = subprocess.SW_HIDE

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

WIDTH = 1080
HEIGHT = 1920
FPS = 60
CPU_THREADS = max(4, (os.cpu_count() or 8))

MODO_ENCUADRE_DEFAULT = "full"
VOLUMEN_VOZ_NARRADOR = 1.48
VOLUMEN_AUDIO_VIDEO_ORIGINAL = 0.0
VOLUMEN_MUSICA_FONDO = 0.12
SUBTITLE_OFFSET_SEC = -0.02
DURACION_CALLOUTS_DEFAULT = 1.8

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

VOCES_DISPONIBLES: Dict[str, str] = {
    "Giuseppe (YouTuber Hype - Recomendada)": "it-IT-GiuseppeMultilingualNeural",
    "Tomás (Argentina Dinámico)": "es-AR-TomasNeural",
    "Jorge (México Dinámico)": "es-MX-JorgeNeural",
    "Álvaro (España Intenso)": "es-ES-AlvaroNeural",
    "Dalia (Femenina Expresiva)": "es-MX-DaliaNeural",
}
EDGE_VOICE_DEFAULT = "it-IT-GiuseppeMultilingualNeural"
EDGE_PITCH_DEFAULT = "+0Hz"

BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def _resolver_carpeta_asset(nombre: str) -> Path:
    en_assets = ASSETS_DIR / nombre
    if en_assets.exists():
        return en_assets
    directa = BASE_DIR / nombre
    if directa.exists():
        return directa
    en_assets.mkdir(parents=True, exist_ok=True)
    return en_assets

EMOJIS_DIR = _resolver_carpeta_asset("emojis")
FONTS_DIR = _resolver_carpeta_asset("fonts")
FOTOS_DIR = _resolver_carpeta_asset("fotos")
SFX_DIR = _resolver_carpeta_asset("sfx")
MUSICA_DIR = _resolver_carpeta_asset("musica")
TEMP_DIR = BASE_DIR / "temp_build"
OUTPUT_DIR = BASE_DIR / "output_shorts"

DEFAULT_VIDEO_INPUT = BASE_DIR / "video_input.mp4"
DEFAULT_GUION_TXT = BASE_DIR / "guion_video.txt"
PROMPT_IA_PATH = BASE_DIR / "PROMPT_PARA_IA_GUIONES.txt"
PROMPT_COMPACTO_PATH = BASE_DIR / "PROMPT_ARGON_COMPACTO.txt"

# Constantes de estilos visuales CustomTkinter
BG_DARK = "#0a0d14"
CARD_BG = "#131825"
CARD_BORDER = "#1f2637"
PURPLE_MAIN = "#7c3aed"
CYAN_ACCENT = "#06b6d4"
GREEN_ACCENT = "#10b981"
TEXT_MAIN = "#f1f5f9"
TEXT_MUTED = "#94a3b8"
INPUT_BG = "#0f1420"
MESES_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}

@dataclass
class SegmentoVideoGuion:
    id_segmento: str
    texto_voz: str
    efecto_visual: str = "ninguno"
    t_inicio_video: Optional[float] = None
    t_fin_video: Optional[float] = None
    pausa_final_seg: float = 0.16
    sfx_lista: List[str] = field(default_factory=list)
    emoji: Optional[str] = None
    posicion_emoji: str = "auto"
    flecha: Optional[str] = None
    circulo: Optional[str] = None
    tamano_circulo: str = "medio"
    track_flecha_activo: bool = False
    track_circulo_activo: bool = False
    callout_flecha: Optional[str] = None
    callout_circulo: Optional[str] = None
    tiene_circulo: bool = False
    tiene_flecha: bool = False
    tiene_emoji: bool = False
    tiene_foto: bool = False
    emoji_nombre: Optional[str] = None
    foto_nombre: Optional[str] = None

    def __post_init__(self) -> None:
        if self.flecha:
            self.track_flecha_activo = True
            self.tiene_flecha = True
            if not self.callout_flecha:
                self.callout_flecha = self.flecha
        if self.circulo:
            self.track_circulo_activo = True
            self.tiene_circulo = True
            if not self.callout_circulo:
                self.callout_circulo = self.circulo
        if self.emoji:
            self.tiene_emoji = True
            if not self.emoji_nombre:
                self.emoji_nombre = self.emoji

@dataclass
class ConfigGuion:
    titulo_superior: str = ""
    titulo_youtube: str = ""
    descripcion_youtube: str = ""
    estado_publicacion: str = "privado"
    schedule: Optional[str] = None
    para_ninos: bool = False
    tags_youtube: List[str] = field(default_factory=list)
    modo_encuadre: str = MODO_ENCUADRE_DEFAULT
    voz_narrador: str = EDGE_VOICE_DEFAULT
    archivo_salida: Optional[str] = None
    volumen_video_original: float = VOLUMEN_AUDIO_VIDEO_ORIGINAL
    volumen_musica: float = VOLUMEN_MUSICA_FONDO
    tono_video: str = "fondo"
    duracion_callouts: float = DURACION_CALLOUTS_DEFAULT
    palabras_verdes_extra: Set[str] = field(default_factory=set)
    palabras_rojas_extra: Set[str] = field(default_factory=set)
    palabras_cian_extra: Set[str] = field(default_factory=set)
    segmentos: List[SegmentoVideoGuion] = field(default_factory=list)

@dataclass
class PalabraSubtitulo:
    texto: str
    inicio_seg: float
    fin_seg: float
    forzar_destaque: bool = False

HORARIOS_PICO_OPTIMOS: Dict[int, List[str]] = {
    1: ["19:00"],
    2: ["13:00", "20:00"],
    3: ["12:30", "17:30", "21:00"],
    4: ["11:00", "15:00", "18:30", "21:30"],
    5: ["10:00", "13:00", "16:00", "19:00", "22:00"],
    6: ["09:30", "12:00", "14:30", "17:00", "19:30", "22:00"],
}


def _quitar_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
