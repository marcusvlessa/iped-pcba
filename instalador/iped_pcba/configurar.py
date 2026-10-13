"""Aplica um Plano nos arquivos do IPED, com backup e reversão.

Regras de escrita:
- toda execução copia antes os arquivos que vai tocar para
  <raiz>/pcba/backup/<carimbo>/, com um manifesto.json;
- preserva BOM, quebra de linha (CRLF/LF) e comentários do arquivo original;
- uma chave já ativa é substituída no lugar; se só existir comentada,
  a primeira ocorrência comentada é ativada; senão vai para o fim.
"""

import datetime
import io
import json
import os
import re
import shutil

PASTA_PCBA = "pcba"
BOM = u"﻿"


def ler_texto(caminho):
    with io.open(caminho, "r", encoding="utf-8", newline="") as f:
        return f.read()


def gravar_texto(caminho, texto):
    pasta = os.path.dirname(caminho)
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta)
    with io.open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def ler_chaves(texto):
    """Chaves ativas (não comentadas) de um arquivo chave = valor."""
    out = {}
    for linha in texto.lstrip(BOM).splitlines():
        s = linha.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def definir_chave(texto, chave, valor):
    """Devolve o texto com chave = valor aplicado."""
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(eol)
    ativa = re.compile(r"^\s*" + re.escape(chave) + r"\s*=")
    comentada = re.compile(r"^\s*#\s*" + re.escape(chave) + r"\s*=")
    nova = "{} = {}".format(chave, valor)

    def limpa(l):
        return l.lstrip(BOM)

    for i, l in enumerate(linhas):
        if ativa.match(limpa(l)):
            linhas[i] = (BOM if l.startswith(BOM) else "") + nova
            return eol.join(linhas)
    for i, l in enumerate(linhas):
        if comentada.match(limpa(l)):
            linhas[i] = (BOM if l.startswith(BOM) else "") + nova
            return eol.join(linhas)
    if linhas and linhas[-1] == "":
        linhas.insert(len(linhas) - 1, nova)
    else:
        linhas.append(nova)
    return eol.join(linhas)


def carimbo():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


class Backup(object):
    """Copia arquivos para pcba/backup/<carimbo>/ antes da primeira escrita."""

    def __init__(self, raiz, nome=None):
        self.raiz = raiz
        base = nome or carimbo()
        self.nome, n = base, 1
        # duas execuções no mesmo segundo não podem dividir a mesma pasta
        while os.path.exists(os.path.join(raiz, PASTA_PCBA, "backup", self.nome)):
            n += 1
            self.nome = "{}-{}".format(base, n)
        self.pasta = os.path.join(raiz, PASTA_PCBA, "backup", self.nome)
        self.registros = {}

    def proteger(self, relativo):
        if relativo in self.registros:
            return
        origem = os.path.join(self.raiz, relativo)
        existia = os.path.exists(origem)
        if existia:
            destino = os.path.join(self.pasta, relativo)
            if os.path.isdir(origem):
                shutil.copytree(origem, destino)
            else:
                if not os.path.isdir(os.path.dirname(destino)):
                    os.makedirs(os.path.dirname(destino))
                shutil.copy2(origem, destino)
        self.registros[relativo] = {"existia": existia,
                                    "pasta": os.path.isdir(origem) if existia else False}

    def fechar(self, extra=None):
        if not self.registros:
            return None
        if not os.path.isdir(self.pasta):
            os.makedirs(self.pasta)
        manifesto = {"criado_em": self.nome, "arquivos": self.registros}
        manifesto.update(extra or {})
        gravar_texto(os.path.join(self.pasta, "manifesto.json"),
                     json.dumps(manifesto, indent=2, ensure_ascii=False))
        return self.pasta


def aplicar_plano(raiz, plano, backup, simular=False):
    """Aplica as alterações. Devolve a lista do que mudou de fato."""
    mudancas = []
    por_arquivo = {}
    for a in plano.alteracoes:
        por_arquivo.setdefault(a.arquivo, []).append(a)
    for relativo, alts in sorted(por_arquivo.items()):
        caminho = os.path.join(raiz, relativo)
        if not os.path.isfile(caminho):
            mudancas.append({"arquivo": relativo, "erro": "arquivo não encontrado"})
            continue
        original = ler_texto(caminho)
        atual = original
        antes = ler_chaves(original)
        for a in alts:
            if antes.get(a.chave) == a.valor:
                continue
            atual = definir_chave(atual, a.chave, a.valor)
            mudancas.append({"arquivo": relativo, "chave": a.chave, "de": antes.get(a.chave),
                             "para": a.valor, "motivo": a.motivo})
        if atual != original and not simular:
            backup.proteger(relativo)
            gravar_texto(caminho, atual)
    return mudancas


def listar_backups(raiz):
    base = os.path.join(raiz, PASTA_PCBA, "backup")
    if not os.path.isdir(base):
        return []

    def ordem(nome):
        partes = nome.split("-")
        return (partes[0], partes[1] if len(partes) > 1 else "",
                int(partes[2]) if len(partes) > 2 and partes[2].isdigit() else 1)
    return sorted((d for d in os.listdir(base)
                   if os.path.isfile(os.path.join(base, d, "manifesto.json"))), key=ordem)


