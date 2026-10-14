"""Assistente do painel: envia a pergunta de um agente para a IA local e deixa a IA consultar o caso
pelas ferramentas do MCP, mostrando cada passo.

IA local suportada (nada sai da máquina):
  - Ollama            http://127.0.0.1:11434   (API /api/chat com ferramentas)
  - LM Studio e outros compatíveis com OpenAI   (API /v1/chat/completions com ferramentas)

Cada chamada de ferramenta passa pelo MCP e fica no log de auditoria do caso, como qualquer outra.
A conversa termina numa resposta em texto, que o analista pode copiar ou salvar no caso.
"""

import datetime
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import agentes, contexto as ctx
from .configurar import gravar_texto, ler_texto
from .mcpcliente import ClienteMcp, ErroMcp

ARQ_CONFIG = os.path.join(os.path.expanduser("~"), ".iped-pcba", "ia.json")
PASTA_CONVERSAS = os.path.join("iped-pcba-ia", "conversas")
MAX_PASSOS = 12
MAX_RESULTADO = 6000  # caracteres de cada resultado de ferramenta entregues ao modelo
TIMEOUT_MODELO = 900  # CPU sem GPU pode levar minutos por resposta


# ------------------------------------------------------------------ configuração da IA local

def ler_config(arquivo=None):
    try:
        c = json.loads(ler_texto(arquivo or ARQ_CONFIG))
    except (OSError, ValueError):
        c = {}
    return {"tipo": c.get("tipo") or "ollama", "url": c.get("url") or "", "modelo": c.get("modelo") or ""}


def gravar_config(c, arquivo=None):
    tipo = c.get("tipo") or "ollama"
    if tipo not in ("ollama", "openai"):
        raise ValueError("Tipo de IA desconhecido: " + tipo)
    url = (c.get("url") or "").strip().rstrip("/")
    if url and not url_local(url):
        raise ValueError("Só IA local (127.0.0.1 ou localhost) pode ser usada pelo painel. Para IA na nuvem, "
                         "copie a pergunta para o programa ligado ao MCP.")
    dados = {"tipo": tipo, "url": url, "modelo": (c.get("modelo") or "").strip()}
    arquivo = arquivo or ARQ_CONFIG
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    gravar_texto(arquivo, json.dumps(dados, ensure_ascii=False, indent=1))
    return dados


def url_local(url):
    try:
        u = urllib.parse.urlsplit(url)
        return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost") and not u.username
    except ValueError:
        return False


def url_padrao(tipo):
    return "http://127.0.0.1:11434" if tipo == "ollama" else "http://127.0.0.1:1234"


# ------------------------------------------------------------------ modelos

