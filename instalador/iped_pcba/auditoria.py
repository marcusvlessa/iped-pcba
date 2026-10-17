"""Verifica o log de auditoria do MCP da PCBA (mcp-auditoria.jsonl).

Cada linha termina com ,"hash":"<64 hex>"}. O corpo é a linha sem esse trecho, fechada com }.
Regras: o campo "anterior" do corpo é o hash da linha anterior (64 zeros na primeira),
hash = sha256(anterior + corpo) e "seq" cresce de 1 em 1.

Uso: python -m iped_pcba.auditoria <arquivo.jsonl>
"""

import hashlib
import io
import json
import re
import sys

INICIO = "0" * 64
_FIM = re.compile(r',"hash":"([0-9a-f]{64})"\}$')


def verificar(caminho):
    """Retorna (quantidade de registros válidos, lista de problemas)."""
    problemas = []
    anterior = INICIO
    seq_esperada = 1  # o primeiro registro do arquivo é sempre o seq 1
    n = 0
    with io.open(caminho, encoding="utf-8", newline="") as f:
        for num, linha in enumerate(f, 1):
            linha = linha.rstrip("\r\n")
            if not linha:
                continue
            m = _FIM.search(linha)
            if not m:
                problemas.append("linha %d: sem hash" % num)
                break
            corpo = linha[:m.start()] + "}"
            try:
                dados = json.loads(corpo)
            except ValueError:
                problemas.append("linha %d: JSON inválido" % num)
                break
            if dados.get("anterior") != anterior:
                problemas.append("linha %d: encadeamento quebrado (linha anterior removida ou alterada)" % num)
            calc = hashlib.sha256((dados.get("anterior", "") + corpo).encode("utf-8")).hexdigest()
            if calc != m.group(1):
                problemas.append("linha %d: conteúdo alterado (hash não confere)" % num)
            seq = dados.get("seq")
            if seq != seq_esperada:
                problemas.append("linha %d: sequência %s, esperada %s" % (num, seq, seq_esperada))
            seq_esperada = (seq or 0) + 1
            anterior = m.group(1)
            n += 1
    return n, problemas


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Uso: python -m iped_pcba.auditoria <mcp-auditoria.jsonl>")
        return 2
    n, problemas = verificar(argv[0])
    if problemas:
        print("AUDITORIA COM PROBLEMAS (%d registros lidos):" % n)
        for p in problemas:
            print("  - " + p)
        return 1
    print("Auditoria íntegra: %d registros, cadeia de hashes confere." % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
