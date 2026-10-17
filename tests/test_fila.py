import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import painel, processar  # noqa: E402


class TestFilaGravada(unittest.TestCase):
    """A fila de vários casos sobrevive a fechar ou atualizar o painel."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = [mock.patch.object(processar, "PASTA", self.tmp),
                  mock.patch.object(painel.Estado, "_comando",
                                    lambda s, d: (d["evidencias"], d["saida"], ["iped"])),
                  mock.patch.object(painel.Estado, "processar", self._processar)]
        for x in self.p:
            x.start()
        self.iniciados = []

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.tmp)

    def _processar(self, d, depois=None):
        self.iniciados.append((d, depois))
        return {"tarefa": "t{}".format(len(self.iniciados))}

    def _estado(self):
        e = painel.Estado(None)
        e.tarefas.pid = lambda tid: 999999
        return e

    def _caso(self, e, nome):
        return e.fila_adicionar({"evidencias": ["/ev/" + nome], "saida": os.path.join(self.tmp, nome)})

    def test_volta_depois_de_fechar_o_painel(self):
        e = self._estado()
        self._caso(e, "a")
        self._caso(e, "b")
        e.fila_remover({"id": "1"})
        self._caso(e, "c")
        self.assertEqual([j["id"] for j in e.fila_ler()["fila"]], ["2", "3"])  # sem id repetido
        e.fila_iniciar({"grupo": "Operação fictícia"})
        self.assertEqual(len(self.iniciados), 1)

        # o painel fecha com o caso "b" no meio
        with mock.patch.object(processar, "pid_vivo", lambda pid: False):
            e2 = self._estado()
            r = e2.fila_ler()
            self.assertEqual(r["grupo"], "Operação fictícia")
            self.assertEqual([j["estado"] for j in r["fila"]], ["aguardando", "aguardando"])
            self.assertTrue(r["fila"][0]["retomar"])
            self.assertIn("continua de onde parou", r["fila"][0]["erro"])
            e2.fila_iniciar({})
        pedido = self.iniciados[-1][0]
        self.assertTrue(pedido["continuar"])  # o IPED recebe --continue
        self.assertTrue(pedido["saida"].endswith("b"))

        # terminam os dois: o grupo de multicasos é salvo e a fila seguinte começa vazia
        with mock.patch("iped_pcba.multicasos.salvar_grupo") as grupo:
            self.iniciados[-1][1](0)
            self.iniciados[-1][1](0)
        grupo.assert_called_once()
        self.assertEqual(self._estado().fila_ler()["fila"], [])

    def test_nao_reabre_iped_que_ainda_roda(self):
        e = self._estado()
        self._caso(e, "a")
        e.fila_iniciar({})
        with mock.patch.object(processar, "pid_vivo", lambda pid: pid == 999999):
            e2 = self._estado()
            e2.fila_iniciar({})
        self.assertEqual(len(self.iniciados), 1)
        j = e2.fila_ler()["fila"][0]
        self.assertEqual(j["estado"], "aguardando")
        self.assertIn("ainda está rodando", j["erro"])

    def test_arquivo_estragado_nao_impede_o_painel(self):
        with open(os.path.join(self.tmp, "fila.json"), "w") as f:
            f.write("{nao é json")
        self.assertEqual(self._estado().fila_ler()["fila"], [])

    def test_pid_vivo(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            self.assertTrue(processar.pid_vivo(p.pid))
        finally:
            p.kill()
            p.wait()
        self.assertFalse(processar.pid_vivo(p.pid))
        self.assertFalse(processar.pid_vivo(None))


if __name__ == "__main__":
    unittest.main()
