"""Liga o MCP do IPED aos programas de IA da máquina e procura servidores de IA local.

Clientes suportados:
  - Claude Desktop  (claude_desktop_config.json, chave mcpServers)
  - LM Studio       (~/.lmstudio/mcp.json, mesmo formato)
  - Hermes Agent    (~/.hermes/config.yaml, chave mcp_servers)

Antes de alterar um arquivo, uma cópia fica ao lado (<arquivo>.bak-pcba-<data-hora>).
Só a entrada "iped-pcba" é criada ou trocada; o resto do arquivo fica como estava.
"""

import json
import os
import re
import shutil
import sys
import urllib.request

from .configurar import carimbo, gravar_texto, ler_texto

NOME = "iped-pcba"


def _home():
    return os.path.expanduser("~")


def caminho_cliente(cliente):
    h = _home()
    if cliente == "claude":
        if os.name == "nt":
            return os.path.join(os.environ.get("APPDATA") or os.path.join(h, "AppData", "Roaming"),
                                "Claude", "claude_desktop_config.json")
        if sys.platform == "darwin":
            return os.path.join(h, "Library", "Application Support", "Claude",
                                "claude_desktop_config.json")
        return os.path.join(h, ".config", "Claude", "claude_desktop_config.json")
    if cliente == "lmstudio":
        return os.path.join(h, ".lmstudio", "mcp.json")
    if cliente == "hermes":
        return os.path.join(h, ".hermes", "config.yaml")
    raise ValueError(cliente)


def _instalado(cliente):
    """O programa parece instalado? (a pasta de configuração existe)"""
    return os.path.isdir(os.path.dirname(caminho_cliente(cliente)))


def _copia(caminho):
    if os.path.isfile(caminho):
        destino, n = "{}.bak-pcba-{}".format(caminho, carimbo()), 1
        while os.path.exists(destino):
            n += 1
            destino = "{}.bak-pcba-{}-{}".format(caminho, carimbo(), n)
        shutil.copy2(caminho, destino)
        return destino
    return None


# ------------------------------------------------------------------ JSON (Claude, LM Studio)

def ler_json(caminho):
    if not os.path.isfile(caminho):
        return {}
    texto = ler_texto(caminho).strip()
    return json.loads(texto) if texto else {}


def mesclar_json(dados, comando, args):
    dados = dict(dados or {})
    servidores = dict(dados.get("mcpServers") or {})
    servidores[NOME] = {"command": comando, "args": list(args)}
    dados["mcpServers"] = servidores
    return dados


def remover_json(dados):
    dados = dict(dados or {})
    servidores = dict(dados.get("mcpServers") or {})
    servidores.pop(NOME, None)
    dados["mcpServers"] = servidores
    return dados


# ------------------------------------------------------------------ YAML (Hermes), sem PyYAML

def _q(s):
    return json.dumps(s, ensure_ascii=False)  # string JSON é YAML válido


def bloco_hermes(comando, args, recuo=2):
    r = " " * recuo
    return [r + "{}:".format(NOME),
            r * 2 + "command: {}".format(_q(comando)),
            r * 2 + "args: [{}]".format(", ".join(_q(a) for a in args))]


def mesclar_yaml(texto, comando, args):
    """Cria ou troca mcp_servers.iped-pcba num config.yaml, mexendo só nesse trecho."""
    linhas = (texto or "").splitlines()
    topo = next((i for i, l in enumerate(linhas) if re.match(r"^mcp_servers:\s*(#.*)?$", l)), None)
    if topo is None:
        if any(re.match(r"^mcp_servers:", l) for l in linhas):
            raise ValueError("mcp_servers no formato em linha ({}); edite à mão".format(
                "mcp_servers: {...}"))
        if linhas and linhas[-1].strip():
            linhas.append("")
        return "\n".join(linhas + ["mcp_servers:"] + bloco_hermes(comando, args)) + "\n"
    # fim da seção mcp_servers: próxima linha não vazia sem recuo
    fim = len(linhas)
    for j in range(topo + 1, len(linhas)):
        if linhas[j].strip() and not linhas[j][0].isspace() and not linhas[j].lstrip().startswith("#"):
            fim = j
            break
    secao = linhas[topo + 1:fim]
    recuo = next((len(l) - len(l.lstrip()) for l in secao
                  if l.strip() and not l.lstrip().startswith("#")), 2)
    novo = bloco_hermes(comando, args, recuo)
    ini = None
    for k, l in enumerate(secao):
        if re.match(r"^\s{%d}%s:\s*$" % (recuo, re.escape(NOME)), l):
            ini = k
            break
    if ini is None:
        secao = secao + novo
    else:
        k = ini + 1
        while k < len(secao) and (not secao[k].strip() or
                                  len(secao[k]) - len(secao[k].lstrip()) > recuo):
            k += 1
        secao = secao[:ini] + novo + secao[k:]
    return "\n".join(linhas[:topo + 1] + secao + linhas[fim:]) + "\n"


