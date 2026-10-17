"""Encontra instalações do IPED na máquina, sem depender de caminho fixo.

Ordem de busca:
1. variável de ambiente IPED_ROOT;
2. ~/.iped/ipedRoot.txt, que o próprio IPED grava ao abrir;
3. pastas comuns (raiz dos discos, Tools, Program Files, Área de Trabalho,
   Downloads, Documentos, /opt, /srv, /usr/local) até três níveis.

Só conta como instalação a pasta que tem IPEDConfig.txt E iped.jar.
"""

import glob
import io
import os
import re
import string

PROFUNDIDADE = 3


def eh_instalacao(pasta):
    return (os.path.isfile(os.path.join(pasta, "IPEDConfig.txt"))
            and os.path.isfile(os.path.join(pasta, "iped.jar")))


def versao_de(pasta):
    for jar in glob.glob(os.path.join(pasta, "lib", "iped-engine-*.jar")):
        m = re.search(r"iped-engine-([\d.]+)", os.path.basename(jar))
        if m:
            return m.group(1).rstrip(".")
    m = re.search(r"iped-([\d.]+)", os.path.basename(os.path.normpath(pasta)))
    return m.group(1).rstrip(".") if m else ""


def _chave_versao(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def _bases():
    casa = os.path.expanduser("~")
    bases = [casa]
    for sub in ("Desktop", "Área de Trabalho", "Downloads", "Documents", "Documentos"):
        bases.append(os.path.join(casa, sub))
    if os.name == "nt":
        for letra in string.ascii_uppercase:
            raiz = letra + ":\\"
            if os.path.isdir(raiz):
                bases += [raiz, os.path.join(raiz, "Tools"), os.path.join(raiz, "Program Files"),
                          os.path.join(raiz, "Program Files (x86)")]
    else:
        bases += ["/opt", "/srv", "/usr/local", "/data"]
    return [b for b in bases if os.path.isdir(b)]


def _varrer(base, profundidade):
    achados = []
    for nivel in range(profundidade + 1):
        padrao = os.path.join(base, *(["*"] * nivel + ["iped.jar"]))
        for jar in glob.glob(padrao):
            pasta = os.path.dirname(jar)
            if eh_instalacao(pasta):
                achados.append(pasta)
    return achados


def candidatos_declarados():
    out = []
    if os.environ.get("IPED_ROOT"):
        out.append(os.environ["IPED_ROOT"])
    arq = os.path.join(os.path.expanduser("~"), ".iped", "ipedRoot.txt")
    if os.path.isfile(arq):
        try:
            with io.open(arq, encoding="utf-8", errors="ignore") as f:
                linha = f.read().strip().lstrip(u"﻿")
            if linha:
                out.append(linha)
        except OSError:
            pass
    return out


def localizar_iped(bases=None, profundidade=PROFUNDIDADE):
    """Lista de instalações encontradas, a de versão mais nova primeiro. Entre versões iguais,
    vem primeiro a que o IPED registrou como em uso (ipedRoot.txt ou IPED_ROOT)."""
    vistos = {}
    declarados = set()
    # com bases informadas, a instalação registrada só conta se estiver dentro delas
    dentro = [os.path.normcase(os.path.abspath(b)).rstrip("\\/") + os.sep for b in bases or []]
    for c in candidatos_declarados():
        if eh_instalacao(c):
            chave = os.path.normcase(os.path.abspath(c))
            declarados.add(chave)
            if bases is None or any((chave + os.sep).startswith(d) for d in dentro):
                vistos[chave] = os.path.abspath(c)
    for base in (bases if bases is not None else _bases()):
        for p in _varrer(base, profundidade):
            vistos.setdefault(os.path.normcase(os.path.abspath(p)), os.path.abspath(p))
    lista = [{"raiz": p, "versao": versao_de(p), "em_uso": k in declarados}
             for k, p in vistos.items()]
    return sorted(lista, key=lambda x: (_chave_versao(x["versao"]), x["em_uso"], x["raiz"]),
                  reverse=True)
