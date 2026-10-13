"""Registros telemáticos no formato padronizado da PCBA e o resumo deles para o relatório.

Todo retorno de provedor (WhatsApp, Google, Apple, operadoras, Guardião) é convertido para o
mesmo formato de registro, um por linha, com as colunas de CAMPOS. Os conversores de cada
provedor (fase 3) gravam esse CSV; o resumo abaixo não depende de provedor.

Datas: data_hora em ISO 8601 com fuso (ex.: 2026-03-01T13:05:00Z ou 2026-03-01T10:05:00-03:00).
Sem fuso, a data é tratada como UTC, que é como os provedores entregam. No relatório tudo sai
no horário de Brasília (GMT-3, a Bahia não tem horário de verão).
"""

import csv
import datetime
import io
import json
from collections import Counter, OrderedDict

from .configurar import ler_texto

CAMPOS = ["provedor", "conta", "tipo", "data_hora", "interlocutor", "direcao", "ip", "porta",
          "dispositivo", "grupo", "duracao_s", "local", "fonte"]
TIPOS = OrderedDict([
    ("mensagem", ("mensagem", "mensagens")),
    ("chamada", ("chamada", "chamadas")),
    ("conexao", ("registro de conexão", "registros de conexão")),
    ("login", ("login", "logins")),
    ("localizacao", ("registro de localização", "registros de localização")),
    ("contato", ("contato de agenda", "contatos de agenda")),
    ("grupo", ("registro de grupo", "registros de grupo")),
    ("outro", ("outro registro", "outros registros")),
])
BRT = datetime.timezone(datetime.timedelta(hours=-3))


def ler_data(texto):
    t = (texto or "").strip()
    if not t:
        return None
    if t.endswith("Z") or t.endswith("z"):
        t = t[:-1] + "+00:00"
    t = t.replace(" UTC", "+00:00")
    d = datetime.datetime.fromisoformat(t)
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(BRT)


def fmt_data(d, hora=True):
    return d.strftime("%d/%m/%Y %H:%M:%S" if hora else "%d/%m/%Y")


def ler_csv(caminho):
    """Lê o CSV padronizado (separador , ou ;). Linhas sem data ou com data inválida vão para 'rejeitadas'."""
    texto = ler_texto(caminho)
    if texto.startswith("﻿"):
        texto = texto[1:]
    sep = ";" if texto.split("\n", 1)[0].count(";") > texto.split("\n", 1)[0].count(",") else ","
    registros, rejeitadas = [], []
    for n, linha in enumerate(csv.DictReader(io.StringIO(texto), delimiter=sep), start=2):
        r = {c: (linha.get(c) or "").strip() for c in CAMPOS}
        try:
            r["_data"] = ler_data(r["data_hora"])
        except ValueError:
            r["_data"] = None
        if r["_data"] is None or not r["provedor"] or not r["conta"]:
            rejeitadas.append(n)
            continue
        r["tipo"] = r["tipo"].lower() if r["tipo"].lower() in TIPOS else "outro"
        registros.append(r)
    return registros, rejeitadas


def _plural(n, tipo):
    s, p = TIPOS[tipo]
    return "{} {}".format(n, s if n == 1 else p)


def _lista(itens):
    itens = list(itens)
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def resumir(registros, top=10):
    """Um resumo por (provedor, conta), ordenado por provedor e volume."""
    grupos = OrderedDict()
    for r in sorted(registros, key=lambda x: x["_data"]):
        grupos.setdefault((r["provedor"].upper(), r["conta"]), []).append(r)
    resumos = []
    for (prov, conta), regs in grupos.items():
        tipos = Counter(r["tipo"] for r in regs)
        inter = OrderedDict()
        for r in regs:
            if r["interlocutor"] and r["tipo"] in ("mensagem", "chamada"):
                i = inter.setdefault(r["interlocutor"], {"total": 0, "primeiro": r["_data"],
                                                         "ultimo": r["_data"], "chamadas": 0})
                i["total"] += 1
                i["ultimo"] = r["_data"]
                if r["tipo"] == "chamada":
                    i["chamadas"] += 1
        ips = OrderedDict()
        for r in regs:
            if r["ip"]:
                i = ips.setdefault(r["ip"], {"total": 0, "primeiro": r["_data"], "ultimo": r["_data"],
                                             "portas": set()})
                i["total"] += 1
                i["ultimo"] = r["_data"]
                if r["porta"]:
                    i["portas"].add(r["porta"])
        horas = Counter(r["_data"].hour for r in regs)
        resumos.append({
            "provedor": prov, "conta": conta, "total": len(regs),
            "inicio": regs[0]["_data"], "fim": regs[-1]["_data"],
            "tipos": OrderedDict((t, tipos[t]) for t in TIPOS if tipos[t]),
            "interlocutores": sorted(inter.items(), key=lambda x: -x[1]["total"])[:top],
            "n_interlocutores": len(inter),
            "ips": sorted(ips.items(), key=lambda x: -x[1]["total"]),
            "dispositivos": sorted({r["dispositivo"] for r in regs if r["dispositivo"]}),
            "grupos": sorted({r["grupo"] for r in regs if r["grupo"]}),
            "faixa_horaria": _faixa(horas),
            "fontes": sorted({r["fonte"] for r in regs if r["fonte"]}),
        })
    resumos.sort(key=lambda s: (s["provedor"], -s["total"]))
    return resumos


