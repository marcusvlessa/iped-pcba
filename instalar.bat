@echo off
rem Instalador IPED-PCBA: de dois cliques. Acha o IPED, mostra o plano e pergunta antes de gravar.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
pause
