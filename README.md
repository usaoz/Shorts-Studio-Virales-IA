# Shorts Studio

*Sistema integral de automatización, edición de video vertical a 60 FPS y publicación programada para YouTube Shorts.*

---

## 🛠️ Descripción General

**Shorts Studio** es una suite de escritorio desarrollada en Python (`CustomTkinter`) orientada a la producción continua y optimización de contenido en formato vertical (9:16). Diseñado bajo una arquitectura modular y reactiva, el sistema gestiona el ciclo completo de vida del contenido: análisis audiovisual, estructuración de guion, generación de voz sincronizada, inserción de elementos visuales dinámicos, renderizado acelerado por hardware y distribución programada en múltiples canales de YouTube.

---

## 🚀 Arquitectura y Capacidades Técnicas

### 1. Renderizado Acelerado por Hardware (60 FPS)
- **Detección Automática de GPU**: Prioriza codificadores por hardware según el hardware disponible:
  - **NVIDIA**: `h264_nvenc`
  - **AMD Radeon**: `h264_amf`
  - **Intel**: `h264_qsv`
  - **CPU**: `libx264` con perfiles multihilo optimizados.
- **Color Grading y Realce Visual**: Procesamiento de fotogramas mediante transformaciones LUT matriciales en OpenCV para consistencia cromática sin penalizar los tiempos de render.

### 2. Visión Computacional y Seguimiento Dinámico
- **Object & Saliency Tracking**: Utiliza algoritmos de flujo óptico y seguimiento (`cv2.TrackerCSRT`) para mantener el foco en el sujeto u objeto principal.
- **Encuadre Dinámico (9:16)**: Modos de recorte vertical directo con seguimiento o composición con fondo difuminado (*blur*) para metraje horizontal.
- **Callouts Temporales**: Flechas y círculos de atención con sincronización exacta y posicionamiento automático basado en análisis espacial.

### 3. Síntesis Vocal y Subtitulado Karaoke
- **Alineación Temporal Precisa**: Integración de síntesis vocal con marcas de tiempo a nivel de palabra (*WordBoundary*).
- **Subtítulos Dinámicos Neón**: Renderizado pre-cacheador con realce semántico de colores (términos de impacto, éxito o alerta).
- **Audio Ducking y Limpieza de Frecuencias**: Supresión automática de silencios residuales y balance paramétrico entre voz, música incidental y efectos de sonido (SFX).

### 4. Motor de Análisis y Redacción Narrativa
- **Jerarquía de Modelos**: Soporte para modelos de lenguaje de última generación:
  - **Argon 4**: Calidad y capacidad de razonamiento profundo.
  - **Gemini 3.8 Flash & 3.6 Flash**: Alta velocidad y fidelidad narrativa.
  - **Gemini 3.5 Flash Lite & 3.1 Flash Lite**: Amplia cuota de procesamiento visual.
- **Análisis Multimodal Dual**: Ingesta de video comprimido y mosaicos de alta densidad temporal para comprensión contextual del metraje.
- **Pool Multi-Cuenta con Tolerancia a Fallos**: Rotación inmediata y transparente de API Keys ante saturación de cuota diaria (error `429 RESOURCE_EXHAUSTED`), garantizando continuidad operativa.
- **Validación Métrica de Ritmo**: Supervisión de cadencia silábica (2.8 a 3.2 palabras por segundo) para máxima retención de audiencia.

### 5. Multi-Canal y Distribución en YouTube
- **Gestión Multi-Cuenta**: Vinculación independiente de múltiples canales de YouTube con preferencias aisladas.
- **Pool de Credenciales OAuth**: Balanceo dinámico entre múltiples archivos `client_secrets.json` para superar los límites diarios de cuota de la YouTube Data API v3.
- **Programador Inteligente**: Distribución horaria automatizada en franjas pico de audiencia sin solapamiento de publicaciones.

---

## 📋 Requisitos del Sistema

- **Sistema Operativo**: Windows 10 / 11 (64-bit).
- **Python**: Versión 3.10 o superior (compatible con Python 3.13).
- **FFmpeg**: Instalado y accesible desde el `PATH` del sistema.
- **Conexión a Internet**: Requerida para llamadas a APIs de Google y subida de contenido.

---

## 📦 Instalación

1. **Clonar o descargar el proyecto**:
   ```bash
   git clone https://github.com/tu-usuario/youtube-shorts.git
   cd youtube-shorts
   ```

2. **Instalar dependencias**:
   Ejecuta el script de instalación automática:
   ```cmd
   Instalar_Requisitos.bat
   ```
   *O manualmente mediante pip:*
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar la aplicación**:
   ```cmd
   Iniciar_Editor.bat
   ```
   *O mediante Python:*
   ```bash
   python Editor_Shorts_Studio.py
   ```

---

## 🔑 Configuración de Credenciales

### 1. API Keys de Gemini / Argon 4
1. Obtén tu clave gratuita en [Google AI Studio](https://aistudio.google.com/apikey).
2. En la aplicación, ve a **Ajustes** -> **Claves API de Gemini / Argon 4**.
3. Pega una o múltiples claves (una por línea o separadas por coma). La aplicación rotará automáticamente entre cuentas si alguna alcanza el límite diario de solicitudes.

### 2. Credenciales de YouTube (OAuth 2.0)
1. En [Google Cloud Console](https://console.cloud.google.com/), habilita **YouTube Data API v3** y configura la pantalla de consentimiento OAuth.
2. Crea una credencial de tipo **OAuth Client ID (Desktop App)** y descarga el archivo JSON (`client_secrets.json`).
3. Carga el archivo en la aplicación usando el selector de credenciales en el encabezado.
4. Vincula uno o más canales desde el menú desplegable de cuenta.

---

## 📁 Estructura del Proyecto

```
YOUTUBE SHORTS/
├── Editor_Shorts_Studio.py     # Interfaz gráfica principal (CustomTkinter) y orquestador
├── motor_optimizado.py         # Subrutinas de procesamiento numérico, OpenCV y filtros
├── subir_a_youtube.py          # Autenticación OAuth, gestión de cuotas y subida a YouTube
├── shorts_engine/              # Módulos del motor de procesamiento
│   ├── config.py               # Constantes globales, rutas y dataclasses
│   ├── gemini_ia.py            # Integración de IA, jerarquía de modelos y pool multi-cuenta
│   ├── video_render.py         # Renderizado final a 60 FPS y composición de pistas
│   ├── subtitulos.py           # Generación y estilos de subtítulos dinámicos
│   ├── audio_tts.py            # Generación de voz y ajuste de tempo
│   ├── vision_tracker.py       # Detección y seguimiento de objetivos en video
│   └── youtube_manager.py      # Búsqueda, descarga (yt-dlp) y cálculo de horarios
├── assets/                     # Recursos estáticos (efectos de sonido, badges, fuentes)
├── tools/                      # Herramientas de verificación y mantenimiento de código
│   ├── verificar.py            # Suite de pruebas de compilación y arranque de GUI
│   └── mapa.py                 # Indexador de símbolos y widgets del proyecto
├── requirements.txt            # Dependencias del entorno Python
└── README.md                   # Documentación técnica del proyecto
```

---

## 🛡️ Licencia y Uso

Proyecto diseñado para automatización técnica de flujos audiovisuales. El uso de APIs de terceros (Google Gemini API y YouTube Data API) está sujeto a sus respectivos términos de servicio y políticas de uso de cuotas.
