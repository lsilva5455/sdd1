@echo off
setlocal

:: =====================================================================
:: CONFIGURACIÓN
:: =====================================================================
set "SC1_NAME=Iniciar_sesion"
set "SC1_TARGET=Iniciar_mps.bat"

set "SC2_NAME=Continuar_sesion"
set "SC2_TARGET=Continuar_mps.bat"

:: Rutas
set "ESCRITORIO=%USERPROFILE%\Desktop"
set "DIR_ACTUAL=%~dp0"
set "REPO_DIR=%USERPROFILE%\mp_core\mp_simclient"
set "GITHUB_USER=lsilva5455"
set "GITHUB_REPO_NAME=mp_simclient"
:: IMPORTANT: Set GITHUB_TOKEN as an environment variable before running this script.
:: To set it: set GITHUB_TOKEN=your_personal_access_token
:: To generate a token: GitHub > Settings > Developer settings > Personal access tokens
if not defined GITHUB_TOKEN (
    echo [ERROR] La variable de entorno GITHUB_TOKEN no esta configurada.
    echo [INFO] Ejecuta: set GITHUB_TOKEN=tu_token_personal
    echo [INFO] Para generar un token: GitHub ^> Settings ^> Developer settings ^> Personal access tokens
    pause
    exit /b 1
)
set "GITHUB_REPO=https://%GITHUB_TOKEN%@github.com/%GITHUB_USER%/%GITHUB_REPO_NAME%.git"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo =====================================================================
echo   INSTALADOR MP SIMCLIENT
echo =====================================================================
echo [INFO] Fecha: 2026-01-03
echo.

:: =====================================================================
:: 1. VERIFICAR SI EXISTE EL DIRECTORIO DEL PROYECTO
:: =====================================================================
if not exist "%REPO_DIR%" (
    echo [INFO] Directorio %REPO_DIR% no encontrado.
    echo [INFO] Clonando repositorio desde GitHub...
    
    :: Crear directorio padre si no existe
    if not exist "%USERPROFILE%\mp_core" (
        mkdir "%USERPROFILE%\mp_core"
    )
    
    :: Verificar si git está instalado
    where git >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Git no esta instalado. Por favor instala Git desde https://git-scm.com/
        echo [ERROR] Una vez instalado, ejecuta este script nuevamente.
        pause
        exit /b 1
    )
    
    :: Clonar repositorio
    cd /d "%USERPROFILE%\mp_core"
    echo [INFO] Clonando repositorio privado con autenticacion...
    git clone %GITHUB_REPO%
    
    if errorlevel 1 (
        echo [ERROR] No se pudo clonar el repositorio. Verifica tu conexion a internet.
        pause
        exit /b 1
    )
    
    echo [OK] Repositorio clonado exitosamente.
    
    :: Cambiar al directorio del proyecto
    cd /d "%REPO_DIR%"
    
    :: Crear carpeta data si no existe
    if not exist "data" mkdir data
    
) else (
    echo [OK] Directorio del proyecto encontrado: %REPO_DIR%
    cd /d "%REPO_DIR%"
)

echo.

:: =====================================================================
:: 2. VERIFICAR E INSTALAR DEPENDENCIAS PYTHON
:: =====================================================================
echo [INFO] Verificando dependencias Python...

:: Verificar si Python está instalado
python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no esta instalado. Por favor instala Python 3.8 o superior.
    pause
    exit /b 1
)

:: Instalar requirements si existen
if exist "requirements.txt" (
    echo [INFO] Instalando dependencias desde requirements.txt...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    
    if errorlevel 1 (
        echo [WARNING] Algunas dependencias no se instalaron correctamente.
    ) else (
        echo [OK] Dependencias instaladas correctamente.
    )
) else (
    echo [WARNING] No se encontro requirements.txt
)

echo.

:: =====================================================================
:: 3. INICIALIZAR VARIABLES Y CONFIGURACIÓN
:: =====================================================================
echo [INFO] Inicializando configuracion del sistema...

:: Crear archivos de datos iniciales si no existen
if not exist "data\lista_pos.json" (
    echo [] > "data\lista_pos.json"
    echo [OK] Creado data\lista_pos.json
)

