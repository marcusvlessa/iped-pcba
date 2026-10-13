"""Gera visao_ficticia.json: a saída do MCP (--exportar-visao) para um caso inventado.

Todos os nomes, números e telefones são fictícios (faixa +55 00 9...). Usado nos testes e nas
capturas de tela do painel.
"""
import json
import os
import random

random.seed(7)
meses = []
for a in (2025, 2026):
    for m in range(1, 13):
        if (a, m) < (2025, 3) or (a, m) > (2026, 9):
            continue
        t = random.randint(400, 900)
        if (a, m) == (2026, 5):
            t = 6400  # pico
        meses.append({"mes": "%d-%02d" % (a, m), "total": t, "comunicacao": int(t * random.uniform(.25, .45))})
nomes = ["FULANO (FICTÍCIO)", "BELTRANO (FICTÍCIO)", "CICRANO (FICTÍCIO)", "GRUPO FAMÍLIA (FICTÍCIO)",
         "DELTA (FICTÍCIO)", "ECO (FICTÍCIO)", "FOXTROT (FICTÍCIO)", "GOLF (FICTÍCIO)", "HOTEL (FICTÍCIO)",
         "ÍNDIA (FICTÍCIO)", "JULIETA (FICTÍCIO)", "KILO (FICTÍCIO)"]
contatos = []
for i, n in enumerate(nomes):
    msg = int(900 / (i + 1)) + random.randint(0, 30)
    cal = int(msg * random.uniform(.05, .3))
    contatos.append({"rank": i + 1, "identifier": "+55009000000%02d" % (i + 1), "name": n,
                     "total_interactions": msg + cal, "messages_count": msg, "calls_count": cal,
                     "channels": ["WhatsApp"] + (["Chamadas"] if cal else []),
                     **({"is_group": True} if "GRUPO" in n else {})})
dono = {"id": "TITULAR_(FICTÍCIO)", "label": "TITULAR (FICTÍCIO)", "total_interactions": 0}
nodes, edges = [dono], []
for c in contatos:
    nodes.append({"id": c["identifier"], "label": c["name"], "total_interactions": c["total_interactions"],
                  **({"is_group": True} if c.get("is_group") else {})})
    edges.append({"source": dono["id"], "target": c["identifier"], "weight": c["total_interactions"],
                  "channels": c["channels"], "messages_count": c["messages_count"], "calls_count": c["calls_count"]})
    dono["total_interactions"] += c["total_interactions"]
for a, b, w in ((1, 2, 40), (1, 3, 25), (2, 5, 12), (4, 6, 9), (3, 7, 6)):
    nodes[a]["total_interactions"] += w
    nodes[b]["total_interactions"] += w
    edges.append({"source": nodes[a]["id"], "target": nodes[b]["id"], "weight": w, "channels": ["WhatsApp"],
                  "messages_count": w, "calls_count": 0})
visao = {
    "gerado_em": "2026-10-13T21:30:00", "caso": "/casos/caso-exemplo",
    "geral": {"total_itens": 184322, "fontes": [{"id": "caso-exemplo", "name": "celular-ficticio.ufdr"}]},
    "categorias": [{"nome": n, "total": t} for n, t in (
        ("Imagens", 61230), ("Chats do WhatsApp", 22410), ("Mensagens do WhatsApp", 21877), ("Áudios", 4310),
        ("Vídeos", 2210), ("Contatos", 1830), ("Chamadas", 1622), ("Documentos PDF", 911),
        ("Histórico de Navegação", 870), ("Localizações", 512), ("Arquivos Criptografados", 14), ("E-mails", 9))],
    "marcadores": [],
    "linha_do_tempo": {"meses": meses, "categorias_comunicacao": ["Chats do WhatsApp", "Chamadas", "E-mails"]},
    "contatos": contatos,
    "rede": {"total_nodes": len(nodes), "total_edges": len(edges), "nodes": nodes, "edges": edges},
    "dispositivos": [{"name": "celular-ficticio.ufdr", "type": "Android", "likely_owners": ["TITULAR (FICTÍCIO)"],
                      "owner_phone_numbers": ["+5500900000000"], "owner_emails": ["titular@example.com"]}],
    "ia_filtros": [{"id": "weapons", "nome": "Armas de Fogo e Munições", "total": 7},
                   {"id": "drugs", "nome": "Drogas", "total": 0},
                   {"id": "nudity", "nome": "Nudez e Conteúdo Adulto", "total": 31},
                   {"id": "faces", "nome": "Faces", "total": 0},
                   {"id": "audio_transcripts", "nome": "Transcrições de áudio", "total": 0},
                   {"id": "csam", "nome": "CSAM", "total": 0},
                   {"id": "ocr", "nome": "OCR", "total": 1290}],
    "especiais": {"apagados": 3412, "recuperados_carving": 880, "alerta_hash": 0},
    "erros": {},
}
with open(os.path.join(os.path.dirname(__file__), "visao_ficticia.json"), "w", encoding="utf-8") as f:
    json.dump(visao, f, ensure_ascii=False, indent=1)
