"""Painel IPED-PCBA: página local (só nesta máquina) que conduz o analista por todo o fluxo.

  1. Máquina e configuração: diagnóstico, plano editável, aplicar com backup, desfazer.
  2. Processar evidências: escolhe evidência, pasta do caso e perfil; roda o IPED e mostra o log.
  3. Casos: abre no IPED, escolhe o caso que a IA vai ler, confere o log de auditoria.
  4. IA (MCP): escrita liberada ou não, liga o MCP ao Claude Desktop, LM Studio e Hermes,
     procura IA local (Ollama, LM Studio) e testa o MCP.
  5. Relatório técnico do caso.
  Visão do caso: gráficos do caso processado, alertas e sugestões (visao.py).

Segurança: escuta só em 127.0.0.1, numa porta livre, e toda chamada precisa do código
aleatório que vai na URL aberta pelo próprio painel. Só usa a biblioteca padrão, para rodar
com o Python que vem dentro do IPED.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, assistente, auditoria, clientesia, contexto, multicasos, perfis, processar, skills
from .configurar import PASTA_PCBA, gravar_texto, ler_chaves, ler_texto, listar_backups
from .configurar import reverter as reverter_backup
from .mcp import (CASO_ATIVO, PASTA_MCP, achar_java, definir_escrita, escrita_ativa,
                  localizar_pacote)
from .recomendar import Alteracao

PACOTE = os.path.dirname(os.path.abspath(__file__))
WIN = os.name == "nt"
PASTA_APP = PASTA_PCBA + "/app"

_BAT_PAINEL = r"""@echo off
rem Gerado pelo instalador IPED-PCBA. Abre o painel IPED-PCBA no navegador.
cd /d "%~dp0"
"%~dp0..\python\python.exe" -c "import sys; sys.path.insert(0, r'%~dp0app'); from iped_pcba.cli import main; sys.exit(main())" painel --iped "%~dp0.."
if errorlevel 1 pause
"""

_SH_PAINEL = """#!/usr/bin/env bash
# Gerado pelo instalador IPED-PCBA. Abre o painel IPED-PCBA no navegador.
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/../python/bin/python3"; [ -x "$PY" ] || PY=python3
exec "$PY" -c "import sys; sys.path.insert(0, '$DIR/app'); from iped_pcba.cli import main; sys.exit(main())" painel --iped "$DIR/.." "$@"
"""


def instalar_painel(raiz, so, backup):
    """Copia o painel para <IPED>/pcba/app e cria <IPED>/pcba/painel-pcba.bat (ou .sh).

    Assim o painel continua funcionando mesmo se a pasta baixada do GitHub for apagada."""
    destino = os.path.join(raiz, PASTA_APP, "iped_pcba")
    if os.path.normcase(os.path.abspath(destino)) != os.path.normcase(PACOTE):
        backup.proteger(PASTA_APP)
        if os.path.isdir(destino):
            shutil.rmtree(destino)
        shutil.copytree(PACOTE, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    nome = "painel-pcba.bat" if so == "windows" else "painel-pcba.sh"
    relativo = PASTA_PCBA + "/" + nome
    backup.proteger(relativo)
    caminho = os.path.join(raiz, relativo)
    if so == "windows":
        gravar_texto(caminho, _BAT_PAINEL.replace("\n", "\r\n"))
    else:
        gravar_texto(caminho, _SH_PAINEL)
        os.chmod(caminho, 0o755)
    return [PASTA_APP, relativo]


def _python_iped(raiz):
    for p in (os.path.join(raiz, "python", "python.exe"), os.path.join(raiz, "python", "bin", "python3")):
        if os.path.isfile(p):
            return p
    return sys.executable


def _boot(modulo, *args):
    pai = os.path.dirname(PACOTE)
    return ["-c", "import sys; sys.path.insert(0, r'{}'); from iped_pcba.{} import main; "
                  "sys.exit(main())".format(pai, modulo)] + list(args)


FILTROS = {
    None: "Evidências|*.e01;*.ex01;*.dd;*.raw;*.img;*.001;*.iso;*.ufdr;*.zip;*.ad1;*.aff;*.vmdk;*.vhd;"
          "*.vhdx;*.dmg|Todos os arquivos|*.*",
    "csv": "Planilhas CSV|*.csv;*.txt|Todos os arquivos|*.*",
    "imagem": "Imagens|*.jpg;*.jpeg;*.png",
    "todos": "Todos os arquivos|*.*",
    "contexto": "Documentos|*.txt;*.md;*.csv;*.tsv;*.json;*.xml;*.html;*.htm;*.log;*.eml;*.rtf;*.docx;*.odt;*.ods;"
                "*.xlsx;*.pptx;*.pdf|Todos os arquivos|*.*",
}


# Janela-dona invisível, sempre no topo e ativada antes do diálogo: sem ela o diálogo
# nasce atrás do navegador (o processo do PowerShell não tem foco) e parece que nada abriu.
_DONO = ("Add-Type -AssemblyName System.Windows.Forms;"
         "$f=New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false;"
         "StartPosition='Manual';Location=New-Object System.Drawing.Point(-32000,-32000);"
         "Size=New-Object System.Drawing.Size(1,1);FormBorderStyle='None';Opacity=0};"
         "$f.Show();$f.Activate();")


def escolher(tipo, titulo="", multiplos=False, filtro=None):
    """Janela nativa de escolha de pasta/arquivo. Devolve lista de caminhos ([] se cancelar)."""
    if WIN:
        if tipo == "pasta":
            ps = _DONO + ("$d=New-Object System.Windows.Forms.FolderBrowserDialog;$d.Description='{t}';"
                  "$d.ShowNewFolderButton=$true;"
                  "if($d.ShowDialog($f) -eq 'OK'){{[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                  "$d.SelectedPath}};$f.Close()").format(t=titulo.replace("'", ""))
        else:
            ps = _DONO + ("$d=New-Object System.Windows.Forms.OpenFileDialog;$d.Title='{t}';"
                  "$d.Multiselect=${m};"
                  "$d.Filter='{filtro}';"
                  "if($d.ShowDialog($f) -eq 'OK'){{[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                  "$d.FileNames}};$f.Close()").format(t=titulo.replace("'", ""), m="true" if multiplos else "false",
                                                   filtro=FILTROS.get(filtro, FILTROS[None]))
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                           capture_output=True, timeout=600, creationflags=0x08000000)
        return [l.strip() for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--title=" + titulo]
        if tipo == "pasta":
            cmd.append("--directory")
        if multiplos:
            cmd += ["--multiple", "--separator=\n"]
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        return [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    raise RuntimeError("Sem janela de escolha nesta máquina; digite o caminho.")


class Estado(object):
    def __init__(self, raiz):
        self.raiz = os.path.abspath(raiz) if raiz else None
        self.token = secrets.token_urlsafe(24)
        self.tarefas = processar.Tarefas()
        self.ultimo = None  # (maquina, plano) do último diagnóstico
        self.lock = threading.Lock()
        self.conversas = assistente.Conversas()
        self.fila = []          # indexação de vários casos, um depois do outro
        self.fila_grupo = None

    # ------------------------------------------------------------ visão geral
    def resumo(self):
        from .localizar import eh_instalacao, versao_de
        raiz = self.raiz
        out = {"versao_painel": __version__, "raiz": raiz, "so": "windows" if WIN else "linux"}
        if not raiz or not eh_instalacao(raiz):
            out["iped_ok"] = False
            return out
        out["iped_ok"] = True
        out["versao_iped"] = versao_de(raiz)
        out["backups"] = listar_backups(raiz)
        out["configurado"] = os.path.isfile(os.path.join(raiz, PASTA_PCBA, "maquina.json"))
        lanc = os.path.normpath(os.path.join(raiz, PASTA_MCP,
                                             "iped-pcba-mcp.bat" if WIN else "iped-pcba-mcp.sh"))
        out["mcp"] = {"instalado": os.path.isfile(lanc), "lancador": lanc,
                      "escrita": escrita_ativa(raiz),
                      "pacote": bool(localizar_pacote(os.path.dirname(os.path.dirname(PACOTE))))}
        out["perfis"] = processar.perfis(raiz)
        from .perfis import ajuda
        out["perfis_ajuda"] = [ajuda(p) for p in out["perfis"]]
        out["casos"] = processar.casos()
        out["caso_ativo"] = ler_texto(CASO_ATIVO).strip() if os.path.isfile(CASO_ATIVO) else None
        out["tarefas"] = self.tarefas.listar()
        out["clientes"] = clientesia.situacao(lanc)
        out["atalho"] = os.path.isfile(_atalho())
        return out

    # ------------------------------------------------------------ configuração
    def diagnosticar(self, d):
        from .cli import _args, _plano
        argv = ["diagnosticar", "--iped", self.raiz]
        if d.get("temp"):
            argv += ["--temp", d["temp"]]
        if d.get("saida_ssd"):
            argv.append("--saida-ssd")
        if d.get("servidor_transcricao"):
            argv += ["--servidor-transcricao", d["servidor_transcricao"]]
        args = _args(argv)
        maquina, plano = _plano(args)
        with self.lock:
            self.ultimo = (maquina, plano)
        atuais = {}
        for a in plano.alteracoes:
            cam = os.path.join(self.raiz, a.arquivo)
            if a.arquivo not in atuais:
                atuais[a.arquivo] = ler_chaves(ler_texto(cam)) if os.path.isfile(cam) else {}
        alts = [dict(a.como_dict(), atual=atuais[a.arquivo].get(a.chave)) for a in plano.alteracoes]
        java, maior = achar_java("windows" if WIN else "linux",
                                 localizar_pacote(os.path.dirname(os.path.dirname(PACOTE))))
        return {"maquina": maquina, "heap_gb": plano.heap_gb, "transcricao": plano.transcricao,
                "alteracoes": alts, "avisos": plano.avisos, "java21": java,
                "pacotes_python": maquina.get("iped", {}).get("pacotes_python")}

    def aplicar(self, d):
        from .cli import executar_aplicacao
        with self.lock:
            if not self.ultimo:
                raise ValueError("Rode o diagnóstico antes de aplicar.")
            maquina, plano = self.ultimo
        escolhidas = d.get("alteracoes")
        if escolhidas is not None:  # o usuário pode desmarcar ou editar valores
            plano.alteracoes = [Alteracao(a["arquivo"], a["chave"], a["valor"], a.get("motivo", ""))
                                for a in escolhidas]
        r = executar_aplicacao(self.raiz, maquina, plano, perfis=d.get("perfis", True),
                               mcp=d.get("mcp", True), escrita=d.get("escrita", True))
        return r

    def reverter(self, d):
        nome, arquivos = reverter_backup(self.raiz, d.get("backup") or None)
        return {"backup": nome, "restaurados": arquivos}

    # ------------------------------------------------------------ processamento
    def _comando(self, d):
        evid = [e for e in (d.get("evidencias") or []) if e.strip()]
        saida = (d.get("saida") or "").strip()
        extras = ["--continue"] if d.get("continuar") else []
        if d.get("portavel"):
            extras.append("--portable")
        cmd = processar.comando_processar(self.raiz, evid, saida, perfil=d.get("perfil") or None,
                                          adicionar=bool(d.get("adicionar")) or bool(d.get("continuar")),
                                          fuso=d.get("fuso") or "GMT-3", extras=extras)
        return evid, saida, cmd

    def processar(self, d, depois=None):
        evid, saida, cmd = self._comando(d)
        aviso_perfil = perfis.atualizar_se_preciso(self.raiz, d.get("perfil") or "")

        def fim(codigo):
            if codigo == 0 or processar.eh_caso(saida):
                processar.registrar_caso(saida, "processado no painel", evid)
            if depois:
                depois(codigo)
        tid = self.tarefas.iniciar("processar", "Processar " + os.path.basename(saida.rstrip("\\/")),
                                   cmd, cwd=self.raiz, ao_terminar=fim)
        return {"tarefa": tid, "comando": cmd, "aviso": aviso_perfil}

    # ------------------------------------------------------------ fila (indexação multicase)
    def fila_adicionar(self, d):
        _, saida, _ = self._comando(d)       # valida evidências e pasta já ao pôr na fila
        with self.lock:
            if any(os.path.normcase(os.path.abspath(j["saida"])) == os.path.normcase(os.path.abspath(saida))
                   and j["estado"] in ("aguardando", "rodando") for j in self.fila):
                raise ValueError("Esta pasta de caso já está na fila.")
            self.fila.append({"id": "{}".format(len(self.fila) + 1), "saida": saida, "estado": "aguardando",
                              "tarefa": None, "pedido": {k: d.get(k) for k in
                                                         ("evidencias", "saida", "perfil", "fuso", "portavel")}})
        return self.fila_ler()

    def fila_remover(self, d):
        with self.lock:
            self.fila = [j for j in self.fila if not (j["id"] == d.get("id") and j["estado"] != "rodando")]
        return self.fila_ler()

    def fila_iniciar(self, d):
        self.fila_grupo = (d.get("grupo") or "").strip() or None
        self._fila_proxima()
        return self.fila_ler()

    def _fila_proxima(self):
        with self.lock:
            if any(j["estado"] == "rodando" for j in self.fila):
                return
            prox = next((j for j in self.fila if j["estado"] == "aguardando"), None)
            if prox:
                prox["estado"] = "rodando"
        if not prox:
            ok = [j["saida"] for j in self.fila if j["estado"] == "ok"]
            if self.fila_grupo and len(ok) >= 2:
                from . import multicasos
                multicasos.salvar_grupo(self.fila_grupo, ok)
                self.fila_grupo = None
            return

        def depois(codigo, j=prox):
            j["estado"] = "ok" if codigo == 0 else "erro"
            self._fila_proxima()
        try:
            prox["tarefa"] = self.processar(prox["pedido"], depois)["tarefa"]
        except Exception as e:  # pasta ocupada desde que entrou na fila, evidência sumiu...
            prox["estado"], prox["erro"] = "erro", str(e)
            self._fila_proxima()

    def fila_ler(self):
        out = []
        for j in self.fila:
            x = {k: j.get(k) for k in ("id", "saida", "estado", "tarefa", "erro")}
            x["evidencias"] = j["pedido"].get("evidencias")
            x["perfil"] = j["pedido"].get("perfil")
            if j["tarefa"] and j["estado"] == "rodando":
                try:
                    p = self.tarefas.progresso(j["tarefa"])
                    x["percentual"], x["restante_s"], x["fase"] = p["percentual"], p["restante_s"], p["fase"]
                except Exception:
                    pass
            out.append(x)
        return {"fila": out, "grupo": self.fila_grupo}

    def whisper(self, d):
        cmd = [_python_iped(self.raiz)] + _boot("componentes", "whisper")
        return {"tarefa": self.tarefas.iniciar("componente", "Instalar faster-whisper", cmd)}

    # ------------------------------------------------------------ casos
    def caso_adicionar(self, d):
        pasta = (d.get("pasta") or "").strip()
        if not processar.eh_caso(pasta):
            raise ValueError("Esta pasta não é um caso do IPED (faltam iped/index, iped/data, iped/lib).")
        processar.registrar_caso(pasta, "adicionado pelo usuário")
        return {"ok": True}

    def caso_ativar(self, d):
        pasta = (d.get("pasta") or "").strip()
        if not processar.eh_caso(pasta):
            raise ValueError("Esta pasta não é um caso do IPED.")
        gravar_texto(CASO_ATIVO, os.path.abspath(pasta))
        return {"caso_ativo": os.path.abspath(pasta)}

    def auditoria(self, pasta):
        arq = os.path.join(pasta, "iped-pcba-auditoria", "mcp-auditoria.jsonl")
        if not os.path.isfile(arq):
            return {"arquivo": arq, "existe": False}
        n, problemas = auditoria.verificar(arq)
        linhas = ler_texto(arq).splitlines()[-100:]
        regs = []
        for l in reversed(linhas):
            try:
                o = json.loads(l)
            except ValueError:
                continue
            regs.append({k: o.get(k) for k in ("seq", "ts", "usuario", "ferramenta", "argumentos",
                                               "situacao", "detalhe", "duracao_ms")})
        return {"arquivo": arq, "existe": True, "registros": n, "problemas": problemas,
                "integra": not problemas, "ultimos": regs}

    # ------------------------------------------------------------ visão do caso
    def visao_ler(self, caso):
        from . import visao
        r = self.resumo()
        clientes = r.get("clientes") or []
        amb = {"mcp": (r.get("mcp") or {}).get("instalado"),
               "ia_ligada": any(c.get("aponta_para_este") for c in clientes)}
        out = visao.ler(caso, amb)
        out["mcp_instalado"] = bool(amb["mcp"])
        return out

    def visao_atualizar(self, caso):
        from . import visao
        r = self.resumo()
        if not r["mcp"]["instalado"]:
            raise ValueError("O MCP não está instalado: aplique a configuração com o pacote completo (passo 1).")
        cmd = visao.comando_exportar(r["mcp"]["lancador"], caso)
        return {"tarefa": self.tarefas.iniciar("visao", "Números do caso " + os.path.basename(caso.rstrip("\\/")),
                                               cmd, cwd=caso)}

    # ------------------------------------------------------------ assistente (agentes)
    def assist_agentes(self):
        from . import agentes
        r = self.resumo()
        return {"agentes": agentes.para_painel(), "config": assistente.ler_config(),
                "ia_local": clientesia.ia_local(), "escrita": (r.get("mcp") or {}).get("escrita"),
                "mcp_instalado": (r.get("mcp") or {}).get("instalado"), "clientes": r.get("clientes")}

    def assist_enviar(self, d):
        r = self.resumo()
        if not r["mcp"]["instalado"]:
            raise ValueError("O MCP não está instalado: aplique a configuração com o pacote completo (passo 1).")
        caso = _caso_valido(d)
        itens = contexto.ler_lista(caso) if d.get("usar_contexto", True) else []
        cid = self.conversas.iniciar(r["mcp"]["lancador"], caso, d.get("agente"), d.get("pergunta"),
                                     assistente.ler_config(), bool(r["mcp"]["escrita"]), itens)
        return {"id": cid}

    # ------------------------------------------------------------ IA
    def ia(self):
        return {"local": clientesia.ia_local()}

    def testar_mcp(self, d):
        from .mcpcliente import ClienteMcp, ErroMcp
        r = self.resumo()
        if not r["mcp"]["instalado"]:
            raise ValueError("O MCP não está instalado. Aplique a configuração com o pacote completo.")
        lanc = r["mcp"]["lancador"]
        cmd = [lanc]
        caso = d.get("caso") or r.get("caso_ativo")
        if caso:
            cmd += ["--case", caso]
        cli = ClienteMcp(cmd, timeout=180)
        try:
            info = cli.iniciar()
            fs = cli.ferramentas()
            out = {"servidor": (info or {}).get("serverInfo"), "ferramentas": len(fs),
                   "escrita_visivel": sorted(f for f in fs if f in (
                       "add_to_bookmark", "set_item_checked", "remove_from_bookmark",
                       "set_bookmark_comment", "bookmark_search_results"))}
            if caso:
                res = cli.ferramenta("get_case_summary")
                out["resumo_caso"] = res["texto"][:3000]
            return out
        except ErroMcp as e:
            raise ValueError(str(e))
        finally:
            cli.fechar()


def _atalho():
    return os.path.join(os.path.expanduser("~"), "Desktop", "Painel IPED-PCBA.lnk")


def criar_atalho(raiz):
    if not WIN:
        raise ValueError("Atalho só no Windows.")
    alvo = os.path.join(raiz, PASTA_PCBA, "painel-pcba.bat")
    if not os.path.isfile(alvo):
        raise ValueError("Aplique a configuração antes (ela cria o painel dentro do IPED).")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');$s.TargetPath='{alvo}';"
          "$s.WorkingDirectory='{dir}';$s.WindowStyle=7;$s.Description='Painel IPED-PCBA';$s.Save()"
          ).format(lnk=_atalho().replace("'", "''"), alvo=alvo.replace("'", "''"),
                   dir=os.path.dirname(alvo).replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=60,
                   creationflags=0x08000000)
    return {"atalho": _atalho()}


# ---------------------------------------------------------------- servidor HTTP

def _handler(estado, html):
    class H(BaseHTTPRequestHandler):
        server_version = "PainelPCBA"

        def log_message(self, *a):
            pass

        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _json(self, codigo, obj):
            dados = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._host_ok():
                return self._json(403, {"erro": "host"})
            if u.path == "/":
                if q.get("t", [""])[0] != estado.token:
                    return self._json(403, {"erro": "Abra o painel pelo atalho ou pelo instalar.bat."})
                dados = html.replace("__TOKEN__", estado.token).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                 "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(dados)
                return
            return self._json(404, {"erro": "não encontrado"})

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-Token") != estado.token:
                return self._json(403, {"erro": "acesso negado"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                d = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"erro": "JSON inválido"})
            rota = urlparse(self.path).path
            try:
                r = _rotear(estado, rota, d)
            except KeyError as e:
                return self._json(404, {"erro": "não encontrado: {}".format(e)})
            except PermissionError as e:
                return self._json(400, {"erro": "Sem permissão para gravar em {}. Feche o IPED; "
                                                "se o IPED estiver em Program Files, rode como "
                                                "administrador.".format(e.filename)})
            except (ValueError, RuntimeError, OSError) as e:
                return self._json(400, {"erro": str(e)})
            except Exception as e:  # mostra no painel em vez de derrubar
                return self._json(500, {"erro": "{}: {}".format(type(e).__name__, e)})
            return self._json(200, r)
    return H


def _rotear(e, rota, d):
    if rota == "/api/resumo":
        return e.resumo()
    if rota == "/api/trocar-iped":
        from .localizar import eh_instalacao
        if not eh_instalacao(d.get("raiz", "")):
            raise ValueError("Pasta sem IPEDConfig.txt e iped.jar.")
        e.raiz = os.path.abspath(d["raiz"])
        e.ultimo = None
        return e.resumo()
    if rota == "/api/localizar":
        from .localizar import localizar_iped
        return {"instalacoes": localizar_iped()}
    if rota == "/api/diagnosticar":
        return e.diagnosticar(d)
    if rota == "/api/aplicar":
        return e.aplicar(d)
    if rota == "/api/reverter":
        return e.reverter(d)
    if rota == "/api/escolher":
        return {"caminhos": escolher(d.get("tipo", "pasta"), d.get("titulo", ""),
                                     bool(d.get("multiplos")), d.get("filtro"))}
    if rota == "/api/processar":
        return e.processar(d)
    if rota == "/api/fila/ler":
        return e.fila_ler()
    if rota == "/api/fila/adicionar":
        return e.fila_adicionar(d)
    if rota == "/api/fila/remover":
        return e.fila_remover(d)
    if rota == "/api/fila/iniciar":
        return e.fila_iniciar(d)
    if rota == "/api/multi/grupos":
        return {"grupos": multicasos.grupos()}
    if rota == "/api/multi/salvar":
        return {"grupos": multicasos.salvar_grupo(d.get("nome"), [_caso_valido({"caso": c}) for c in d.get("casos") or []])}
    if rota == "/api/multi/remover":
        return {"grupos": multicasos.remover_grupo(d.get("nome"))}
    if rota == "/api/multi/abrir":
        return multicasos.abrir_no_iped(d.get("casos") or [])
    if rota == "/api/multi/cruzar":
        r = multicasos.cruzar([_caso_valido({"caso": c}) for c in d.get("casos") or []])
        r["relatorio"] = multicasos.salvar_relatorio(r)
        r["texto"] = multicasos.relatorio_md(r)
        return r
    if rota == "/api/multi/abrir-pasta":
        os.makedirs(multicasos.PASTA_SAIDA, exist_ok=True)
        return {"aberto": _abrir_local(multicasos.PASTA_SAIDA)}
    if rota == "/api/whisper":
        return e.whisper(d)
    if rota == "/api/tarefa":
        return e.tarefas.ler_log(d["id"], int(d.get("desde") or 0))
    if rota == "/api/tarefa/progresso":
        return e.tarefas.progresso(d["id"])
    if rota == "/api/parar":
        return {"parado": e.tarefas.parar(d["id"])}
    if rota == "/api/caso/adicionar":
        return e.caso_adicionar(d)
    if rota == "/api/caso/esquecer":
        processar.esquecer_caso(d["pasta"])
        return {"ok": True}
    if rota == "/api/caso/abrir":
        return {"aberto": processar.abrir_caso(d["pasta"])}
    if rota == "/api/caso/ativar":
        return e.caso_ativar(d)
    if rota == "/api/caso/auditoria":
        return e.auditoria(d["pasta"])
    if rota == "/api/ia":
        return e.ia()
    if rota == "/api/ia/escrita":
        return {"escrita": definir_escrita(e.raiz, bool(d.get("ativa")))}
    if rota == "/api/ia/configurar":
        r = e.resumo()
        return clientesia.configurar(d["cliente"], r["mcp"]["lancador"])
    if rota == "/api/ia/remover":
        return clientesia.remover(d["cliente"])
    if rota == "/api/ia/testar":
        return e.testar_mcp(d)
    if rota == "/api/assist/agentes":
        return e.assist_agentes()
    if rota == "/api/assist/config":
        return {"config": assistente.gravar_config(d)}
    if rota == "/api/assist/enviar":
        return e.assist_enviar(d)
    if rota == "/api/assist/ler":
        return e.conversas.ler(d["id"], int(d.get("desde") or 0))
    if rota == "/api/assist/parar":
        e.conversas.parar(d["id"])
        return {"ok": True}
    if rota == "/api/assist/salvar":
        return {"arquivo": assistente.salvar(_caso_valido(d), d.get("agente") or "Assistente", d.get("pergunta") or "",
                                             d.get("resposta") or "", d.get("modelo") or "", d.get("contexto"))}
    if rota == "/api/contexto/ler":
        return contexto.situacao(_caso_valido(d))
    if rota == "/api/contexto/adicionar":
        contexto.adicionar(_caso_valido(d), d.get("caminhos") or [])
        return contexto.situacao(_caso_valido(d))
    if rota == "/api/contexto/remover":
        contexto.remover(_caso_valido(d), d.get("caminho") or "")
        return contexto.situacao(_caso_valido(d))
    if rota == "/api/skills/ler":
        return skills.situacao()
    if rota == "/api/skills/instalar":
        return {"feito": skills.instalar(d.get("destinos"))}
    if rota == "/api/skills/abrir":
        os.makedirs(skills.ZIPS, exist_ok=True)
        return {"aberto": _abrir_local(skills.ZIPS)}
    if rota == "/api/contexto/preparar":
        return contexto.preparar(_caso_valido(d))
    if rota == "/api/contexto/abrir":
        return {"aberto": _abrir_local(os.path.join(_caso_valido(d), "iped-pcba-ia"))}
    if rota == "/api/contexto/copiado":
        contexto.registrar_copia(_caso_valido(d), str(d.get("destino") or "IA na nuvem")[:80])
        return {"ok": True}
    if rota == "/api/visao/ler":
        return e.visao_ler(_caso_valido(d))
    if rota == "/api/visao/atualizar":
        return e.visao_atualizar(_caso_valido(d))
    if rota.startswith("/api/rt/") or rota.startswith("/api/unidade/"):
        return _rotear_rt(rota, d)
    if rota == "/api/atalho":
        return criar_atalho(e.raiz)
    if rota == "/api/sair":
        threading.Thread(target=e.servidor.shutdown, daemon=True).start()
        return {"ok": True}
    raise KeyError(rota)


def _caso_valido(d):
    caso = os.path.abspath(d.get("caso") or "")
    if not processar.eh_caso(caso):
        raise ValueError("Escolha um caso processado pelo IPED.")
    return caso


def _rotear_rt(rota, d):
    """Relatório técnico do caso: rascunho em <caso>/iped-pcba-relatorio/rt.json."""
    from . import rt
    from .cli import incorporar_telematica
    if rota == "/api/unidade/ler":
        return {"unidade": rt.ler_unidade(), "arquivo": rt.ARQ_UNIDADE}
    if rota == "/api/unidade/gravar":
        u = d.get("unidade") or {}
        if u.get("logo") and not os.path.isfile(u["logo"]):
            raise ValueError("Logotipo não encontrado: " + u["logo"])
        return {"unidade": rt.gravar_unidade(u)}
    caso = _caso_valido(d)
    if rota == "/api/rt/ler":
        dados = rt.ler_rt(caso)
        docx = os.path.join(caso, rt.PASTA_CASO, "RT.docx")
        return {"dados": dados, "campos": rt.CAMPOS, "lacunas": rt.lacunas(dados, rt.ler_unidade()),
                "listas": rt.lista_de_arquivos(caso), "docx": docx if os.path.isfile(docx) else None,
                "pasta": os.path.join(caso, rt.PASTA_CASO)}
    if rota == "/api/rt/gravar":
        rt.gravar_rt(caso, d.get("dados") or {})
        return _rotear_rt("/api/rt/ler", {"caso": caso})
    if rota == "/api/rt/telematica":
        if not os.path.isfile(d.get("registros") or ""):
            raise ValueError("Escolha o CSV de registros telemáticos.")
        _, info = incorporar_telematica(caso, d["registros"], d.get("investigados") or {})
        r = _rotear_rt("/api/rt/ler", {"caso": caso})
        r["importacao"] = {k: info[k] for k in ("registros", "rejeitadas", "contas", "provedores")}
        return r
    if rota == "/api/rt/hash":
        arq = d.get("arquivo") or ""
        if not os.path.isfile(arq):
            raise ValueError("Arquivo não encontrado: " + arq)
        dados = rt.ler_rt(caso)
        linha = "{} — SHA-256: {}".format(os.path.basename(arq), rt.sha256(arq))
        dados["hashes"] = [h for h in dados.get("hashes") or [] if "[" not in h and
                           not h.startswith(os.path.basename(arq) + " —")] + [linha]
        rt.gravar_rt(caso, dados)
        return _rotear_rt("/api/rt/ler", {"caso": caso})
    if rota == "/api/rt/gerar":
        if d.get("dados") is not None:
            rt.gravar_rt(caso, d["dados"])
        saida = os.path.join(caso, rt.PASTA_CASO, "RT.docx")
        try:
            rt.gerar_docx(rt.ler_rt(caso), saida, rt.ler_unidade())
        except PermissionError:
            raise ValueError("Não consegui gravar o RT.docx: feche o arquivo no Word e tente de novo.")
        return {"docx": saida}
    if rota == "/api/rt/abrir":
        alvo = os.path.join(caso, rt.PASTA_CASO, "RT.docx" if d.get("o") == "docx" else "")
        if not os.path.exists(alvo):
            raise ValueError("Ainda não existe: " + alvo)
        return {"aberto": _abrir_local(alvo)}
    raise KeyError(rota)


def _abrir_local(alvo):
    """Abre arquivo ou pasta no programa padrão desta máquina."""
    if WIN:
        os.startfile(alvo)  # noqa
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", alvo])
    return alvo


def servir(raiz, porta=0, navegador=True):
    estado = Estado(raiz)
    html = ler_texto(os.path.join(PACOTE, "painel.html"))
    srv = ThreadingHTTPServer(("127.0.0.1", porta), _handler(estado, html))
    estado.servidor = srv
    url = "http://127.0.0.1:{}/?t={}".format(srv.server_address[1], estado.token)
    print("Painel IPED-PCBA aberto em:\n  {}\nDeixe esta janela aberta enquanto usa o painel. "
          "Para encerrar, feche-a ou use o botão Sair do painel.".format(url), flush=True)
    if navegador:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
