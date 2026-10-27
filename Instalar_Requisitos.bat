@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================================
echo   ⚡ INSTALADOR DE DEPENDENCIAS - SHORTS STUDIO
echo ============================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python no esta instalado. Instalando Python 3.13 y FFmpeg con winget...
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [*] Instalando FFmpeg con winget...
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
)

echo [*] Instalando librerias de Python necesarias (requirements.txt)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ============================================================================
echo   [OK] ¡Todo listo! Ya puedes abrir "Shorts Studio.exe" o "Iniciar_Editor.bat"
echo ============================================================================
pause
