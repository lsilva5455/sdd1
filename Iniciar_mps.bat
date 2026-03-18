@echo off
:: Desactivamos la expansión retardada al inicio para evitar errores de carga
setlocal 

:: 1. CONFIGURACIÓN BÁSICA
set "FOLDER_RAIZ=data"
set "MAX_CARPETAS=500"
set "BORRAR_CANTIDAD=50"
set "BASE_DIR=%~dp0"

:: Forzamos que el script trabaje en su propia carpeta
cd /d "%BASE_DIR%"

echo ======================================================
echo [DEBUG] INICIANDO SCRIPT - 2026-01-02
echo [DEBUG] Ubicacion: "%BASE_DIR%"
echo ======================================================

:: 2. VERIFICACIÓN DE CARPETAS
echo [1/5] Creando estructura si no existe...
if not exist "%FOLDER_RAIZ%" mkdir "%FOLDER_RAIZ%"
if not exist "%FOLDER_RAIZ%\last" mkdir "%FOLDER_RAIZ%\last"
if not exist "%FOLDER_RAIZ%\historial" mkdir "%FOLDER_RAIZ%\historial"

:: 3. LIMPIEZA FIFO (Sin bloques de parentesis largos para evitar cierres)
echo [2/5] Auditando historial...
set "count=0"
for /f "delims=" %%D in ('dir "%FOLDER_RAIZ%\historial" /ad /b /o:d 2^>nul') do (
    set /a count+=1
)

if %count% GTR %MAX_CARPETAS% (
    echo [!] Limite excedido. Limpiando...
    for /f "tokens=* delims=" %%A in ('dir "%FOLDER_RAIZ%\historial" /ad /b /o:d') do (
        if %BORRAR_CANTIDAD% GTR 0 (
            rd /s /q "%FOLDER_RAIZ%\historial\%%A"
            set /a BORRAR_CANTIDAD-=1
        )
    )
)

:: 4. GENERAR TIMESTAMP CON SEGUNDOS
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
:: Formato: _YYYY_MM_DD_HHMMSS
set "STAMP=_%dt:~0,4%_%dt:~4,2%_%dt:~6,2%_%dt:~8,2%%dt:~10,2%%dt:~12,2%"

:: 5. RESPALDO Y MOVIMIENTO
echo [3/5] Procesando archivos de 'last' a 'historial'...
:: Verificamos si hay archivos en last
dir /a-d "%FOLDER_RAIZ%\last\*" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Creando backup: last%STAMP%
    mkdir "%FOLDER_RAIZ%\historial\last%STAMP%"
    move /y "%FOLDER_RAIZ%\last\*" "%FOLDER_RAIZ%\historial\last%STAMP%\" >nul
)

echo [4/5] Moviendo archivos nuevos de data/ a data/last/...
:: /XF excluye el script. /LEV:1 solo archivos en raiz de data.
robocopy "%FOLDER_RAIZ%" "%FOLDER_RAIZ%\last" /MOV /LEV:1 /XF "%~nx0" /XD last historial /NFL /NDL /NJH /NJS /nc /ns /np

:: 6. EJECUCIÓN
echo [5/5] Ejecutando Python...
if exist "src\main.py" (
    echo ------------------------------------------------------
    py src\main.py --new -vvv
    echo ------------------------------------------------------
    if %errorlevel% neq 0 echo [!] Python devolvio error: %errorlevel%
) else (
    echo [ERROR] No se encontro "src\main.py" en esta carpeta.
)

echo.
echo ======================================================
echo [FIN] Proceso terminado.
echo ======================================================
pause
exit
