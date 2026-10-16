"""Vários casos juntos: grupos de casos, abertura conjunta no IPED (-multicases) e análise cruzada.

A análise cruzada usa o visao.json que o MCP exporta para cada caso (rede de comunicações inteira e
dispositivos com titulares). Procura telefones, contas e e-mails que aparecem em mais de um caso,
titulares de um caso que aparecem como contato em outro, e monta uma rede única com todos os casos.
Só a biblioteca padrão.
"""

import datetime
import json
import os
import re
import subprocess

from .configurar import gravar_texto, ler_texto
from .processar import PASTA as PASTA_PCBA, WIN, eh_caso
from . import visao

ARQ_GRUPOS = os.path.join(PASTA_PCBA, "multicasos.json")
PASTA_SAIDA = os.path.join(PASTA_PCBA, "multicasos")


# ------------------------------------------------------------------ grupos de casos

def grupos():
    try:
        return json.loads(ler_texto(ARQ_GRUPOS))
    except Exception:
        return []


def salvar_grupo(nome, casos):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Dê um nome ao grupo de casos.")
    if len(casos) < 2:
        raise ValueError("Escolha pelo menos dois casos.")
    lista = [g for g in grupos() if g["nome"] != nome]
    lista.insert(0, {"nome": nome, "casos": [os.path.abspath(c) for c in casos],
                     "salvo": datetime.datetime.now().isoformat(timespec="seconds")})
    os.makedirs(PASTA_PCBA, exist_ok=True)
    gravar_texto(ARQ_GRUPOS, json.dumps(lista[:50], indent=2, ensure_ascii=False))
    return lista


def remover_grupo(nome):
    lista = [g for g in grupos() if g["nome"] != nome]
    gravar_texto(ARQ_GRUPOS, json.dumps(lista, indent=2, ensure_ascii=False))
    return lista


