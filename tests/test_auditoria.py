import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import auditoria  # noqa: E402


def _linha(seq, anterior, **campos):
    """Mesmo formato do RegistroAuditoria.java (vertx JsonObject.encode, compacto)."""
    corpo = dict(seq=seq, **campos)
    corpo["anterior"] = anterior
    texto = json.dumps(corpo, ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha256((anterior + texto).encode("utf-8")).hexdigest()
    return texto[:-1] + ',"hash":"%s"}' % h, h


class TestAuditoria(unittest.TestCase):
    def _log(self, n=3):
        linhas, ant = [], auditoria.INICIO
        for i in range(1, n + 1):
            l, ant = _linha(i, ant, ferramenta="t%d" % i, caso="C:/casos/ação")
            linhas.append(l)
        return linhas

    def _gravar(self, linhas):
        fd, p = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(linhas) + "\n")
        self.addCleanup(os.remove, p)
        return p

    def test_integro(self):
        self.assertEqual(auditoria.verificar(self._gravar(self._log())), (3, []))

    def test_linha_alterada(self):
        ls = self._log()
        ls[1] = ls[1].replace('"t2"', '"tX"')
        n, probs = auditoria.verificar(self._gravar(ls))
        self.assertTrue(any("alterado" in p for p in probs))

    def test_linha_removida(self):
        ls = self._log()
        del ls[1]
        n, probs = auditoria.verificar(self._gravar(ls))
        self.assertTrue(any("encadeamento" in p for p in probs))

    def test_main_codigo_saida(self):
        self.assertEqual(auditoria.main([self._gravar(self._log())]), 0)


if __name__ == "__main__":
    unittest.main()
