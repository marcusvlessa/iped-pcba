"""Atualização do próprio IPED-PCBA pelas versões publicadas no GitHub (Releases).

Ao abrir, o painel pergunta ao GitHub qual é a última versão publicada. Só lê: nenhum dado da máquina
ou dos casos é enviado. Se houver uma mais nova:
  1. o pacote é baixado em segundo plano e conferido (tamanho e SHA-256) e extraído ao lado da pasta atual;
  2. quando o painel fecha (pelo botão "Atualizar agora" ou na próxima vez que ele é aberto), um script
     de fora do pacote espera o painel sair, guarda a versão atual em iped-pcba-anterior-<versão> e põe
     a nova no lugar. No Windows o painel reabre sozinho.
Nada é apagado: para voltar, basta renomear a pasta anterior. Só a biblioteca padrão.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

from . import __version__

WIN = os.name == "nt"
PCBA_REPO = "marcusvlessa/iped-pcba"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODIGO_REINICIAR = 75  # o painel sai com este código para o instalar.bat fechar sem pedir tecla
PACOTE = "iped-pcba-windows.zip" if WIN else "iped-pcba-linux.tar.gz"


def _casa():
    return os.path.join(os.path.expanduser("~"), ".iped-pcba")


def _arq_config():
    return os.path.join(_casa(), "atualizacao.json")


def _arq_pronta():
    return os.path.join(_casa(), "atualizacao-pronta.json")


def _nova_pasta():
    return os.path.join(os.path.dirname(REPO), "_iped-pcba-nova")


def chave(v):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def _ler_json(arq, padrao):
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar_json(arq, dados):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=1, ensure_ascii=False)


def ler_config():
    """automatica: baixa sozinha e instala ao reabrir o painel (padrão). Desligada, só avisa."""
    c = _ler_json(_arq_config(), {})
    return {"automatica": c.get("automatica", True) is not False}


def gravar_config(automatica):
    _gravar_json(_arq_config(), {"automatica": bool(automatica)})
    return ler_config()


def desenvolvimento():
    """Cópia de desenvolvimento (clone do git): não se atualiza sozinha."""
    return os.path.isdir(os.path.join(REPO, ".git"))


_CACHE = {}


def verificar(forcar=False, timeout=5):
    """Última versão publicada e se é mais nova que esta. Sem internet, devolve 'erro' e segue."""
    if not forcar and _CACHE.get("quando", 0) > time.time() - 3600:
        return dict(_CACHE["r"])
    r = {"atual": __version__, "nova": None, "tem_nova": False, "desenvolvimento": desenvolvimento()}
    try:
        req = urllib.request.Request("https://api.github.com/repos/{}/releases/latest".format(PCBA_REPO),
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "iped-pcba"})
        with urllib.request.urlopen(req, timeout=timeout) as f:
            rel = json.loads(f.read().decode("utf-8"))
        v = (rel.get("tag_name") or "").lstrip("vV")
        r.update(nova=v, tag=rel.get("tag_name"), notas=(rel.get("body") or "")[:4000], url=rel.get("html_url"),
                 publicada=(rel.get("published_at") or "")[:10], tem_nova=chave(v) > chave(__version__),
                 tem_pacote=any(a.get("name") == PACOTE for a in rel.get("assets") or []))
    except Exception as e:
        r["erro"] = "Não consegui consultar o GitHub ({}).".format(e)
    _CACHE.update(quando=time.time(), r=r)
    return dict(r)


def pronta():
    """A versão já baixada e extraída, esperando o painel fechar para entrar no lugar."""
    p = _ler_json(_arq_pronta(), None)
    if not p or not os.path.isfile(os.path.join(p.get("pasta", ""), "instalar.bat" if WIN else "scripts/instalar.sh")):
        return None
    return p if chave(p.get("versao")) > chave(__version__) else None


def _versao_da_pasta(pasta):
    try:
        with open(os.path.join(pasta, "instalador", "iped_pcba", "__init__.py"), encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("__version__"):
                    return linha.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def baixar(log=print):
    """Baixa, confere e extrai a versão nova ao lado da atual. Não troca nada ainda."""
    from . import dependencias
    if desenvolvimento():
        raise RuntimeError("Esta é uma cópia de desenvolvimento (git): atualize com git pull.")
    info = verificar(forcar=True, timeout=15)
    if info.get("erro"):
        raise RuntimeError(info["erro"])
    if not info["tem_nova"]:
        log("Você já está na versão mais nova ({}).".format(__version__))
        return None
    log("Versão nova: {} (você usa a {}).".format(info["nova"], __version__))
    a = dependencias.asset_github(PCBA_REPO, nome=PACOTE, tag=info["tag"])
    arq = dependencias.baixar(a["url"], os.path.join(_casa(), "downloads", "iped-pcba-{}-{}".format(
        info["nova"], PACOTE)), a["tamanho"], a["sha256"])
    destino = _nova_pasta()
    if os.path.isdir(destino):
        shutil.rmtree(destino)  # sobra de uma tentativa anterior, criada por este módulo
    os.makedirs(destino)
    if arq.endswith(".zip"):
        dependencias.extrair(arq, destino)
    else:
        with tarfile.open(arq) as t:
            t.extractall(destino, filter="data") if sys.version_info >= (3, 12) else t.extractall(destino)
    pasta = os.path.join(destino, "iped-pcba")
    v = _versao_da_pasta(pasta)
    if v != info["nova"]:
        raise RuntimeError("O pacote baixado diz ser a versão {!r}, e não a {}.".format(v, info["nova"]))
    _gravar_json(_arq_pronta(), {"versao": v, "pasta": pasta, "baixada": datetime.datetime.now().isoformat(
        timespec="seconds")})
    log("Versão {} pronta. Ela entra no lugar quando o painel fechar.".format(v))
    log("PRONTA={}".format(v))
    return pasta


def _pasta_anterior():
    base = "{}-anterior-{}".format(REPO, __version__)
    return base if not os.path.exists(base) else base + "-" + time.strftime("%Y%m%d-%H%M%S")


def script_troca(pid, p=None):
    """Grava o script que, fora do pacote, espera o painel (pid) sair e troca as pastas."""
    p = p or pronta()
    if not p:
        raise RuntimeError("Nenhuma versão nova baixada.")
    bk, nova = _pasta_anterior(), p["pasta"]
    os.makedirs(_casa(), exist_ok=True)
    if WIN:
        arq = os.path.join(_casa(), "atualizar.bat")
        texto = r"""@echo off