if not exist "data\mapeo_statistics.json" (
    echo {} > "data\mapeo_statistics.json"
    echo [OK] Creado data\mapeo_statistics.json
)

if not exist "data\slot_state.json" (
    echo {} > "data\slot_state.json"
    echo [OK] Creado data\slot_state.json
)

if not exist "data\numero_simid.txt" (
    echo 0 > "data\numero_simid.txt"
    echo [OK] Creado data\numero_simid.txt
)

:: Crear subdirectorios necesarios
if not exist "data\temp" mkdir "data\temp"
if not exist "data\historial" mkdir "data\historial"
if not exist "data\last" mkdir "data\last"
if not exist "logs" mkdir "logs"

echo [OK] Estructura de directorios inicializada.
echo.

:: =====================================================================
:: 4. CONFIGURAR ACCESOS DIRECTOS EN EL ESCRITORIO
:: =====================================================================
echo [INFO] Configurando accesos directos en el escritorio...

:: 1. Verificar y crear Acceso Directo 1 (Iniciar)
if not exist "%ESCRITORIO%\%SC1_NAME%.lnk" (
    echo [CREANDO] %SC1_NAME%...
    call :CreateShortcut "%SC1_TARGET%" "%SC1_NAME%" "%ESCRITORIO%"
) else (
    echo [OK] %SC1_NAME% ya existe en el escritorio.
)

:: 2. Verificar y crear Acceso Directo 2 (Continuar)
if not exist "%ESCRITORIO%\%SC2_NAME%.lnk" (
    echo [CREANDO] %SC2_NAME%...
    call :CreateShortcut "%SC2_TARGET%" "%SC2_NAME%" "%ESCRITORIO%"
) else (
    echo [OK] %SC2_NAME% ya existe en el escritorio.
)

echo.

:: =====================================================================
:: 5. CONFIGURAR CARPETA STARTUP
:: =====================================================================
echo [INFO] Configurando carpeta de inicio automatico...

:: Verificar que exista la carpeta Startup
if not exist "%STARTUP_DIR%" (
    echo [ERROR] No se encontro la carpeta Startup.
    goto :SkipStartup
)

:: Limpiar Startup, manteniendo solo startup1.vbs
echo [INFO] Limpiando carpeta Startup (manteniendo startup1.vbs)...
for %%F in ("%STARTUP_DIR%\*") do (
    if /i not "%%~nxF"=="startup1.vbs" (
        del /q "%%F" 2>nul
        if exist "%%F" (
            echo [WARNING] No se pudo eliminar: %%~nxF
        ) else (
            echo [OK] Eliminado: %%~nxF
        )
    )
)

:: Crear script VBS que ejecute los dos programas en secuencia
echo [INFO] Creando script de inicio automatico en secuencia...
set "STARTUP_SCRIPT=%STARTUP_DIR%\MP_SimClient_Startup.vbs"
set "TEMP_VBS=%TEMP%\mp_startup_temp.vbs"

