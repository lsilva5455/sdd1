@echo off
:: Ubicar el script en su directorio actual
set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

echo ======================================================
echo [EXEC] LANZANDO SIMCLIENT (MODO RESUME)
echo [DATE] 2026-01-02
echo ======================================================

:: Verificar únicamente la existencia del script de Python antes de lanzar
if exist "src\main.py" (
    :: Ejecución directa sin manipulación de carpetas
    py src\main.py --resume -vvv
    
    if %errorlevel% neq 0 (
        echo.
        echo [!] Ejecucion finalizada con codigo de error: %errorlevel%
    )
) else (
    echo [ERROR] No se encuentra "src\main.py" en: %BASE_DIR%
)

echo.
echo [FIN] Presione cualquier tecla para cerrar...
pause >nul
