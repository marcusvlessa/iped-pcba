"""MCP falso (STDIO, JSON-RPC por linha) para testar o assistente sem IPED. Dados fictícios."""

import json
import sys

FERRAMENTAS = [
    {"name": "get_case_summary", "description": "Resumo do caso",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search_documents", "description": "Busca",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "bookmark_search_results", "description": "Marca resultados",
     "inputSchema": {"type": "object", "properties": {}}},
]

for linha in sys.stdin:
    msg = json.loads(linha)
    if "id" not in msg:
        continue
    m = msg["method"]
    if m == "initialize":
        r = {"serverInfo": {"name": "falso"}}
    elif m == "tools/list":
        r = {"tools": FERRAMENTAS}
    elif m == "tools/call":
        p = msg["params"]
        if p["name"] == "search_documents":
            texto = "3 itens para '{}': doc_id 11 (01/02/2024), 12, 13 [FICTÍCIO]".format(p["arguments"].get("query"))
        else:
            texto = "Caso fictício: 1000 itens"
        r = {"content": [{"type": "text", "text": texto}]}
    else:
        r = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": r}) + "\n")
    sys.stdout.flush()
