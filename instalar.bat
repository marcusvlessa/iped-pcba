@echo off
rem Instalador IPED-PCBA: dois cliques. Acha o IPED e abre o painel no navegador.
rem Para configurar pelo console: instalar.bat -Texto
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
pause