def _post(url, corpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca passa por proxy
    try:
        with abridor.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")[:500]
        if "does not support tools" in texto or "tool" in texto.lower() and e.code == 400:
            raise RuntimeError("Este modelo não aceita ferramentas. Escolha um modelo com suporte a ferramentas "
                               "(por exemplo qwen2.5, qwen3, llama3.1 ou mistral-nemo).")
        raise RuntimeError("A IA local respondeu com erro {}: {}".format(e.code, texto))
    except urllib.error.URLError as e:
        raise RuntimeError("Não consegui falar com a IA local em {} ({}). Ela está aberta?".format(url, e.reason))


def _ferramentas_para_modelo(ferramentas):
    return [{"type": "function", "function": {
        "name": f["name"], "description": (f.get("description") or "")[:1500],
        "parameters": f.get("inputSchema") or {"type": "object", "properties": {}}}} for f in ferramentas]


class ModeloOllama(object):
    def __init__(self, url, modelo):
        self.url, self.modelo = (url or url_padrao("ollama")).rstrip("/"), modelo

    def responder(self, mensagens, ferramentas):
        r = _post(self.url + "/api/chat", {"model": self.modelo, "messages": mensagens, "stream": False,
                                           "tools": _ferramentas_para_modelo(ferramentas),
                                           "options": {"temperature": 0.2}}, TIMEOUT_MODELO)
        m = r.get("message") or {}
        chamadas = []
        for i, c in enumerate(m.get("tool_calls") or []):
            f = c.get("function") or {}
            args = f.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            chamadas.append({"id": "c{}".format(i), "nome": f.get("name"), "args": args})
        return m.get("content") or "", chamadas, m

    def resultado(self, chamada, texto):
        return {"role": "tool", "content": texto, "tool_name": chamada["nome"]}


class ModeloOpenAI(object):
    def __init__(self, url, modelo):
        self.url, self.modelo = (url or url_padrao("openai")).rstrip("/"), modelo

    def responder(self, mensagens, ferramentas):
        r = _post(self.url + "/v1/chat/completions", {"model": self.modelo, "messages": mensagens,
                                                      "tools": _ferramentas_para_modelo(ferramentas),
                                                      "temperature": 0.2}, TIMEOUT_MODELO)
        m = ((r.get("choices") or [{}])[0]).get("message") or {}
        chamadas = []
        for c in m.get("tool_calls") or []:
            f = c.get("function") or {}
            try:
                args = json.loads(f.get("arguments") or "{}")
            except ValueError:
                args = {}
            chamadas.append({"id": c.get("id"), "nome": f.get("name"), "args": args})
        msg = {"role": "assistant", "content": m.get("content") or ""}
        if m.get("tool_calls"):
            msg["tool_calls"] = m["tool_calls"]
        return m.get("content") or "", chamadas, msg

    def resultado(self, chamada, texto):
        return {"role": "tool", "tool_call_id": chamada["id"], "content": texto}


def modelo_de(config):
    if not config.get("modelo"):
        raise ValueError("Escolha o modelo de IA local (Ollama ou LM Studio) antes de enviar.")
    if config.get("url") and not url_local(config["url"]):
        raise ValueError("Só IA local (127.0.0.1 ou localhost) pode ser usada pelo painel.")
    return (ModeloOllama if config["tipo"] == "ollama" else ModeloOpenAI)(config.get("url"), config["modelo"])


# ------------------------------------------------------------------ conversa

def executar(modelo, mcp, agente, pergunta, ao_evento, escrita=False, parar=lambda: False, contexto=None):
    """Laço da conversa: modelo pede ferramentas, MCP responde, até o modelo dar a resposta final.

    contexto (ctx.Contexto): arquivos que o analista anexou; vão na pergunta ou viram ferramentas locais.

    ao_evento(dict) recebe cada passo: tipo = pensando | ferramenta | resultado | resposta | erro.
    Devolve o texto final.
    """
    permitidas = set(agente["ferramentas"])
    todas = mcp.ferramentas_completas()
    ferramentas = [f for f in todas if f["name"] in permitidas]
    if agente.get("escrita") and not escrita:
        ao_evento({"tipo": "aviso", "texto": "A escrita no caso está desligada (passo IA/MCP). Este agente só vai "
                                             "consultar; marcar ou escrever no RT não vai funcionar."})
    locais = set()
    if contexto is not None and not contexto.vazio():
        pergunta = pergunta + "\n\n" + contexto.apresentacao()
        if contexto.total() > ctx.JUNTO_NA_PERGUNTA:
            ferramentas = ferramentas + ctx.FERRAMENTAS
            locais = set(ctx.NOMES)
    mensagens = [{"role": "system", "content": agentes.sistema(agente)}, {"role": "user", "content": pergunta}]
    for passo in range(MAX_PASSOS):
        if parar():
            raise RuntimeError("Conversa interrompida.")
        ao_evento({"tipo": "pensando", "passo": passo + 1})
        texto, chamadas, msg = modelo.responder(mensagens, ferramentas)
        mensagens.append(msg)
        if not chamadas:
            ao_evento({"tipo": "resposta", "texto": texto})
            return texto
        for c in chamadas:
            ao_evento({"tipo": "ferramenta", "nome": c["nome"], "args": c["args"]})
            if c["nome"] in locais:
                saida = contexto.ferramenta(c["nome"], c["args"])
            elif c["nome"] not in permitidas:
                saida = "Ferramenta não permitida para este agente: {}".format(c["nome"])
            else:
                try:
                    r = mcp.ferramenta(c["nome"], c["args"])
                    saida = r["texto"]
                except ErroMcp as e:
                    saida = "Erro do MCP: {}".format(e)
            ao_evento({"tipo": "resultado", "nome": c["nome"], "tamanho": len(saida),
                       "trecho": saida[:400]})
            if len(saida) > MAX_RESULTADO:
                saida = saida[:MAX_RESULTADO] + "\n[... resultado cortado em {} caracteres; peça menos itens ou " \
                                                 "leia um item por vez]".format(MAX_RESULTADO)
            mensagens.append(modelo.resultado(c, saida))
    mensagens.append({"role": "user", "content": "Pare de consultar e responda agora com o que já encontrou."})
    texto, _, _ = modelo.responder(mensagens, [])
    ao_evento({"tipo": "resposta", "texto": texto})
    return texto


class Conversas(object):
    """Conversas rodando em segundo plano; o painel lê os eventos aos poucos."""

    def __init__(self):
        self._c = {}
        self._lock = threading.Lock()
        self._n = 0

    def iniciar(self, lancador, caso, agente_id, pergunta, config, escrita, contexto_itens=None):
        agente = agentes.por_id(agente_id)
        if not (pergunta or "").strip():
            raise ValueError("Escreva a pergunta.")
        modelo = modelo_de(config)
        with self._lock:
            self._n += 1
            cid = "c{}".format(self._n)
            conv = {"id": cid, "agente": agente["nome"], "pergunta": pergunta, "caso": caso,
                    "modelo": config["modelo"], "inicio": datetime.datetime.now().isoformat(timespec="seconds"),
                    "eventos": [], "rodando": True, "resposta": None, "parar": False, "contexto": []}
            self._c[cid] = conv

        def evento(e):
            e["t"] = time.time()
            with self._lock:
                conv["eventos"].append(e)

        def rodar():
            mcp = None
            try:
                c = None
                if contexto_itens:
                    evento({"tipo": "aviso", "texto": "Lendo os arquivos de contexto…"})
                    c = ctx.Contexto(contexto_itens)
                    conv["contexto"] = c.para_registro()
                    evento({"tipo": "aviso", "texto": "{} arquivo(s) de contexto lidos ({} caracteres).".format(
                        len(c.textos), c.total())})
                    for arq, motivo in c.problemas[:10]:
                        evento({"tipo": "aviso", "texto": "Contexto não lido: {} ({})".format(arq, motivo)})
                evento({"tipo": "aviso", "texto": "Abrindo o caso no MCP…"})
                mcp = ClienteMcp([lancador, "--case", caso], timeout=600)
                mcp.iniciar()
                conv["resposta"] = executar(modelo, mcp, agente, pergunta, evento, escrita,
                                            parar=lambda: conv["parar"], contexto=c)
            except Exception as ex:  # mostra no painel
                evento({"tipo": "erro", "texto": str(ex)})
            finally:
                if mcp:
                    mcp.fechar()
                conv["rodando"] = False
        threading.Thread(target=rodar, daemon=True).start()
        return cid

    def ler(self, cid, desde=0):
        with self._lock:
            c = self._c.get(cid)
            if not c:
                raise ValueError("Conversa não encontrada.")
            return {"eventos": c["eventos"][desde:], "pos": len(c["eventos"]), "rodando": c["rodando"],
                    "resposta": c["resposta"], "contexto": c["contexto"]}

    def parar(self, cid):
        with self._lock:
            if cid in self._c:
                self._c[cid]["parar"] = True


def salvar(caso, agente_nome, pergunta, resposta, modelo, contexto=None):
    """Grava a conversa em <caso>/iped-pcba-ia/conversas/<data>-<agente>.md e devolve o caminho."""
    agora = datetime.datetime.now()
    pasta = os.path.join(caso, PASTA_CONVERSAS)
    os.makedirs(pasta, exist_ok=True)
    nome = "{}-{}.md".format(agora.strftime("%Y%m%d-%H%M%S"),
                             "".join(ch if ch.isalnum() else "-" for ch in agente_nome.lower()).strip("-"))
    caminho = os.path.join(pasta, nome)
    anexos = "".join("- {}\n".format(x) for x in (contexto or []))
    gravar_texto(caminho, "# {}\n\nData: {}  \nModelo: {} (IA local)  \nCaso: {}\n\n## Pergunta\n\n{}\n\n"
                          "{}## Resposta da IA (revisar antes de usar)\n\n{}\n".format(
                              agente_nome, agora.strftime("%d/%m/%Y %H:%M"), modelo, caso, pergunta,
                              "## Arquivos de contexto lidos pela IA\n\n" + anexos + "\n" if anexos else "",
                              resposta or ""))
    return caminho
