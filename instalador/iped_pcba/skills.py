"""Skills de análise (pasta skills/ na raiz do pacote): cada uma é um SKILL.md no formato aberto Agent Skills.

O painel usa as skills de três jeitos:
  - IA local (Ollama, LM Studio): cada skill vira um agente do Assistente, sem instalar nada;
  - Claude Code e Hermes Agent: copia as pastas para ~/.claude/skills e ~/.hermes/skills/iped-pcba;
  - Claude Desktop e claude.ai: gera um .zip por skill, que o analista envia em Configurações > Capacidades.
Antes de trocar uma skill já instalada e diferente, guarda a anterior em ~/.iped-pcba/backup-skills/.
Só a biblioteca padrão.
"""

import filecmp
import os
import shutil
import time
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PASTA = os.path.join(REPO, "skills")
ZIPS = os.path.join(REPO, "skills-zip")


def _frontmatter(texto):
    """Lê o cabeçalho YAML simples do SKILL.md (chave: valor e um nível de aninhamento)."""
    if not texto.startswith("---"):
        return {}, texto
    fim = texto.find("\n---", 3)
    cab, corpo = texto[3:fim], texto[fim + 4:].lstrip("\n")
    d, pai = {}, None
    for linha in cab.splitlines():
        if not linha.strip():
            continue
        chave, _, valor = linha.strip().partition(":")
        valor = valor.strip().strip('"')
        if linha.startswith((" ", "\t")) and pai is not None:
            d[pai][chave] = valor
        elif valor:
            d[chave], pai = valor, None
        else:
            d[chave], pai = {}, chave
    return d, corpo


def listar(pasta=PASTA):
    out = []
    if not os.path.isdir(pasta):
        return out
    for nome in sorted(os.listdir(pasta)):
        arq = os.path.join(pasta, nome, "SKILL.md")
        if not os.path.isfile(arq):
            continue
        with open(arq, encoding="utf-8") as f:
            cab, corpo = _frontmatter(f.read())
        fer = (cab.get("metadata") or {}).get("ferramentas", "")
        out.append({"id": cab.get("name") or nome, "pasta": os.path.join(pasta, nome), "descricao": cab.get("description", ""),
                    "corpo": corpo, "ferramentas": "todas" if fer.strip() == "todas" else
                    [x.strip() for x in fer.split(",") if x.strip()]})
    # a análise completa, que usa as outras, fica por último
    return sorted(out, key=lambda s: s["id"] == "analise-forense-completa")


TITULOS = {
    "analise-financeira": ("Análise financeira", "PDFs, extratos, PIX, SIMBA, RIF e cripto: transações, contrapartes e sinais de lavagem."),
    "analise-imagens": ("Análise de imagens", "Fotos, prints, documentos, OCR, QR codes, imagens e rostos semelhantes."),
    "analise-audio": ("Análise de áudios", "Transcrições de áudios: quem fala, quando e sobre o quê."),
    "analise-geolocalizacao": ("Geolocalização", "Coordenadas de fotos, histórico de localização e apps de mobilidade."),
    "analise-midias-x-logs": ("Mídias x logs do aparelho", "Confere nos logs do aparelho quando e como cada mídia foi gerada."),
    "analise-forense-completa": ("Análise completa", "Orquestra todas as skills e monta a análise do caso por tópico."),
}


def _titulo(s):
    return TITULOS.get(s["id"], (s["id"].replace("-", " ").capitalize(), s["descricao"]))


def como_agente(s):
    """A skill como agente do Assistente (IA local)."""
    titulo, resumo = _titulo(s)
    return {"id": "skill:" + s["id"], "nome": titulo, "skill": True, "descricao": resumo,
            "papel": "Siga a skill {} abaixo.\n\n{}".format(s["id"], s["corpo"]),
            "ferramentas": s["ferramentas"], "escrita": s["id"] == "analise-forense-completa",
            "passos": 40 if s["id"] == "analise-forense-completa" else 20,
            "prompts": [{"titulo": "Rodar a análise no caso",
                         "texto": "Faça a {} do caso em análise seguindo a skill.".format(titulo.lower())},
                        {"titulo": "Focar em [ALVO]",
                         "texto": "Faça a {} com foco em [ALVO] (nome, telefone, conta ou período).".format(titulo.lower())}]}


