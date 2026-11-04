@echo off
rem ==========================================================================
rem  build_exe.bat - gera claude_usage_guard.exe (Windows 10 1809+ / 11)
rem  Requer Python 3.9+ instalado (python.org). Rode com duplo clique ou no
rem  terminal, dentro desta pasta.
rem ==========================================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (echo Python nao encontrado. Instale em https://www.python.org/downloads/ & goto :err)

echo [1/3] Instalando dependencias (pywinpty, pyinstaller)...
%PY% -m pip install --upgrade -r requirements-windows.txt pyinstaller || goto :err

echo [2/3] Gerando o executavel...
rem --onedir: o .exe abre rapido. Isso importa porque os hooks do Claude Code
rem chamam o .exe a cada uso de ferramenta (--onefile descompacta tudo a cada
rem chamada e deixaria cada uma ~1 s mais lenta).
rem numpy/PIL: o programa não usa, mas o PyInstaller os puxa se estiverem
rem instalados no Python (+34 MB). O tkinter (janela) entra sozinho.
%PY% -m PyInstaller --noconfirm --clean --onedir --console ^
    --name claude_usage_guard --icon assets\app.ico --add-data "assets\app.ico;assets" ^
    --add-data "assets\skills;assets\skills" ^
    --exclude-module numpy --exclude-module PIL ^
    --collect-all winpty claude_usage_guard.py || goto :err

echo [3/3] Copiando config.yaml...
copy /y config.yaml dist\claude_usage_guard\config.yaml >nul || goto :err

echo.
echo Pronto: %~dp0dist\claude_usage_guard\claude_usage_guard.exe
echo Teste com:  dist\claude_usage_guard\claude_usage_guard.exe check-config
exit /b 0

:err
echo.
echo Falha no build. Veja as mensagens acima.
exit /b 1
