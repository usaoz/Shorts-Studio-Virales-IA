# ⚡ Shorts Studio — Piloto Automático de Shorts Virales con IA (60 FPS)

Aplicación de escritorio en Python (`CustomTkinter`) que automatiza de punta a punta la creación, edición y programación inteligente de **YouTube Shorts virales**:
- **Pool de Canales Fuente**: Escanea canales de YouTube en busca de Shorts virales según filtro de vistas (`100K+`, `500K+`, `1M+`, `5M+`) sin repetir videos ya usados.
- **Cerebro Multimodal con Gemini / Argon 4**: Analiza el video completo en movimiento + mosaico de cuadros y genera automáticamente el título viral, descripción, hashtags, efectos de cámara, sonidos y guion narrado continuo.
- **Modo Manual / Personalizado**: Permite ver los links de los Shorts elegidos antes de editar y personalizar el Título, Descripción o Guion de cada Reel.
- **Renderizado a 60 FPS con GPU Autodetectada**:
  - **NVIDIA (`h264_nvenc`)** — se activa automáticamente si tienes placa NVIDIA.
  - **AMD Radeon (`h264_amf`)** — se activa automáticamente si tienes placa AMD.
  - **Intel (`h264_qsv`)** o **CPU (`libx264`)** como respaldo automático.
- **Subtítulos Luminosos Neón + Emojis + Seguimiento de Objetivos (*Optical Flow*)**: Las flechas (`fotos/flecha.png`) y círculos rojos (`fotos/circulo_rojo.png`) persiguen el objeto real en pantalla.
- **Multi-Cuenta de YouTube y Pool de APIs (`+6 Shorts/día` por proyecto)**: Permite vincular múltiples canales de YouTube (con sus propios canales fuente guardados), rotar entre cuentas o grupos de cuentas, y sumar múltiples archivos `client_secrets.json` para superar el límite diario de 6 Shorts de Google Cloud.

---

## 📦 Instalación Rápida (Para probar desde el ZIP)

1. Descarga el repositorio como **ZIP** (`Code` -> `Download ZIP`) y descomprímelo en una carpeta.
2. Ejecuta **`Instalar_Requisitos.bat`** (instala automáticamente las librerías de Python de `requirements.txt` y verifica `FFmpeg`).
3. Abre la aplicación desde **`Shorts Studio.exe`** o **`Iniciar_Editor.bat`**.

---

## 🔑 Configuración Inicial (1 sola vez)

1. **Clave de IA (Gemini / Google AI Studio)**:
   - Abre **⚙️ Ajustes** dentro de la app, haz clic en **`🌐 Obtener Gratis`** ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)), pega tu API Key y dale a **Guardar**.
2. **Credenciales de Subida a YouTube (`client_secrets.json`)**:
   - En [Google Cloud Console](https://console.cloud.google.com/), crea un proyecto, habilita **YouTube Data API v3**, configura la pantalla OAuth como *Externo* (agregando tu correo en *Test users*) y crea una credencial **OAuth Client ID (Desktop App)**.
   - Descarga el archivo JSON y cárgalo tocando el botón **`+`** al lado de `🔋 Shorts restantes` arriba a la derecha en la app.
   - Toca el botón **`📺 Mi Cuenta ▾`** arriba a la derecha -> **`➕ Vincular Nueva Cuenta`** para autorizar tu canal de YouTube.
