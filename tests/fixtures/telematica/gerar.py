"""Gera registros_ficticios.csv: dados INVENTADOS para teste (nenhum dado real).

Números 5500..., e-mails example.com e IPs das faixas de documentação (RFC 5737 e RFC 3849).
"""
import csv
import datetime
import os
import random

random.seed(7)
WA, GO = "+5500900000001", "fulano.ficticio@example.com"
INTER = ["+5500900000002", "+5500900000003", "+5500900000004", "+5500900000005", "+5500900000006",
         "+5500900000007"]
IPS = ["203.0.113.10", "203.0.113.45", "198.51.100.7", "2001:db8::1a"]
CAMPOS = ["provedor", "conta", "tipo", "data_hora", "interlocutor", "direcao", "ip", "porta",
          "dispositivo", "grupo", "duracao_s", "local", "fonte"]
base = datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.timezone.utc)
linhas = []
for i in range(120):
    d = base + datetime.timedelta(hours=random.randint(0, 24 * 20), minutes=random.randint(0, 59))
    t = random.choices(["mensagem", "chamada", "conexao"], [6, 2, 3])[0]
    c = t == "conexao"
    linhas.append({
        "provedor": "WhatsApp", "conta": WA, "tipo": t, "data_hora": d.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interlocutor": "" if c else random.choices(INTER, [8, 5, 3, 2, 1, 1])[0],
        "direcao": "" if c else random.choice(["enviada", "recebida"]),
        "ip": random.choices(IPS, [6, 2, 1, 1])[0] if c else "",
        "porta": str(random.choice([40112, 51200, 33017])) if c else "",
        "dispositivo": "Android (fictício)", "grupo": "Grupo Fictício A" if i % 15 == 0 else "",
        "duracao_s": str(random.randint(5, 600)) if t == "chamada" else "", "local": "",
        "fonte": "retorno-whatsapp-ficticio.zip"})
for i in range(30):
    d = base + datetime.timedelta(hours=random.randint(0, 24 * 20))
    linhas.append({"provedor": "Google", "conta": GO, "tipo": "login",
                   "data_hora": d.strftime("%Y-%m-%dT%H:%M:%SZ"), "ip": random.choice(IPS[:2]),
                   "fonte": "google-lers-ficticio.zip"})
linhas.append({"provedor": "Google", "conta": GO, "tipo": "login", "data_hora": "data-ruim"})
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "registros_ficticios.csv"), "w",
          newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, CAMPOS, delimiter=";")
    w.writeheader()
    for l in linhas:
        w.writerow({k: l.get(k, "") for k in CAMPOS})