def abrir_no_iped(casos):
    """Abre os casos juntos na interface do IPED (opção -multicases, um caso por linha)."""
    casos = [os.path.abspath(c) for c in casos]
    if len(casos) < 2:
        raise ValueError("Escolha pelo menos dois casos.")
    fora = [c for c in casos if not eh_caso(c)]
    if fora:
        raise ValueError("Não são casos do IPED: " + "; ".join(fora))
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    lista = os.path.join(PASTA_SAIDA, "casos-{}.txt".format(datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    with open(lista, "w", encoding="utf-8") as f:
        f.write("\n".join(casos) + "\n")
    base = casos[0]
    jar = os.path.join(base, "iped", "lib", "iped-search-app.jar")
    java = os.path.join(base, "iped", "jre", "bin", "java.exe" if WIN else "java")
    if not os.path.isfile(java):
        java = "java"
    if not os.path.isfile(jar):
        raise ValueError("Não achei a interface do IPED em " + base)
    flags = 0x00000008 if WIN else 0
    subprocess.Popen([java, "-jar", jar, "-multicases", lista], cwd=base, creationflags=flags,
                     start_new_session=not WIN)
    return {"lista": lista, "casos": casos}


# ------------------------------------------------------------------ análise cruzada

def chave(ident):
    """Chave para comparar identificadores entre casos: telefone, e-mail, conta ou nome.

    Telefones viram DDD + 8 últimos dígitos (tira o 55, o 0 de operadora e o nono dígito), para
    +55 71 9xxxx-xxxx, 71 9xxxx-xxxx e 5571xxxxxxxx@s.whatsapp.net baterem. Devolve (tipo, chave)."""
    s = str(ident or "").strip()
    if not s:
        return None, None
    low = s.lower()
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", low)
    if m and "whatsapp" not in low and "s.us" not in low and not low.startswith(("+", "55")):
        return "email", m.group(0)
    dig = re.sub(r"\D", "", low.split("@")[0])
    if 8 <= len(dig) <= 15:
        if dig.startswith("55") and len(dig) >= 12:
            dig = dig[2:]
        dig = dig.lstrip("0")
        if len(dig) >= 10:
            ddd, num = dig[:2], dig[2:]
            return "telefone", ddd + num[-8:]
        return "telefone", dig[-8:]
    nome = re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", low)).strip()
    return ("nome", nome) if len(nome) >= 3 else (None, None)


def _nome_caso(pasta):
    return os.path.basename(os.path.abspath(pasta).rstrip("\\/"))


def cruzar(casos, ler=None):
    """Cruza os casos. ler(caso) devolve o visao.json do caso (padrão: o arquivo exportado pelo MCP)."""
    ler = ler or (lambda c: visao._ler_json(os.path.join(visao.pasta(c), visao.ARQ_VISAO)))
    if len(casos) < 2:
        raise ValueError("Escolha pelo menos dois casos.")
    info, idx = [], {}           # idx[(tipo, chave)] = {caso: {...}}
    nos_rede, arestas = {}, {}

    def ver(ci, ident, rotulo, papel, inter=0):
        tipo, k = chave(ident)
        if not k:
            k2 = chave(rotulo)
            tipo, k = k2
        if not k:
            return None
        e = idx.setdefault((tipo, k), {})
        x = e.setdefault(ci, {"rotulos": set(), "papel": set(), "interacoes": 0})
        x["rotulos"].add(str(rotulo or ident))
        x["papel"].add(papel)
        x["interacoes"] += inter
        return tipo + ":" + k

    for ci, c in enumerate(casos):
        nome = _nome_caso(c)
        v = ler(c)
        if not v:
            info.append({"pasta": c, "nome": nome, "ok": False,
                         "erro": "sem os números do caso: abra a Visão do caso e clique em Atualizar"})
            continue
        rede = v.get("rede") or {}
        rot = {n.get("id"): n.get("label") or n.get("id") for n in rede.get("nodes") or []}
        tot = {}
        for e in rede.get("edges") or []:
            w = e.get("weight") or 0
            tot[e.get("source")] = tot.get(e.get("source"), 0) + w
            tot[e.get("target")] = tot.get(e.get("target"), 0) + w
        mapa = {}
        for nid, w in tot.items():
            mapa[nid] = ver(ci, nid, rot.get(nid, nid), "contato", w)
        titulares = []
        for d in v.get("dispositivos") or []:
            dono = []
            for tel in d.get("owner_phone_numbers") or []:
                dono.append(ver(ci, tel, (d.get("likely_owners") or [tel])[0], "titular"))
                titulares.append(tel)
            for em in d.get("owner_emails") or []:
                dono.append(ver(ci, em, em, "titular"))
            for nm in d.get("likely_owners") or []:
                k = ver(ci, nm, nm, "titular")
                # na rede o titular aparece pelo nome: no grafo único ele vira o telefone (ou e-mail) dele
                if nm in mapa:
                    mapa[nm] = next((x for x in dono if x), k)
        for e in rede.get("edges") or []:
            a, b = mapa.get(e.get("source")), mapa.get(e.get("target"))
            if not a or not b or a == b:
                continue
            par = tuple(sorted((a, b)))
            t = arestas.setdefault(par, {"source": par[0], "target": par[1], "weight": 0, "messages_count": 0,
                                         "calls_count": 0, "channels": [], "casos": []})
            t["weight"] += e.get("weight") or 0
            t["messages_count"] += e.get("messages_count") or 0
            t["calls_count"] += e.get("calls_count") or 0
            t["channels"] = sorted(set(t["channels"]) | set(e.get("channels") or []))
            if nome not in t["casos"]:
                t["casos"].append(nome)
        info.append({"pasta": c, "nome": nome, "ok": True, "gerado_em": v.get("gerado_em"),
                     "contatos": len(tot), "ligacoes": len(rede.get("edges") or []),
                     "edges_before_limit": rede.get("edges_before_limit"), "titulares": titulares})

    nomes = [i["nome"] for i in info]
    comuns = []
    for (tipo, k), por in idx.items():
        # rótulo do nó: o nome de titular, se for titular em algum caso; senão o nome mais informativo
        rots = [r for x in por.values() if "titular" in x["papel"] for r in x["rotulos"]] or \
            [r for x in por.values() for r in x["rotulos"]]
        rots.sort(key=lambda r: (not re.search(r"[A-Za-zÀ-ú]", r), -len(r)))
        nos_rede[tipo + ":" + k] = {"id": tipo + ":" + k, "label": rots[0], "tipo": tipo,
                                    "casos": [nomes[ci] for ci in sorted(por)]}
        if len(por) < 2:
            continue
        titular_em = [nomes[ci] for ci, x in por.items() if "titular" in x["papel"]]
        comuns.append({"chave": k, "tipo": tipo, "casos": [nomes[ci] for ci in sorted(por)],
                       "rotulos": {nomes[ci]: sorted(x["rotulos"]) for ci, x in por.items()},
                       "interacoes": {nomes[ci]: x["interacoes"] for ci, x in por.items()},
                       "titular_em": titular_em,
                       "forca": "forte" if tipo in ("telefone", "email") else "fraca (só o nome)"})
    comuns.sort(key=lambda x: (x["tipo"] == "nome", -len(x["titular_em"]), -len(x["casos"]),
                               -sum(x["interacoes"].values())))
    usados = {e["source"] for e in arestas.values()} | {e["target"] for e in arestas.values()}
    rede = {"multicaso": True, "casos": nomes, "nodes": [n for k, n in nos_rede.items() if k in usados],
            "edges": sorted(arestas.values(), key=lambda e: -e["weight"])}
    rede["edges_before_limit"] = len(rede["edges"])
    return {"casos": info, "comuns": comuns, "rede": rede,
            "resumo": {"casos": len(info), "com_dados": sum(1 for i in info if i["ok"]),
                       "comuns_fortes": sum(1 for x in comuns if x["tipo"] != "nome"),
                       "comuns_nome": sum(1 for x in comuns if x["tipo"] == "nome"),
                       "titulares_cruzados": sum(1 for x in comuns if x["titular_em"])}}


def relatorio_md(r):
    """Texto da análise cruzada para salvar ou levar à IA."""
    L = ["# Análise cruzada de casos", "",
         "Gerada em {} pelo painel IPED-PCBA. Identificadores iguais indicam possível vínculo; confira cada um "
         "no IPED antes de concluir. Coincidência só de nome é indício fraco.".format(
             datetime.datetime.now().strftime("%d/%m/%Y %H:%M")), "", "## Casos", ""]
    for c in r["casos"]:
        L.append("- {}: {}".format(c["nome"], "{} contatos, {} ligações".format(c["contatos"], c["ligacoes"])
                                   if c["ok"] else c["erro"]))
    L += ["", "## Identificadores em mais de um caso", ""]
    if not r["comuns"]:
        L.append("Nenhum telefone, e-mail, conta ou nome em comum.")
    else:
        L.append("| Identificador | Tipo | Casos | Como aparece | Interações por caso | Titular em |")
        L.append("|---|---|---|---|---|---|")
        for x in r["comuns"]:
            L.append("| {} | {} | {} | {} | {} | {} |".format(
                x["chave"], x["tipo"] + ("" if x["tipo"] != "nome" else " (fraco)"), ", ".join(x["casos"]),
                "; ".join("{}: {}".format(c, ", ".join(v)) for c, v in x["rotulos"].items()).replace("|", "/"),
                ", ".join("{}: {}".format(c, n) for c, n in x["interacoes"].items()),
                ", ".join(x["titular_em"]) or "-"))
    return "\n".join(L) + "\n"


def salvar_relatorio(r):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    arq = os.path.join(PASTA_SAIDA, "analise-cruzada-{}.md".format(datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    with open(arq, "w", encoding="utf-8") as f:
        f.write(relatorio_md(r))
    return arq
