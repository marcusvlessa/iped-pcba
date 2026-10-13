"""Processamento (indexação) de evidências pelo IPED e tarefas longas do painel.

Cada tarefa roda num processo separado, com a saída gravada em
~/.iped-pcba/painel/tarefas/<id>.log, e continua rodando mesmo se o painel for fechado.
Os casos processados pelo painel ficam listados em ~/.iped-pcba/painel/casos.json.
"""

import datetime
import json
import os
import subprocess
import threading

from .configurar import gravar_texto, ler_texto

PASTA = os.path.join(os.path.expanduser("~"), ".iped-pcba", "painel")
WIN = os.name == "nt"


def _pasta(*p):
    d = os.path.join(PASTA, *p)
    os.makedirs(d, exist_ok=True)
    return d


def java_do_iped(raiz):
    exe = os.path.join(raiz, "jre", "bin", "java.exe" if WIN else "java")
    return exe if os.path.isfile(exe) else "java"


def perfis(raiz):
    pasta = os.path.join(raiz, "profiles")
    if not os.path.isdir(pasta):
        return []
    nomes = sorted(p for p in os.listdir(pasta) if os.path.isdir(os.path.join(pasta, p)))
    # perfis da PCBA primeiro
    return [p for p in nomes if p.startswith("pcba-")] + [p for p in nomes if not p.startswith("pcba-")]


def eh_caso(pasta):
    return all(os.path.isdir(os.path.join(pasta, "iped", d)) for d in ("index", "data", "lib"))


def heap_gb(raiz):
    try:
        dados = json.loads(ler_texto(os.path.join(raiz, "pcba", "maquina.json")))
        return int(dados["plano"]["heap_gb"])
    except Exception:
        return None


def comando_processar(raiz, evidencias, saida, perfil=None, adicionar=False, heap=None,
                      fuso="GMT-3", extras=None):
    """Linha de comando do IPED para processar as evidências."""
    if not evidencias:
        raise ValueError("Informe ao menos uma evidência.")
    for e in evidencias:
        if not os.path.exists(e):
            raise ValueError("Evidência não encontrada: " + e)
    if not saida:
        raise ValueError("Informe a pasta do caso.")
    if os.path.isdir(saida) and os.listdir(saida) and not adicionar:
        if eh_caso(saida):
            raise ValueError("A pasta do caso já tem um caso. Marque 'acrescentar ao caso' "
                             "ou escolha outra pasta.")
        raise ValueError("A pasta do caso não está vazia. Escolha uma pasta nova.")
    cmd = [java_do_iped(raiz), "-jar", os.path.join(raiz, "iped.jar")]
    heap = heap or heap_gb(raiz)
    if heap:
        # o IPED exige -Xmx depois do iped.jar: ele repassa ao processo filho que processa
        cmd.append("-Xmx{}g".format(heap))
    for e in evidencias:
        cmd += ["-d", e]
    cmd += ["-o", saida, "--nogui"]
    if perfil:
        cmd += ["-profile", perfil]
    if fuso:
        cmd += ["-tz", fuso]
    if adicionar:
        cmd.append("--append")
    cmd += list(extras or [])
    return cmd


def abrir_caso(caso):
    """Abre o caso na interface de análise do IPED."""
    exe = os.path.join(caso, "IPED-SearchApp.exe")
    flags = 0x00000008 if WIN else 0  # DETACHED_PROCESS
    if WIN and os.path.isfile(exe):
        subprocess.Popen([exe], cwd=caso, creationflags=flags)
        return exe
    jar = os.path.join(caso, "iped", "lib", "iped-search-app.jar")
    java = os.path.join(caso, "iped", "jre", "bin", "java.exe" if WIN else "java")
    if not os.path.isfile(java):
        java = "java"
    if not os.path.isfile(jar):
        raise ValueError("Não achei a interface do IPED neste caso: " + caso)
    subprocess.Popen([java, "-jar", jar], cwd=caso, creationflags=flags,
                     start_new_session=not WIN)
    return jar


