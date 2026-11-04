@echo off
rem roda os comandos passados como argumentos num processo NAO elevado (via runas /trustlevel)
set OUT=%~dp0lowpriv.txt
whoami /groups | findstr /i "Mandatory" >> "%OUT%"
%* >> "%OUT%" 2>&1
echo EXIT=%ERRORLEVEL% >> "%OUT%"
echo FIM >> "%OUT%"
