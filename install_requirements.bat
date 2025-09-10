@echo off
mode con: cols=100 lines=30
color 0a
cls
echo.
echo   _________ __  ______     ____  ______________ __________________    __ 
echo  /_  __/ / / / / / __ \   / __ \/ ____/ ____/  _/ ____/  _/  _/   / / 
echo   / / / /_/ / / / / / /  / / / / /_  / /_   / // /    / / / /    / /  
echo  / / / __  / / / /_/ /  / /_/ / __/ / __/ _/ // /____/ /_/ /    / /___
echo /_/ /_/ /_/_/_/\____/   \____/_/   /_/   /___/\____/___/___/   /_____/
echo.
echo                        [ Created by Hannibal THO ]
echo.
echo =================================================================================
echo.
echo [1] Requisitos de instalacion (Necesario para la primera configuracion)
echo    - Instala todos los paquetes y dependencias de Python necesarios
echo    - Configura el entorno para THO GFUSION
echo.
echo [2] Unete a la comunidad oficial de Discord
echo    - Obten soporte y actualizaciones
echo    - Conectate con otros usuarios
echo    - Accede a contenido exclusivo
echo.
echo =================================================================================
echo.
set /p choice="Escribe un numero (1 o 2): "

if "%choice%"=="2" (
    start https://discord.gg/hxYaTaKT
    exit
)
if "%choice%"=="1" (
    cls
    echo Verificando Python y paquetes instalados...
    echo.
    
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python no esta instalado o no esta en el PATH
        echo Por favor, instala Python desde https://www.python.org/downloads/
        echo.
        echo Presiona cualquier tecla para salir...
        pause >nul
        exit
    )
    
    echo Actualizando pip...
    python -m pip install --upgrade pip >nul 2>&1

    echo Verificando paquetes instalados...
    python -c "import PyQt5, keyboard, numpy, matplotlib, requests, cryptography, pymem, psutil, PIL, comtypes, win32api, dotenv, imgui, websockets" 2>nul
    if not errorlevel 1 (
        echo.
        echo Todos los paquetes necesarios ya estan instalados!
        echo.
        echo Instalacion completada! Presiona cualquier tecla para salir...
        echo =================================================================================
        pause >nul
        exit
    )
    
    echo Instalando paquetes faltantes...
    echo [                    ] 0%%
    pip install PyQt5 >nul 2>&1
    echo [==                  ] 10%%
    pip install keyboard >nul 2>&1
    echo [====                ] 20%%
    pip install numpy >nul 2>&1
    echo [======              ] 30%%
    pip install matplotlib >nul 2>&1
    echo [========            ] 40%%
    pip install requests >nul 2>&1
    echo [==========          ] 50%%
    pip install cryptography >nul 2>&1
    echo [============        ] 60%%
    pip install pymem >nul 2>&1
    echo [==============      ] 70%%
    pip install psutil >nul 2>&1
    echo [================    ] 80%%
    pip install pillow >nul 2>&1
    echo [==================  ] 90%%
    pip install comtypes >nul 2>&1
    pip install pywin32 >nul 2>&1
    pip install python-dotenv >nul 2>&1
    pip install imgui >nul 2>&1
    pip install websockets >nul 2>&1
    pip install pyinstaller >nul 2>&1
    echo [====================] 100%%

    echo.
    echo Instalacion completada! Presiona cualquier tecla para salir...
    echo =================================================================================
    pause >nul
    exit
)

echo Opcion no valida. Presiona cualquier tecla para salir...
pause >nul