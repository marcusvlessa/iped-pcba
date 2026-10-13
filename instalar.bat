@echo off
rem Instalador IPED-PCBA: dois cliques. Acha o IPED e abre o painel no navegador.
rem Para configurar pelo console: instalar.bat -Texto
echo IPED-PCBA 0.2 - ao final abre o Painel IPED-PCBA no navegador.
echo Se aparecer so a pergunta S/N e nada abrir, voce esta usando uma copia antiga.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
pause