def remover_yaml(texto):
    linhas = (texto or "").splitlines()
    saida, pulando, recuo = [], False, 0
    for l in linhas:
        m = re.match(r"^(\s+)%s:\s*$" % re.escape(NOME), l)
        if m:
            pulando, recuo = True, len(m.group(1))
            continue
        if pulando and (not l.strip() or len(l) - len(l.lstrip()) > recuo):
            continue
        pulando = False
        saida.append(l)
    # seção mcp_servers vazia vira nula no YAML; tira o cabeçalho
    limpo = []
    for i, l in enumerate(saida):
        if re.match(r"^mcp_servers:\s*$", l):
            resto = [x for x in saida[i + 1:] if x.strip()]
            if not resto or not resto[0][0].isspace():
                continue
        limpo.append(l)
    while limpo and not limpo[-1].strip():
        limpo.pop()
    return "\n".join(limpo) + "\n"


# ------------------------------------------------------------------ operações

def situacao(lancador):
    """Para cada cliente: instalado? configurado? apontando para este lançador?"""
    out = []
    for c, rotulo in (("claude", "Claude Desktop"), ("lmstudio", "LM Studio"),
                      ("hermes", "Hermes Agent")):
        cam = caminho_cliente(c)
        item = {"cliente": c, "nome": rotulo, "arquivo": cam, "instalado": _instalado(c),
                "configurado": False, "aponta_para_este": False}
        try:
            if c == "hermes":
                txt = ler_texto(cam) if os.path.isfile(cam) else ""
                m = re.search(r"^\s+%s:\s*\n\s+command:\s*(.+)$" % re.escape(NOME), txt, re.M)
                if m:
                    item["configurado"] = True
                    cmd = m.group(1).strip()
                    try:
                        cmd = json.loads(cmd)
                    except ValueError:
                        cmd = cmd.strip("'\"")
                    item["aponta_para_este"] = os.path.normcase(cmd) == os.path.normcase(lancador or "")
            else:
                ent = (ler_json(cam).get("mcpServers") or {}).get(NOME)
                if ent:
                    item["configurado"] = True
                    item["aponta_para_este"] = (os.path.normcase(ent.get("command", ""))
                                                == os.path.normcase(lancador or ""))
        except Exception as e:  # arquivo corrompido: mostra, não quebra o painel
            item["erro"] = str(e)
        out.append(item)
    return out


def configurar(cliente, lancador, args=None):
    """Grava a entrada iped-pcba no cliente. Devolve {arquivo, copia}."""
    args = list(args or [])
    cam = caminho_cliente(cliente)
    if cliente == "hermes":
        texto = ler_texto(cam) if os.path.isfile(cam) else ""
        novo = mesclar_yaml(texto, lancador, args)
    else:
        novo = json.dumps(mesclar_json(ler_json(cam), lancador, args), indent=2, ensure_ascii=False) + "\n"
    copia = _copia(cam)
    gravar_texto(cam, novo)
    return {"arquivo": cam, "copia": copia}


def remover(cliente):
    cam = caminho_cliente(cliente)
    if not os.path.isfile(cam):
        return {"arquivo": cam, "copia": None}
    if cliente == "hermes":
        novo = remover_yaml(ler_texto(cam))
    else:
        novo = json.dumps(remover_json(ler_json(cam)), indent=2, ensure_ascii=False) + "\n"
    copia = _copia(cam)
    gravar_texto(cam, novo)
    return {"arquivo": cam, "copia": copia}


# ------------------------------------------------------------------ IA local

SERVIDORES_LOCAIS = (
    ("Ollama", "http://127.0.0.1:11434/api/tags", "models", "name"),
    ("LM Studio", "http://127.0.0.1:1234/v1/models", "data", "id"),
)


def ia_local(timeout=1.5):
    """Servidores de IA rodando nesta máquina e os modelos que oferecem."""
    achados = []
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for nome, url, lista, campo in SERVIDORES_LOCAIS:
        item = {"nome": nome, "url": url.rsplit("/", 2)[0], "ativo": False, "modelos": []}
        try:
            with abridor.open(url, timeout=timeout) as r:
                dados = json.loads(r.read().decode("utf-8"))
            item["ativo"] = True
            item["modelos"] = [m.get(campo) for m in dados.get(lista, []) if m.get(campo)]
        except Exception:
            pass
        achados.append(item)
    return achados
