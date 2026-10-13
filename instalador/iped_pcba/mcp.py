"""Instala o MCP da PCBA (fork do iped-tools-mcp) junto do IPED.

O MCP não leva as bibliotecas do IPED dentro dele: o lançador põe <IPED>/lib/* no classpath,
então ele lê os casos com a mesma versão do IPED que os gerou.

De onde vem o MCP, nesta ordem:
1. mcp-dist/ na raiz deste repositório (pacote da página de Releases, com Java embutido);
2. mcp/target/*-runner.jar (compilado na própria máquina com Maven).

O Java usado precisa ser 21 ou mais novo (o Java que vem com o IPED 4.3 é o 11):
o runtime do pacote, depois JAVA_HOME, depois as pastas comuns de JDK e o PATH.
"""

import datetime
import glob
import json
import os
import re
import shutil
import subprocess

from .configurar import PASTA_PCBA, gravar_texto

JAVA_MINIMO = 21
HEAP_MCP_GB = 4
PASTA_MCP = PASTA_PCBA + "/mcp"
JAR = "iped-pcba-mcp.jar"
# Se este arquivo existe na pasta do MCP, o lançador libera as ferramentas de escrita
# (marcadores, comentários, seleção de itens). Tudo continua no log de auditoria.
ARQ_ESCRITA = "escrita-ativa.txt"
# Caso que a IA enxerga; o MCP relê este arquivo a cada chamada.
CASO_ATIVO = os.path.join(os.path.expanduser("~"), ".iped-tools-mcp", "active_case.txt")
CLASSE = "br.com.ipedtools.mcp.McpApplication"
ABERTURAS = " ".join("--add-opens=java.base/{}=ALL-UNNAMED".format(p) for p in (
    "java.lang", "java.lang.reflect", "java.math", "java.util", "java.util.concurrent",
    "java.util.concurrent.atomic", "java.net", "java.text", "java.nio", "java.io"))


def versao_java(saida):
    """Versão principal a partir da saída de 'java -version' (1.8 -> 8)."""
    m = re.search(r'version "(\d+)(?:\.(\d+))?', saida or "")
    if not m:
        return 0
    principal = int(m.group(1))
    if principal == 1 and m.group(2):
        return int(m.group(2))
    return principal


def _exe(pasta, so):
    return os.path.join(pasta, "bin", "java.exe" if so == "windows" else "java")