def _faixa(horas):
    """Janela de 4 horas com mais eventos (hora local)."""
    if not horas:
        return None
    melhor = max(range(24), key=lambda h: sum(horas[(h + k) % 24] for k in range(4)))
    total = sum(horas.values())
    n = sum(horas[(melhor + k) % 24] for k in range(4))
    return {"inicio": melhor, "fim": (melhor + 4) % 24, "eventos": n, "percentual": round(100.0 * n / total)}


def texto_analise(s):
    """Rascunho em prosa corrida (sem tópicos), para o analista revisar."""
    partes = []
    tipos = _lista(_plural(n, t) for t, n in s["tipos"].items())
    partes.append(
        "No período de {} a {} (horário de Brasília), a conta {} junto ao provedor {} registrou {} "
        "eventos nos dados recebidos, sendo {}.".format(
            fmt_data(s["inicio"]), fmt_data(s["fim"]), s["conta"], s["provedor"], s["total"], tipos))
    if s["interlocutores"]:
        top = s["interlocutores"][:3]
        frase = ("Foram identificados {} interlocutores distintos em mensagens e chamadas, sendo os mais "
                 "frequentes {}".format(s["n_interlocutores"],
                                        _lista("{} ({} interações)".format(k, v["total"]) for k, v in top)))
        soma = sum(i["total"] for _, i in s["interlocutores"])
        if soma and s["n_interlocutores"] > 3:
            frase += ", que juntos concentram {}% das interações".format(
                round(100.0 * sum(v["total"] for _, v in top) / soma))
        partes.append(frase + " (ver quadro de interlocutores).")
    if s["ips"]:
        ip, v = s["ips"][0]
        partes.append(
            "Os registros apontam {} endereço(s) IP distinto(s). O mais recorrente foi {}, com {} "
            "ocorrência(s) entre {} e {}{}.".format(
                len(s["ips"]), ip, v["total"], fmt_data(v["primeiro"]), fmt_data(v["ultimo"]),
                ", porta(s) lógica(s) " + _lista(sorted(v["portas"])) if v["portas"] else ""))
    if s["dispositivos"]:
        partes.append("Dispositivo(s) informado(s) pelo provedor: {}.".format(_lista(s["dispositivos"])))
    if s["grupos"]:
        partes.append("A conta aparece em {} grupo(s): {}.".format(len(s["grupos"]), _lista(s["grupos"][:10])))
    f = s["faixa_horaria"]
    if f and s["total"] >= 10:
        partes.append("A maior concentração de atividade ocorreu entre {:02d}h e {:02d}h, com {}% dos "
                      "eventos.".format(f["inicio"], f["fim"], f["percentual"]))
    return " ".join(partes)


def quadros(s):
    """Quadros de apoio (interlocutores e IPs) no formato do relatório."""
    q = []
    if s["interlocutores"]:
        q.append({"titulo": "Quadro – principais interlocutores – {} {}".format(s["provedor"], s["conta"]),
                  "colunas": ["INTERLOCUTOR", "INTERAÇÕES", "CHAMADAS", "PRIMEIRA", "ÚLTIMA"],
                  "linhas": [[k, str(v["total"]), str(v["chamadas"]), fmt_data(v["primeiro"]),
                              fmt_data(v["ultimo"])] for k, v in s["interlocutores"]]})
    if s["ips"]:
        q.append({"titulo": "Quadro – endereços IP – {} {}".format(s["provedor"], s["conta"]),
                  "colunas": ["IP", "OCORRÊNCIAS", "PORTAS", "PRIMEIRA", "ÚLTIMA"],
                  "linhas": [[k, str(v["total"]), ", ".join(sorted(v["portas"])) or "-",
                              fmt_data(v["primeiro"]), fmt_data(v["ultimo"])] for k, v in s["ips"][:30]]})
    return q


def analises_para_rt(resumos, investigados=None):
    """Converte os resumos em entradas 'analises' do RT, uma por provedor.

    investigados: {conta: nome}. A conclusão fica sempre como lacuna: quem conclui é o analista.
    """
    investigados = investigados or {}
    por_prov = OrderedDict()
    for s in resumos:
        por_prov.setdefault(s["provedor"], []).append(s)
    saida = []
    for prov, lista in por_prov.items():
        saida.append({
            "provedor": prov,
            "titulo": "DA ANÁLISE DOS DADOS TELEMÁTICOS – " + prov,
            "tabela": [{"investigado": investigados.get(s["conta"]) or "[INVESTIGADO]",
                        "conta": s["conta"],
                        "periodo": "Dados: {} a {}".format(fmt_data(s["inicio"], False),
                                                           fmt_data(s["fim"], False))} for s in lista],
            "texto": "\n".join(texto_analise(s) for s in lista),
            "quadros": [q for s in lista for q in quadros(s)],
            "conclusao": "[CONCLUSÃO DO ANALISTA SOBRE {}]".format(prov),
            "gerado_automaticamente": True,
        })
    return saida


def resumo_json(resumos):
    """Versão serializável (para a IA via MCP e para o painel)."""
    def conv(v):
        if isinstance(v, datetime.datetime):
            return v.isoformat()
        if isinstance(v, set):
            return sorted(v)
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        return v
    return json.loads(json.dumps(conv(resumos), ensure_ascii=False))
