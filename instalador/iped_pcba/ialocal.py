"""IA local nesta máquina: Ollama e LM Studio.

Acha os dois mesmo com o servidor desligado, lista os modelos baixados, liga o servidor quando o analista
manda uma pergunta e escolhe sozinho um modelo que aceita ferramentas (tool use) se nenhum foi escolhido.
Só fala com 127.0.0.1: nada sai da máquina. Só a biblioteca padrão.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request

WIN = os.name == "nt"
OLLAMA_URL = "http://127.0.0.1:11434"
LMSTUDIO_URL = "http://127.0.0.1:1234"

# Famílias que aceitam ferramentas, da preferida para a menos indicada. O nome do modelo é comparado sem
# separadores, então "Qwen2.5-7B-Instruct", "qwen2.5:7b" e "lmstudio-community/Qwen2.5-7B" casam com "qwen2.5".
PREFERIDOS = ("qwen3", "qwen2.5", "llama3.3", "llama3.1", "llama3.2", "mistralnemo", "mistralsmall", "mistral",
              "gptoss", "gemma3", "granite", "hermes", "phi4", "command")
NAO_CONVERSA = ("embed", "nomic", "bge", "rerank", "whisper", "clip")


def _home():
    return os.path.expanduser("~")


def _sem_proxy():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get_json(url, timeout=1.5):
    with _sem_proxy().open(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _norm(nome):
    return re.sub(r"[^a-z0-9.]", "", (nome or "").lower()).replace("meta", "")


def conversa(nome):
    """Modelo de conversa (não é de embeddings, reranking, áudio...)."""
    n = (nome or "").lower()
    return bool(n) and not any(x in n for x in NAO_CONVERSA)


def nota(nome):
    """Quanto menor, melhor para o assistente. Modelos fora da lista ficam no fim, mas ainda servem."""
    n = _norm(nome)
    for i, fam in enumerate(PREFERIDOS):
        if fam in n:
            return i
    return len(PREFERIDOS)


def com_ferramentas(nome):
    return conversa(nome) and nota(nome) < len(PREFERIDOS)


def escolher(modelos):
    ok = [m for m in modelos if conversa(m)]
    return sorted(ok, key=lambda m: (nota(m), ok.index(m)))[0] if ok else ""


# ------------------------------------------------------------------ Ollama

def ollama_exe():
    c = shutil.which("ollama")
    if c:
        return c
    if WIN:
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(p):
            return p
    return None


def ollama_baixados():
    """Modelos baixados pelo Ollama, lidos do disco (funciona com o Ollama fechado)."""
    base = os.environ.get("OLLAMA_MODELS") or os.path.join(_home(), ".ollama", "models")
    lib = os.path.join(base, "manifests", "registry.ollama.ai")
    out = []
    for cam in sorted(glob.glob(os.path.join(lib, "*", "*", "*"))):
        if os.path.isfile(cam):
            dono, nome, tag = cam.split(os.sep)[-3:]
            out.append("{}:{}".format(nome if dono == "library" else dono + "/" + nome, tag))
    return out


# ------------------------------------------------------------------ LM Studio

def _pastas_lmstudio():
    h = _home()
    return [os.path.join(h, ".lmstudio"), os.path.join(h, ".cache", "lm-studio")]


def lms_cli():
    """Linha de comando do LM Studio (lms), que liga o servidor e carrega modelos."""
    c = shutil.which("lms")
    if c:
        return c
    for p in _pastas_lmstudio():
        cam = os.path.join(p, "bin", "lms.exe" if WIN else "lms")
        if os.path.isfile(cam):
            return cam
    return None


def lmstudio_app():
    if WIN:
        base = os.environ.get("LOCALAPPDATA", "")
        for p in (os.path.join(base, "Programs", "LM Studio", "LM Studio.exe"),
                  os.path.join(base, "Programs", "lm-studio", "LM Studio.exe"),
                  os.path.join(base, "LM-Studio", "LM Studio.exe")):
            if os.path.isfile(p):
                return p
    return None


def lmstudio_instalado():
    return bool(lms_cli() or lmstudio_app() or any(os.path.isdir(p) for p in _pastas_lmstudio()))


def _pastas_modelos_lmstudio():
    pastas = []
    for p in _pastas_lmstudio():
        try:
            with open(os.path.join(p, "settings.json"), encoding="utf-8") as f:
                d = json.load(f).get("downloadsFolder")
            if d:
                pastas.append(d)
        except (OSError, ValueError, AttributeError):
            pass
        pastas.append(os.path.join(p, "models"))
    return [p for i, p in enumerate(pastas) if os.path.isdir(p) and p not in pastas[:i]]


def lmstudio_baixados():
    """Modelos baixados no LM Studio. Usa o lms quando existe (dá o nome que a API aceita); senão lê a pasta
    de modelos (inclusive a que o analista trocou nas configurações do LM Studio)."""
    cli = lms_cli()
    if cli:
        try:
            r = subprocess.run([cli, "ls", "--json"], capture_output=True, text=True, timeout=30,
                               encoding="utf-8", errors="replace")
            dados = json.loads(r.stdout or "[]")
            out = [m.get("modelKey") or m.get("path") for m in dados
                   if isinstance(m, dict) and m.get("type", "llm") == "llm"]
            out = [m for m in out if m]
            if out:
                return out
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    out = []
    for pasta in _pastas_modelos_lmstudio():
        for raiz, _, arqs in os.walk(pasta):
            if any(a.lower().endswith((".gguf", ".safetensors")) for a in arqs):
                rel = os.path.relpath(raiz, pasta).replace(os.sep, "/")
                if rel != "." and rel not in out:
                    out.append(rel)
    return [m for m in out if conversa(m)]


# ------------------------------------------------------------------ situação e servidor

def servidores(timeout=1.5, baixados=True):
    """Ollama e LM Studio nesta máquina: se estão instalados, se o servidor está ligado e os modelos."""
    out = []
    for nome, tipo, url, rota, lista, campo in (
            ("Ollama", "ollama", OLLAMA_URL, "/api/tags", "models", "name"),
            ("LM Studio", "openai", LMSTUDIO_URL, "/v1/models", "data", "id")):
        s = {"nome": nome, "tipo": tipo, "url": url, "ativo": False, "modelos": []}
        try:
            dados = _get_json(url + rota, timeout)
            s["ativo"] = True
            s["modelos"] = [m.get(campo) for m in dados.get(lista, []) if conversa(m.get(campo))]
        except Exception:
            pass
        if tipo == "ollama":
            s["instalado"] = s["ativo"] or bool(ollama_exe())
            s["baixados"] = ollama_baixados() if baixados else []
        else:
            s["instalado"] = s["ativo"] or lmstudio_instalado()
            s["baixados"] = lmstudio_baixados() if baixados and s["instalado"] else []
        s["pode_ligar"] = not s["ativo"] and (bool(ollama_exe()) if tipo == "ollama" else bool(lms_cli()))
        out.append(s)
    return out


def ligar(s):
    """Liga o servidor do Ollama ou do LM Studio, sem janela."""
    flags = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW
    if s["tipo"] == "ollama":
        exe = ollama_exe()
        if not exe:
            raise RuntimeError("O Ollama não está instalado. Instale pelo passo 1 (Instalar o que falta).")
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    else:
        cli = lms_cli()
        if not cli:
            raise RuntimeError("Não achei o comando lms do LM Studio. Abra o LM Studio, vá em Developer e ligue "
                               "o servidor (Start Server), ou abra o LM Studio uma vez para ele instalar o lms.")
        subprocess.run([cli, "server", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=120, creationflags=flags)


def _esperar(tipo, espera):
    fim = time.time() + espera
    while True:
        s = next(x for x in servidores(baixados=False) if x["tipo"] == tipo)
        if s["ativo"] or time.time() > fim:
            return s
        time.sleep(1)


def carregar_lmstudio(modelo):
    cli = lms_cli()
    if cli:
        subprocess.run([cli, "load", modelo, "--yes"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=600, creationflags=0x08000000 if WIN else 0)


def preparar(config, aviso=lambda t: None, espera=60):
    """Deixa a IA local pronta para a conversa e devolve {tipo, url, modelo}.

    Se o analista escolheu um modelo, usa o servidor dele; senão ("Automático") prefere um servidor já ligado
    com modelo de ferramentas, depois um instalado com modelo baixado. Liga o servidor e, no LM Studio sem
    carregamento automático, carrega o modelo.
    """
    tipo, modelo = config.get("tipo") or "auto", (config.get("modelo") or "").strip()
    padrao = OLLAMA_URL if tipo == "ollama" else LMSTUDIO_URL
    if tipo in ("ollama", "openai") and modelo and (config.get("url") or padrao).rstrip("/") != padrao:
        return {"tipo": tipo, "url": config["url"].rstrip("/"), "modelo": modelo}  # endereço próprio do analista
    todos = servidores()
    if tipo in ("ollama", "openai") and modelo:
        alvo = next(s for s in todos if s["tipo"] == tipo)
    else:
        def ordem(s):
            ms = s["modelos"] or s["baixados"]
            return (not (s["ativo"] and s["modelos"]), not ms, nota(escolher(ms)) if ms else 99, not s["instalado"])
        alvo = sorted(todos, key=ordem)[0]
        if not alvo["instalado"]:
            raise RuntimeError("Nenhuma IA local nesta máquina. Instale o Ollama e o modelo pelo passo 1 "
                               "(Instalar o que falta) ou abra o LM Studio com um modelo baixado.")
    nome = alvo["nome"]
    if not alvo["ativo"]:
        if not alvo["instalado"]:
            raise RuntimeError("O {} não está instalado nesta máquina. Escolha Automático ou outro modelo.".format(nome))
        aviso("Ligando o servidor do {}…".format(nome))
        ligar(alvo)
        baixados = alvo["baixados"]
        alvo = _esperar(alvo["tipo"], espera)
        alvo["baixados"] = baixados
        if not alvo["ativo"]:
            raise RuntimeError("O servidor do {} não respondeu em {}. Abra o {} e tente de novo.".format(
                nome, alvo["url"], nome))
    lista = alvo["modelos"]
    if not lista and alvo["tipo"] == "openai" and alvo.get("baixados"):
        quero = modelo if modelo in alvo["baixados"] else escolher(alvo["baixados"])
        aviso("Carregando o modelo {} no LM Studio (pode levar alguns minutos)…".format(quero))
        carregar_lmstudio(quero)
        lista = next(x for x in servidores(baixados=False) if x["tipo"] == "openai")["modelos"]
    if modelo and modelo in lista:
        escolhido = modelo
    else:
        escolhido = escolher(lista)
        if not escolhido:
            raise RuntimeError("O {} está ligado mas não tem modelo. Baixe um modelo com ferramentas (por exemplo "
                               "qwen2.5 7B) no {} ou pelo passo 1.".format(nome, nome))
        if modelo:
            aviso("O modelo {} não está no {}; usando {}.".format(modelo, nome, escolhido))
        else:
            aviso("IA local escolhida: {} ({}).".format(escolhido, nome))
    if not com_ferramentas(escolhido):
        aviso("O modelo {} pode não aceitar ferramentas. Se a IA não consultar o caso, use qwen2.5, qwen3 ou "
              "llama3.1.".format(escolhido))
    return {"tipo": alvo["tipo"], "url": alvo["url"], "modelo": escolhido}