def _versao_de(java):
    try:
        p = subprocess.run([java, "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=30)
        return versao_java(p.stdout.decode("utf-8", "replace"))
    except (OSError, subprocess.SubprocessError):
        return 0


def candidatos_java(so, pacote=None):
    out = []
    if pacote and pacote.get("runtime"):
        out.append(_exe(pacote["runtime"], so))
    if os.environ.get("JAVA_HOME"):
        out.append(_exe(os.environ["JAVA_HOME"], so))
    if so == "windows":
        bases = [os.path.join(os.environ.get(v, ""), d)
                 for v in ("ProgramFiles", "ProgramW6432")
                 for d in ("Java", "Eclipse Adoptium", "Microsoft", "Zulu", "BellSoft", "Amazon Corretto")]
    else:
        bases = ["/usr/lib/jvm", "/opt/java", "/opt"]
    for b in bases:
        out += sorted(glob.glob(os.path.join(b, "*", "bin", "java.exe" if so == "windows" else "java")),
                      reverse=True)
    achado = shutil.which("java")
    if achado:
        out.append(achado)
    vistos, unicos = set(), []
    for c in out:
        k = os.path.normcase(os.path.abspath(c))
        if k not in vistos and os.path.isfile(c):
            vistos.add(k)
            unicos.append(c)
    return unicos


def achar_java(so, pacote=None, versao=_versao_de):
    """(caminho, versão) do primeiro Java >= 21, ou (None, maior versão vista)."""
    maior = 0
    for c in candidatos_java(so, pacote):
        v = versao(c)
        if v >= JAVA_MINIMO:
            return c, v
        maior = max(maior, v)
    return None, maior


def localizar_pacote(repo):
    """Onde está o MCP compilado. None se não houver."""
    dist = os.path.join(repo, "mcp-dist")
    if os.path.isfile(os.path.join(dist, JAR)):
        rt = os.path.join(dist, "runtime")
        return {"jar": os.path.join(dist, JAR), "runtime": rt if os.path.isdir(rt) else None,
                "origem": "mcp-dist"}
    jars = sorted(glob.glob(os.path.join(repo, "mcp", "target", "*-runner.jar")))
    if jars:
        return {"jar": jars[-1], "runtime": None, "origem": "mcp/target"}
    return None


_BAT = r"""@echo off
rem Gerado pelo instalador IPED-PCBA em {data}. Nao edite: rode o instalador de novo.
rem MCP do IPED para IA (Claude Desktop, LM Studio, Hermes), com log de auditoria.
rem Escrita no caso (marcadores) liberada se existir {escrita} nesta pasta (o painel liga e desliga).
rem Uso: iped-pcba-mcp.bat [--case pasta-do-caso] [--http [--host IP] [--porta N]] [--permitir-escrita]
setlocal
set "MCP=%~dp0"
for %%I in ("%~dp0..\..") do set "IPED_ROOT=%%~fI"
set "MODO=--stdio"
echo %* | find /i "--http" >nul && set "MODO="
set "ESCRITA="
if exist "%MCP%{escrita}" set "ESCRITA=--permitir-escrita"
"{java}" -Xmx{heap}g -Dstdout.encoding=UTF-8 -Dfile.encoding=UTF-8 {aberturas} -cp "%MCP%{jar};%IPED_ROOT%\lib\*" {classe} %MODO% %ESCRITA% %*
"""

_SH = """#!/usr/bin/env bash
# Gerado pelo instalador IPED-PCBA em {data}. Não edite: rode o instalador de novo.
# MCP do IPED para IA (Claude Desktop, LM Studio, Hermes), com log de auditoria.
# Escrita no caso (marcadores) liberada se existir {escrita} nesta pasta (o painel liga e desliga).
# Uso: iped-pcba-mcp.sh [--case pasta-do-caso] [--http [--host IP] [--porta N]] [--permitir-escrita]
set -euo pipefail
MCP="$(cd "$(dirname "$0")" && pwd)"
IPED_ROOT="$(cd "$MCP/../.." && pwd)"
MODO="--stdio"
for a in "$@"; do [ "$a" = "--http" ] && MODO=""; done
ESCRITA=""
[ -f "$MCP/{escrita}" ] && ESCRITA="--permitir-escrita"
exec "{java}" -Xmx{heap}g -Dstdout.encoding=UTF-8 -Dfile.encoding=UTF-8 {aberturas} \\
  -cp "$MCP/{jar}:$IPED_ROOT/lib/*" {classe} $MODO $ESCRITA "$@"
"""


def config_clientes(lancador):
    """Trecho de configuração para Claude Desktop e LM Studio (mesmo formato mcpServers)."""
    return {"mcpServers": {"iped-pcba": {"command": lancador, "args": []}}}


def escrita_ativa(raiz):
    return os.path.isfile(os.path.join(raiz, PASTA_MCP, ARQ_ESCRITA))


def definir_escrita(raiz, ativa):
    """Liga ou desliga as ferramentas de escrita para as próximas sessões do MCP."""
    arq = os.path.join(raiz, PASTA_MCP, ARQ_ESCRITA)
    if ativa:
        gravar_texto(arq, "Escrita liberada em {} pelo usuário {}.\n".format(
            datetime.datetime.now().isoformat(timespec="seconds"),
            os.environ.get("USERNAME") or os.environ.get("USER") or "?"))
    elif os.path.isfile(arq):
        os.remove(arq)
    return escrita_ativa(raiz)


def instalar_mcp(raiz, so, repo, backup, simular=False, java=None, pacote=None, escrita=True):
    """Copia o MCP para <IPED>/pcba/mcp e gera o lançador. Devolve um dict com o resultado."""
    pacote = pacote or localizar_pacote(repo)
    if not pacote:
        return {"instalado": False,
                "aviso": "MCP não instalado: pacote não encontrado (baixe o pacote da página de "
                         "Releases, que traz a pasta mcp-dist, ou compile a pasta mcp/ com Maven)."}
    if java is None:
        java, maior = achar_java(so, pacote)
        if not java:
            return {"instalado": False,
                    "aviso": "MCP não instalado: precisa de Java {}+ (maior encontrado: {}). Use o "
                             "pacote da página de Releases, que já traz o Java.".format(
                                 JAVA_MINIMO, maior or "nenhum")}
    destino = os.path.normpath(os.path.join(raiz, PASTA_MCP))
    nome = "iped-pcba-mcp.bat" if so == "windows" else "iped-pcba-mcp.sh"
    lancador = os.path.join(destino, nome)
    res = {"instalado": not simular, "origem": pacote["origem"], "lancador": lancador, "escrita": escrita,
           "java": java, "config_clientes": config_clientes(lancador)}
    if simular:
        return res

    backup.proteger(PASTA_MCP)
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    os.makedirs(destino)
    shutil.copy2(pacote["jar"], os.path.join(destino, JAR))
    if pacote.get("runtime") and os.path.abspath(java).startswith(os.path.abspath(pacote["runtime"])):
        shutil.copytree(pacote["runtime"], os.path.join(destino, "runtime"))
        java = _exe(os.path.join(destino, "runtime"), so)
    # o caminho do Java vai no lançador; o do IPED é relativo à pasta, para sobreviver a cópias
    if so == "windows":
        java_lanc = java.replace(os.path.join(destino, ""), "%MCP%")
    else:
        java_lanc = java.replace(os.path.join(destino, ""), "$MCP/")
    modelo = _BAT if so == "windows" else _SH
    texto = modelo.format(data=datetime.date.today().isoformat(), java=java_lanc, heap=HEAP_MCP_GB,
                          aberturas=ABERTURAS, jar=JAR, classe=CLASSE, escrita=ARQ_ESCRITA)
    if so == "windows":
        texto = texto.replace("\n", "\r\n")
    gravar_texto(lancador, texto)
    if so != "windows":
        os.chmod(lancador, 0o755)
    gravar_texto(os.path.join(destino, "config-clientes-ia.json"),
                 json.dumps(res["config_clientes"], indent=2, ensure_ascii=False))
    definir_escrita(raiz, escrita)
    res["java"] = java
    res["escrita"] = escrita
    return res
