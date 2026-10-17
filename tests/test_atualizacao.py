import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import __version__, atualizacao, painel  # noqa: E402


def _release(tag, pacote=True):
    corpo = {"tag_name": tag, "body": "- Fiz uma melhoria.", "html_url": "https://github.com/x/releases/" + tag,
             "published_at": "2026-10-17T12:00:00Z",
             "assets": [{"name": atualizacao.PACOTE}] if pacote else []}
    return mock.patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(corpo).encode()))


class TestAtualizacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "forense", "iped-pcba")
        os.makedirs(os.path.join(self.repo, "instalador", "iped_pcba"))
        with open(os.path.join(self.repo, "versao-antiga.txt"), "w") as f:
            f.write(__version__)
        self.home = os.path.join(self.tmp, "home")
        self.patches = [mock.patch.object(atualizacao, "REPO", self.repo),
                        mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})]
        for p in self.patches:
            p.start()
        atualizacao._CACHE.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        atualizacao._CACHE.clear()
        shutil.rmtree(self.tmp)

    def _pacote(self, versao):
        """Pacote como o do GitHub: um .zip com a pasta iped-pcba."""
        arq = os.path.join(self.tmp, "pacote.zip")
        with zipfile.ZipFile(arq, "w") as z:
            z.writestr("iped-pcba/instalador/iped_pcba/__init__.py", '__version__ = "{}"\n'.format(versao))
            z.writestr("iped-pcba/instalar.bat", "@echo off\n")
            z.writestr("iped-pcba/scripts/instalar.sh", "#!/bin/sh\n")
            z.writestr("iped-pcba/versao-nova.txt", versao)
        return arq

    def test_compara_versoes(self):
        with _release("v99.0.0"):
            r = atualizacao.verificar(forcar=True)
        self.assertTrue(r["tem_nova"])
        self.assertTrue(r["tem_pacote"])
        self.assertEqual(r["nova"], "99.0.0")
        with _release("v0.1.0"):
            self.assertFalse(atualizacao.verificar(forcar=True)["tem_nova"])
        with _release("v0.10.0"):  # 0.10 é maior que 0.4, não menor
            self.assertEqual(atualizacao.verificar(forcar=True)["tem_nova"],
                             atualizacao.chave("0.10.0") > atualizacao.chave(__version__))

    def test_sem_internet_segue(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("sem rede")):
            r = atualizacao.verificar(forcar=True)
        self.assertFalse(r["tem_nova"])
        self.assertIn("GitHub", r["erro"])

    def test_config_padrao_e_automatica(self):
        self.assertTrue(atualizacao.ler_config()["automatica"])
        self.assertFalse(atualizacao.gravar_config(False)["automatica"])
        self.assertFalse(atualizacao.ler_config()["automatica"])

    def test_copia_de_desenvolvimento_nao_se_atualiza(self):
        os.makedirs(os.path.join(self.repo, ".git"))
        with _release("v99.0.0"), self.assertRaises(RuntimeError):
            atualizacao.baixar(lambda *a: None)

    def _baixar(self, versao_no_pacote="99.0.0"):
        arq = self._pacote(versao_no_pacote)
        with _release("v99.0.0"), \
                mock.patch("iped_pcba.dependencias.asset_github",
                           return_value={"url": "x", "nome": "p.zip", "tamanho": None, "sha256": None}), \
                mock.patch("iped_pcba.dependencias.baixar", return_value=arq):
            return atualizacao.baixar(lambda *a: None)

    def test_baixa_extrai_ao_lado_e_fica_pronta(self):
        pasta = self._baixar()
        self.assertEqual(os.path.dirname(os.path.dirname(pasta)), os.path.dirname(self.repo))
        self.assertTrue(os.path.isfile(os.path.join(pasta, "versao-nova.txt")))
        self.assertEqual(atualizacao.pronta()["versao"], "99.0.0")
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "versao-antiga.txt")))  # nada trocado ainda

    def test_recusa_pacote_de_outra_versao(self):
        with self.assertRaises(RuntimeError):
            self._baixar("98.0.0")
        self.assertIsNone(atualizacao.pronta())

    @unittest.skipIf(os.name == "nt", "o teste da troca usa o script do Linux")
    def test_troca_as_pastas_depois_que_o_painel_sai(self):
        self._baixar()
        painel_falso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
        threading.Thread(target=painel_falso.wait, daemon=True).start()  # quem abriu o painel recolhe o processo
        arq, bk = atualizacao.script_troca(painel_falso.pid)
        r = subprocess.run(["sh", arq], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "versao-nova.txt")))
        self.assertTrue(os.path.isfile(os.path.join(bk, "versao-antiga.txt")))
        self.assertTrue(bk.endswith("-anterior-" + __version__))
        self.assertIsNone(atualizacao.pronta())

    def test_script_do_windows(self):
        self._baixar()
        with mock.patch.object(atualizacao, "WIN", True):
            arq, bk = atualizacao.script_troca(4321)
        with open(arq, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn('PID eq 4321', texto)
        self.assertIn('move "{}" "{}"'.format(self.repo, bk), texto)
        self.assertIn('instalar.bat', texto)
        self.assertNotIn("{", texto.replace("{}".format(self.repo), ""))  # nada sem preencher

    def test_painel_instala_ao_abrir_se_ja_baixou(self):
        self._baixar()
        with mock.patch.object(atualizacao, "iniciar_troca",
                               return_value={"anterior": "x", "script": "y", "reabre": True}) as troca, \
                mock.patch.object(painel, "ThreadingHTTPServer") as srv:
            codigo = painel.servir(None, navegador=False)
        self.assertEqual(codigo, atualizacao.CODIGO_REINICIAR)
        troca.assert_called_once_with(os.getpid())
        srv.assert_not_called()
        atualizacao.gravar_config(False)  # desligada: o painel abre normalmente
        with mock.patch.object(atualizacao, "iniciar_troca") as troca, \
                mock.patch.object(painel, "ThreadingHTTPServer") as srv, \
                mock.patch.object(painel, "atualizar_se_preciso", return_value=None):
            painel.servir(None, navegador=False)
        troca.assert_not_called()
        srv.assert_called_once()


if __name__ == "__main__":
    unittest.main()