chcp 65001 >nul
title Atualizando o IPED-PCBA
echo Atualizando o IPED-PCBA da versao {atual} para a {nova_v}.
echo Esperando o painel fechar...
set N=0
:esperar
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if errorlevel 1 goto fechou
timeout /t 1 /nobreak >nul
goto esperar
:fechou
rem espera a janela do instalar.bat fechar tambem
timeout /t 2 /nobreak >nul
:trocar
move "{repo}" "{bk}" >nul 2>&1
if not errorlevel 1 goto mover
set /a N+=1
if %N% GEQ 90 goto falhou
timeout /t 1 /nobreak >nul
goto trocar
:mover
move "{nova}" "{repo}" >nul 2>&1
if not errorlevel 1 goto pronto
move "{bk}" "{repo}" >nul 2>&1
goto falhou
:pronto
del "{marca}" >nul 2>&1
echo Pronto. A versao anterior ficou em {bk}
cd /d "{repo}"
start "" "{repo}\instalar.bat"
exit /b 0
:falhou
echo.
echo Nao consegui trocar a pasta {repo}.
echo Algum programa esta com um arquivo dela aberto. Feche as janelas dessa pasta e rode de novo:
echo   {arq}
echo Nada foi perdido: o painel continua na versao {atual}.
pause
exit /b 1
""".format(atual=__version__, nova_v=p["versao"], pid=int(pid), repo=REPO, bk=bk, nova=nova,
           marca=_arq_pronta(), arq=os.path.join(_casa(), "atualizar.bat"))
        with open(arq, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(texto)
    else:
        arq = os.path.join(_casa(), "atualizar.sh")
        texto = """#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 1; done
if mv "{repo}" "{bk}"; then
  if mv "{nova}" "{repo}"; then
    rm -f "{marca}"
    echo "IPED-PCBA atualizado para a {nova_v}. A versão anterior ficou em {bk}. Abra o painel de novo."
    exit 0
  fi
  mv "{bk}" "{repo}"
fi
echo "Não consegui trocar a pasta {repo}. O painel continua na versão {atual}."
exit 1
""".format(pid=int(pid), repo=REPO, bk=bk, nova=nova, marca=_arq_pronta(), nova_v=p["versao"], atual=__version__)
        with open(arq, "w", encoding="utf-8") as f:
            f.write(texto)
    return arq, bk


def iniciar_troca(pid):
    """Dispara o script de troca, solto do painel, e devolve para onde vai a versão atual."""
    arq, bk = script_troca(pid)
    if WIN:
        # janela própria, para o analista ver a troca; cwd fora do pacote para não prender a pasta
        subprocess.Popen(["cmd", "/c", "start", "Atualizando o IPED-PCBA", "cmd", "/c", arq], cwd=_casa(),
                         creationflags=0x08000000, close_fds=True)
    else:
        with open(os.path.join(_casa(), "atualizar.log"), "a") as log:
            subprocess.Popen(["sh", arq], cwd=_casa(), stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
    return {"anterior": bk, "script": arq, "reabre": WIN}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="iped_pcba.atualizacao")
    ap.add_argument("acao", choices=["verificar", "baixar"])
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if a.acao == "verificar":
        print(json.dumps(verificar(forcar=True), indent=2, ensure_ascii=False))
        return 0
    try:
        baixar(lambda *x: print(*x, flush=True))
    except Exception as e:
        print("ERRO:", e, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