def reverter(raiz, nome=None):
    """Restaura um backup (o mais recente, se nome for None)."""
    nomes = listar_backups(raiz)
    if not nomes:
        raise RuntimeError("Nenhum backup encontrado em {}".format(
            os.path.join(raiz, PASTA_PCBA, "backup")))
    nome = nome or nomes[-1]
    pasta = os.path.join(raiz, PASTA_PCBA, "backup", nome)
    manifesto = json.loads(ler_texto(os.path.join(pasta, "manifesto.json")))
    restaurados = []
    for relativo, info in sorted(manifesto["arquivos"].items()):
        alvo = os.path.join(raiz, relativo)
        if os.path.isdir(alvo):
            shutil.rmtree(alvo)
        elif os.path.exists(alvo):
            os.remove(alvo)
        if info["existia"]:
            origem = os.path.join(pasta, relativo)
            if info.get("pasta"):
                shutil.copytree(origem, alvo)
            else:
                shutil.copy2(origem, alvo)
        restaurados.append(relativo)
    return nome, restaurados


# ---------------------------------------------------------------- lançadores

_BAT = r"""@echo off
rem Gerado pelo instalador IPED-PCBA em {data}. Nao edite: rode o instalador de novo.
rem Uso: iped-pcba.bat ^<perfil^> ^<evidencia^> ^<pasta-do-caso^> [outros parametros do IPED]
rem Perfis: {perfis}
if "%~3"=="" (
  echo Uso: %~nx0 perfil evidencia pasta-do-caso
  exit /b 1
)
set IPED_ROOT=%~dp0..
set PERFIL=%~1
set EVID=%~2
set SAIDA=%~3
shift & shift & shift
"%IPED_ROOT%\jre\bin\java.exe" -jar "%IPED_ROOT%\iped.jar" -Xmx{heap}g -profile "%PERFIL%" -d "%EVID%" -o "%SAIDA%" -tz GMT-3 %1 %2 %3 %4 %5 %6 %7 %8 %9
"""

_SH = """#!/usr/bin/env bash
# Gerado pelo instalador IPED-PCBA em {data}. Não edite: rode o instalador de novo.
# Uso: iped-pcba.sh <perfil> <evidencia> <pasta-do-caso> [outros parâmetros do IPED]
# Perfis: {perfis}
set -euo pipefail
if [ $# -lt 3 ]; then echo "Uso: $0 perfil evidencia pasta-do-caso" >&2; exit 1; fi
IPED_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PERFIL="$1"; EVID="$2"; SAIDA="$3"; shift 3
JAVA="$IPED_ROOT/jre/bin/java"; [ -x "$JAVA" ] || JAVA=java
exec "$JAVA" -jar "$IPED_ROOT/iped.jar" -Xmx{heap}g -profile "$PERFIL" -d "$EVID" -o "$SAIDA" -tz GMT-3 --nogui "$@"
"""

_SH_TRANSCRICAO = """#!/usr/bin/env bash
# Servidor central de transcrição (IPED RemoteTranscriptionDiscovery + Service).
# Gerado pelo instalador IPED-PCBA em {data}.
# Uso: transcricao-servidor.sh [porta-descoberta] [porta-servico]
set -euo pipefail
IPED_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORTA_DESC="${{1:-11111}}"; PORTA_SERV="${{2:-11112}}"
JAVA="$IPED_ROOT/jre/bin/java"; [ -x "$JAVA" ] || JAVA=java
CP="$IPED_ROOT/iped.jar:$IPED_ROOT/lib/*"
"$JAVA" -cp "$CP" iped.engine.task.transcript.RemoteTranscriptionDiscovery "$PORTA_DESC" &
sleep 3
exec "$JAVA" -Xmx{heap}g -cp "$CP" iped.engine.task.transcript.RemoteTranscriptionService "127.0.0.1:$PORTA_DESC" "$PORTA_SERV"
"""


def gerar_lancadores(raiz, plano, perfis, so, backup, papel="cliente"):
    heap = plano.heap_gb or 8
    data = datetime.date.today().isoformat()
    lista = ", ".join(perfis)
    gerados = []
    alvos = [("iped-pcba.bat", _BAT)] if so == "windows" else [("iped-pcba.sh", _SH)]
    if so != "windows" and papel == "servidor":
        alvos.append(("transcricao-servidor.sh", _SH_TRANSCRICAO))
    for nome, modelo in alvos:
        relativo = PASTA_PCBA + "/" + nome
        backup.proteger(relativo)
        texto = modelo.format(data=data, heap=heap, perfis=lista)
        if nome.endswith(".bat"):
            texto = texto.replace("\n", "\r\n")
        caminho = os.path.join(raiz, relativo)
        gravar_texto(caminho, texto)
        if not nome.endswith(".bat"):
            os.chmod(caminho, 0o755)
        gerados.append(relativo)
    return gerados


def gravar_maquina(raiz, maquina, plano, mudancas, backup):
    relativo = PASTA_PCBA + "/maquina.json"
    backup.proteger(relativo)
    dados = {"maquina": maquina, "plano": plano.como_dict(), "mudancas": mudancas}
    gravar_texto(os.path.join(raiz, relativo),
                 json.dumps(dados, indent=2, ensure_ascii=False))
    return relativo
