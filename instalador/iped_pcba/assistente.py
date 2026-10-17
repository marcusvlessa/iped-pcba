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

from . import agentes, contexto as ctx, ialocal
from .configurar import gravar_texto, ler_texto
from .mcpcliente import ClienteMcp, ErroMcp

ARQ_CONFIG = os.path.join(os.path.expanduser("~"), ".iped-pcba", "ia.json")
PASTA_CONVERSAS = os.path.join("iped-pcba-ia", "conversas")
MAX_PASSOS = 12
MAX_RESULTADO = 6000  # caracteres de cada resultado de ferramenta entregues ao modelo
TIMEOUT_MODELO = 900  # CPU sem GPU pode levar minutos por resposta
# Sem num_ctx o Ollama usa 2048-4096 tokens e descarta em silêncio o começo da conversa (o papel do agente).
NUM_CTX = 16384
MANTER_RESULTADOS = 6   # resultados de ferramenta mais recentes que vão inteiros ao modelo
RESUMO_ANTIGO = 600     # os mais antigos encolhem para este tamanho


# ------------------------------------------------------------------ configuração da IA local

def ler_config(arquivo=None):
    try:
        c = json.loads(ler_texto(arquivo or ARQ_CONFIG))
    except (OSError, ValueError):
        c = {}
    return {"tipo": c.get("tipo") or "auto", "url": c.get("url") or "", "modelo": c.get("modelo") or ""}


def gravar_config(c, arquivo=None):
    tipo = c.get("tipo") or "auto"
    if tipo not in ("auto", "ollama", "openai"):
        raise ValueError("Tipo de IA desconhecido: " + tipo)
    url = (c.get("url") or "").strip().rstrip("/")
    if url and not url_local(url):
        raise ValueError("Só IA local (127.0.0.1 ou localhost) pode ser usada pelo painel. Para IA na nuvem, "
                         "copie a pergunta para o programa ligado ao MCP.")
    dados = {"tipo": tipo, "url": url, "modelo": (c.get("modelo") or "").strip()}
    if tipo == "auto":
        dados.update(url="", modelo="")
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