:: Crear archivo temporal con manejo de errores y logging
echo On Error Resume Next > "%TEMP_VBS%"
echo Set WshShell = CreateObject("WScript.Shell") >> "%TEMP_VBS%"
echo Set fso = CreateObject("Scripting.FileSystemObject") >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo ' Configuracion >> "%TEMP_VBS%"
echo repoDir = "%REPO_DIR%" >> "%TEMP_VBS%"
echo logFile = repoDir ^& "\logs\startup_errors.log" >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo ' Funcion para escribir logs >> "%TEMP_VBS%"
echo Sub WriteLog(msg) >> "%TEMP_VBS%"
echo   On Error Resume Next >> "%TEMP_VBS%"
echo   Set logStream = fso.OpenTextFile(logFile, 8, True) >> "%TEMP_VBS%"
echo   logStream.WriteLine Now ^& " - " ^& msg >> "%TEMP_VBS%"
echo   logStream.Close >> "%TEMP_VBS%"
echo End Sub >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo WriteLog "=== INICIO MP_SimClient_Startup ===" >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo ' Verificar que existe el directorio >> "%TEMP_VBS%"
echo If Not fso.FolderExists(repoDir) Then >> "%TEMP_VBS%"
echo   WriteLog "ERROR: No existe el directorio " ^& repoDir >> "%TEMP_VBS%"
echo   MsgBox "Error: No se encuentra el directorio del proyecto" ^& vbCrLf ^& repoDir, vbCritical, "MP SimClient Startup" >> "%TEMP_VBS%"
echo   WScript.Quit >> "%TEMP_VBS%"
echo End If >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo ' Verificar que existe el script Python >> "%TEMP_VBS%"
echo pythonScript = repoDir ^& "\src\reset_imei_all.py" >> "%TEMP_VBS%"
echo If Not fso.FileExists(pythonScript) Then >> "%TEMP_VBS%"
echo   WriteLog "ERROR: No existe el archivo " ^& pythonScript >> "%TEMP_VBS%"
echo   MsgBox "Error: No se encuentra reset_imei_all.py" ^& vbCrLf ^& pythonScript, vbCritical, "MP SimClient Startup" >> "%TEMP_VBS%"
echo   WScript.Quit >> "%TEMP_VBS%"
echo End If >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo ' Ejecutar reset_imei_all.py >> "%TEMP_VBS%"
echo WriteLog "Ejecutando reset_imei_all.py..." >> "%TEMP_VBS%"
echo WshShell.CurrentDirectory = repoDir >> "%TEMP_VBS%"
echo comando1 = "cmd /c python " ^& Chr(34) ^& pythonScript ^& Chr(34) >> "%TEMP_VBS%"
echo resultado = WshShell.Run(comando1, 1, False) >> "%TEMP_VBS%"
echo. >> "%TEMP_VBS%"
echo If Err.Number ^<^> 0 Then >> "%TEMP_VBS%"
echo   WriteLog "ERROR al ejecutar: " ^& Err.Description >> "%TEMP_VBS%"
echo   MsgBox "Error al iniciar MP SimClient:" ^& vbCrLf ^& Err.Description, vbCritical, "MP SimClient Startup" >> "%TEMP_VBS%"
echo Else >> "%TEMP_VBS%"
echo   WriteLog "Script iniciado correctamente" >> "%TEMP_VBS%"
echo End If >> "%TEMP_VBS%"

:: Mover archivo temporal a Startup
move /Y "%TEMP_VBS%" "%STARTUP_SCRIPT%" >nul 2>nul

if exist "%STARTUP_SCRIPT%" (
    echo [OK] Script de inicio creado: MP_SimClient_Startup.vbs
) else (
    echo [ERROR] No se pudo crear el script de inicio.
)

:SkipStartup


echo.
echo =====================================================================
echo   INSTALACION COMPLETADA
echo =====================================================================
echo [OK] El sistema MP SimClient ha sido instalado correctamente.
echo [OK] Los accesos directos estan listos en el escritorio.
echo.
echo Para iniciar el sistema, usa: Iniciar_sesion
echo Para continuar una sesion, usa: Continuar_sesion
echo.
pause
exit /b 0

:: =====================================================================
:: FUNCION PARA CREAR ACCESO DIRECTO (VBScript Bridge)
:: =====================================================================
:CreateShortcut
set "target=%~1"
set "name=%~2"
set "destination=%~3"
set "script=%temp%\shortcut.vbs"

:: Determinar el icono según el nombre del acceso directo
set "icon_path="
if /i "%name%"=="Iniciar_sesion" (
    :: Icono de Play/Ejecutar - Verde con flecha derecha
    set "icon_path=%%SystemRoot%%\System32\shell32.dll,137"
)
if /i "%name%"=="Continuar_sesion" (
    :: Icono de Continuar/Resume - Azul con doble flecha
    set "icon_path=%%SystemRoot%%\System32\shell32.dll,239"
)

echo set WshShell = WScript.CreateObject("WScript.Shell") > "%script%"
echo set oShellLink = WshShell.CreateShortcut("%destination%\%name%.lnk") >> "%script%"
echo oShellLink.TargetPath = "%REPO_DIR%\%target%" >> "%script%"
echo oShellLink.WorkingDirectory = "%REPO_DIR%" >> "%script%"
echo oShellLink.WindowStyle = 1 >> "%script%"
if defined icon_path (
    echo oShellLink.IconLocation = "%icon_path%" >> "%script%"
)
echo oShellLink.Save >> "%script%"

cscript /nologo "%script%"
del "%script%"
goto :eof