def destinos(home=None):
    """Onde dá para instalar nesta máquina. 'detectado' diz se o programa parece estar instalado."""
    home = home or os.path.expanduser("~")
    return [
        {"id": "claude-code", "nome": "Claude Code", "pasta": os.path.join(home, ".claude", "skills"),
         "detectado": os.path.isdir(os.path.join(home, ".claude")) or bool(shutil.which("claude"))},
        {"id": "hermes", "nome": "Hermes Agent", "pasta": os.path.join(home, ".hermes", "skills", "iped-pcba"),
         "detectado": os.path.isdir(os.path.join(home, ".hermes"))},
        {"id": "zip", "nome": "Claude Desktop e claude.ai (enviar o .zip)", "pasta": ZIPS, "detectado": True},
    ]


def _igual(a, b):
    if not os.path.isdir(b):
        return False
    c = filecmp.dircmp(a, b)
    return not (c.left_only or c.right_only or filecmp.cmpfiles(a, b, c.common_files, shallow=False)[1:] != ([], []))


def _zip_de(s):
    return os.path.join(ZIPS, s["id"] + ".zip")


def situacao(home=None, pasta=PASTA):
    sk = listar(pasta)
    out = []
    for d in destinos(home):
        itens = []
        for s in sk:
            if d["id"] == "zip":
                z = os.path.join(d["pasta"], s["id"] + ".zip")
                est = "gerado" if os.path.isfile(z) and os.path.getmtime(z) >= os.path.getmtime(
                    os.path.join(s["pasta"], "SKILL.md")) else "falta"
            else:
                alvo = os.path.join(d["pasta"], s["id"])
                est = "instalada" if _igual(s["pasta"], alvo) else ("desatualizada" if os.path.isdir(alvo) else "falta")
            itens.append({"skill": s["id"], "estado": est})
        out.append(dict(d, itens=itens))
    return {"skills": [{"id": s["id"], "nome": _titulo(s)[0], "descricao": _titulo(s)[1]} for s in sk],
            "destinos": out}


def instalar(ids=None, home=None, pasta=PASTA):
    """Instala as skills nos destinos pedidos (todos os detectados se ids=None). Devolve o que fez."""
    home = home or os.path.expanduser("~")
    sk, feito = listar(pasta), []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for d in destinos(home):
        if (ids is None and not d["detectado"]) or (ids is not None and d["id"] not in ids):
            continue
        os.makedirs(d["pasta"], exist_ok=True)
        for s in sk:
            if d["id"] == "zip":
                with zipfile.ZipFile(os.path.join(d["pasta"], s["id"] + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
                    for raiz, _, arqs in os.walk(s["pasta"]):
                        for a in arqs:
                            c = os.path.join(raiz, a)
                            z.write(c, os.path.join(s["id"], os.path.relpath(c, s["pasta"])))
                feito.append({"destino": d["id"], "skill": s["id"], "acao": "zip"})
                continue
            alvo = os.path.join(d["pasta"], s["id"])
            if _igual(s["pasta"], alvo):
                feito.append({"destino": d["id"], "skill": s["id"], "acao": "já estava"})
                continue
            acao = "instalada"
            if os.path.isdir(alvo):
                bk = os.path.join(home, ".iped-pcba", "backup-skills", stamp, d["id"])
                os.makedirs(bk, exist_ok=True)
                shutil.move(alvo, os.path.join(bk, s["id"]))
                acao = "atualizada (anterior em {})".format(bk)
            shutil.copytree(s["pasta"], alvo)
            feito.append({"destino": d["id"], "skill": s["id"], "acao": acao})
    return feito