def _abrir(url, corpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca passa por proxy
    try:
        return abridor.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")[:500]
        if "does not support tools" in texto or "tool" in texto.lower() and e.code == 400:
            raise RuntimeError("Este modelo não aceita ferramentas. Escolha um modelo com suporte a ferramentas "
                               "(por exemplo qwen2.5, qwen3, llama3.1 ou mistral-nemo).")
        raise RuntimeError("A IA local respondeu com erro {}: {}".format(e.code, texto))
    except urllib.error.URLError as e:
        raise RuntimeError("Não consegui falar com a IA local em {} ({}). Ela está aberta?".format(url, e.reason))


def _post(url, corpo, timeout):
    with _abrir(url, corpo, timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _linhas(url, corpo, timeout):
    """Resposta em partes (stream): uma linha JSON por vez, como o Ollama e o LM Studio mandam."""
    with _abrir(url, corpo, timeout) as r:
        for linha in r:
            linha = linha.decode("utf-8", "replace").strip()
            if linha.startswith("data:"):  # formato OpenAI (SSE)
                linha = linha[5:].strip()
            if not linha or linha == "[DONE]":
                continue
            try:
                yield json.loads(linha)
            except ValueError:
                continue


def _compactar(mensagens, manter=MANTER_RESULTADOS, curto=RESUMO_ANTIGO):
    """Encolhe os resultados de ferramenta antigos para a conversa caber na janela do modelo.
    O papel do agente, a pergunta e os resultados recentes ficam inteiros."""
    resultados = [m for m in mensagens if m.get("role") == "tool"]
    for m in resultados[:-manter] if manter else resultados:
        c = m.get("content") or ""
        if len(c) > curto and not m.get("_encolhido"):
            m["content"] = c[:curto] + "\n[... resultado antigo encurtado; consulte de novo se precisar]"
            m["_encolhido"] = True
    return [{k: v for k, v in m.items() if k != "_encolhido"} for m in mensagens]


def _ferramentas_para_modelo(ferramentas):
    return [{"type": "function", "function": {
        "name": f["name"], "description": (f.get("description") or "")[:1500],
        "parameters": f.get("inputSchema") or {"type": "object", "properties": {}}}} for f in ferramentas]


class ModeloOllama(object):
    def __init__(self, url, modelo):
        self.url, self.modelo = (url or url_padrao("ollama")).rstrip("/"), modelo

    def responder(self, mensagens, ferramentas, ao_trecho=None):
        """ao_trecho(texto_ate_agora): a resposta aparece no painel enquanto o modelo escreve."""
        corpo = {"model": self.modelo, "messages": mensagens, "stream": ao_trecho is not None,
                 "tools": _ferramentas_para_modelo(ferramentas),
                 "options": {"temperature": 0.2, "num_ctx": NUM_CTX}}
        if ao_trecho is None:
            m = _post(self.url + "/api/chat", corpo, TIMEOUT_MODELO).get("message") or {}
        else:
            texto, pedidas = "", []
            for parte in _linhas(self.url + "/api/chat", corpo, TIMEOUT_MODELO):
                pm = parte.get("message") or {}
                if pm.get("content"):
                    texto += pm["content"]
                    ao_trecho(texto)
                pedidas += pm.get("tool_calls") or []
                if parte.get("error"):
                    raise RuntimeError("A IA local respondeu com erro: {}".format(parte["error"]))
            m = {"role": "assistant", "content": texto}
            if pedidas:
                m["tool_calls"] = pedidas
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

    def responder(self, mensagens, ferramentas, ao_trecho=None):
        corpo = {"model": self.modelo, "messages": mensagens, "tools": _ferramentas_para_modelo(ferramentas),
                 "temperature": 0.2}
        if ao_trecho is None:
            r = _post(self.url + "/v1/chat/completions", corpo, TIMEOUT_MODELO)
            m = ((r.get("choices") or [{}])[0]).get("message") or {}
        else:
            corpo["stream"] = True
            texto, pedidas = "", {}
            for parte in _linhas(self.url + "/v1/chat/completions", corpo, TIMEOUT_MODELO):
                esc = (parte.get("choices") or [{}])[0]
                d = esc.get("delta") or esc.get("message") or {}  # servidor que ignora o stream manda tudo junto
                if d.get("content"):
                    texto += d["content"]
                    ao_trecho(texto)
                for c in d.get("tool_calls") or []:  # chegam em pedaços, juntados pelo índice
                    k = c.get("index", len(pedidas))
                    t = pedidas.setdefault(k, {"id": "c{}".format(k), "type": "function",
                                               "function": {"name": "", "arguments": ""}})
                    t["id"] = c.get("id") or t["id"]
                    f = c.get("function") or {}
                    t["function"]["name"] += f.get("name") or ""
                    t["function"]["arguments"] += f.get("arguments") or ""
            m = {"content": texto}
            if pedidas:
                m["tool_calls"] = [pedidas[k] for k in sorted(pedidas)]
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

def executar(modelo, mcp, agente, pergunta, ao_evento, escrita=False, parar=lambda: False, contexto=None,
            ao_trecho=None):
    """Laço da conversa: modelo pede ferramentas, MCP responde, até o modelo dar a resposta final.

    contexto (ctx.Contexto): arquivos que o analista anexou; vão na pergunta ou viram ferramentas locais.

    ao_evento(dict) recebe cada passo: tipo = pensando | ferramenta | resultado | resposta | erro.
    ao_trecho(texto), se dado, recebe o texto que o modelo está escrevendo, antes de o passo terminar.
    Devolve o texto final.
    """
    todas = mcp.ferramentas_completas()
    permitidas = {f["name"] for f in todas} if agente["ferramentas"] == "todas" else set(agente["ferramentas"])
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
    for passo in range(agente.get("passos") or MAX_PASSOS):
        if parar():
            raise RuntimeError("Conversa interrompida.")
        ao_evento({"tipo": "pensando", "passo": passo + 1})
        texto, chamadas, msg = _responder(modelo, _compactar(mensagens), ferramentas, ao_trecho)
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
    texto, _, _ = _responder(modelo, _compactar(mensagens), [], ao_trecho)
    ao_evento({"tipo": "resposta", "texto": texto})
    return texto


def _responder(modelo, mensagens, ferramentas, ao_trecho):
    if ao_trecho is None:
        return modelo.responder(mensagens, ferramentas)
    try:
        return modelo.responder(mensagens, ferramentas, ao_trecho)
    finally:
        ao_trecho("")  # o texto parcial some quando o passo termina


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
        if config.get("url") and not url_local(config["url"]):
            raise ValueError("Só IA local (127.0.0.1 ou localhost) pode ser usada pelo painel.")
        with self._lock:
            self._n += 1
            cid = "c{}".format(self._n)
            conv = {"id": cid, "agente": agente["nome"], "pergunta": pergunta, "caso": caso,
                    "modelo": config.get("modelo") or "", "inicio": datetime.datetime.now().isoformat(timespec="seconds"),
                    "eventos": [], "rodando": True, "resposta": None, "parar": False, "contexto": [],
                    "parcial": ""}
            self._c[cid] = conv

        def evento(e):
            e["t"] = time.time()
            with self._lock:
                conv["eventos"].append(e)

        def rodar():
            mcp = None
            try:
                evento({"tipo": "aviso", "texto": "Procurando a IA local…"})
                cfg = ialocal.preparar(config, lambda t: evento({"tipo": "aviso", "texto": t}))
                modelo = modelo_de(cfg)
                conv["modelo"] = cfg["modelo"]
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
                                            parar=lambda: conv["parar"], contexto=c,
                                            ao_trecho=lambda t: conv.__setitem__("parcial", t))
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
                    "resposta": c["resposta"], "contexto": c["contexto"], "modelo": c["modelo"],
                    "parcial": c["parcial"] if c["rodando"] else ""}

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
