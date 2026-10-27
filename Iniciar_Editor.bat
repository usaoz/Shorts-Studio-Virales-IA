@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Agregar rutas de Python 3.13, Scripts y FFmpeg al PATH de la sesion
set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0;%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin;%PATH%"

REM Detectar ejecutable de Python
set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD (
    where python3.13 >nul 2>nul && set "PY_CMD=python3.13"
)
if not defined PY_CMD (
    where py >nul 2>nul && set "PY_CMD=py"
)
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
    )
)

if not defined PY_CMD (
    echo [ERROR] No se pudo encontrar Python en este equipo.
    pause
    exit /b 1
)

%PY_CMD% "Editor_Shorts_Studio.py" %*
if errorlevel 1 (
    echo(
    echo [!] Ocurrio un error al ejecutar la aplicacion.
    pause
)