# ------------------------------------------------------------------ casos conhecidos

def _arq_casos():
    return os.path.join(_pasta(), "casos.json")


def casos():
    try:
        lista = json.loads(ler_texto(_arq_casos()))
    except Exception:
        lista = []
    for c in lista:
        c["existe"] = eh_caso(c["pasta"])
        aud = os.path.join(c["pasta"], "iped-pcba-auditoria", "mcp-auditoria.jsonl")
        c["auditoria"] = aud if os.path.isfile(aud) else None
    return lista


def registrar_caso(pasta, origem="painel", evidencias=None):
    pasta = os.path.abspath(pasta)
    lista = [c for c in casos() if os.path.normcase(c["pasta"]) != os.path.normcase(pasta)]
    lista.insert(0, {"pasta": pasta, "nome": os.path.basename(pasta.rstrip("\\/")),
                     "origem": origem, "evidencias": evidencias or [],
                     "registrado": datetime.datetime.now().isoformat(timespec="seconds")})
    for c in lista:
        c.pop("existe", None)
        c.pop("auditoria", None)
    gravar_texto(_arq_casos(), json.dumps(lista[:100], indent=2, ensure_ascii=False))


def esquecer_caso(pasta):
    lista = [c for c in casos() if os.path.normcase(c["pasta"]) != os.path.normcase(pasta)]
    for c in lista:
        c.pop("existe", None)
        c.pop("auditoria", None)
    gravar_texto(_arq_casos(), json.dumps(lista, indent=2, ensure_ascii=False))


# ------------------------------------------------------------------ tarefas

class Tarefas(object):
    """Processos longos (IPED, pip, testes) com log em arquivo."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lista = {}

    def iniciar(self, tipo, titulo, cmd, cwd=None, ao_terminar=None, env=None):
        with self._lock:
            agora = datetime.datetime.now()
            tid = "{}-{}".format(agora.strftime("%Y%m%d-%H%M%S"), len(self._lista) + 1)
            log = os.path.join(_pasta("tarefas"), tid + ".log")
            arq = open(log, "w", encoding="utf-8", errors="replace")
            arq.write("$ " + " ".join('"{}"'.format(c) if " " in c else c for c in cmd) + "\n\n")
            arq.flush()
            flags = 0x08000000 if WIN else 0  # sem janela de console
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=arq, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=flags, env=env)
            t = {"id": tid, "tipo": tipo, "titulo": titulo, "log": log, "proc": proc,
                 "inicio": agora.isoformat(timespec="seconds"), "fim": None, "codigo": None,
                 "arq": arq}
            self._lista[tid] = t

        def esperar():
            codigo = proc.wait()
            t["codigo"] = codigo
            t["fim"] = datetime.datetime.now().isoformat(timespec="seconds")
            arq.write("\n[fim: código {}]\n".format(codigo))
            arq.close()
            if ao_terminar:
                try:
                    ao_terminar(codigo)
                except Exception:
                    pass
        threading.Thread(target=esperar, daemon=True).start()
        return tid

    def parar(self, tid):
        t = self._lista.get(tid)
        if t and t["codigo"] is None:
            t["proc"].terminate()
            return True
        return False

    def _publico(self, t):
        p = {k: t[k] for k in ("id", "tipo", "titulo", "log", "inicio", "fim", "codigo")}
        p["rodando"] = t["codigo"] is None
        return p

    def listar(self):
        return [self._publico(t) for t in sorted(self._lista.values(), key=lambda x: x["id"],
                                                  reverse=True)]

    def ler_log(self, tid, desde=0, maximo=200000):
        t = self._lista.get(tid)
        if not t:
            raise KeyError(tid)
        with open(t["log"], "rb") as f:
            f.seek(desde)
            dados = f.read(maximo)
        return {"texto": dados.decode("utf-8", "replace"), "pos": desde + len(dados),
                "tarefa": self._publico(t)}
