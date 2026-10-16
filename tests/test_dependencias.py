import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import dependencias as dep  # noqa: E402


class Resposta(io.BytesIO):
    status = 200

    def __init__(self, dados):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDependencias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_baixa_confere_sha_e_extrai(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("iped-4.3.1/iped.jar", b"jar ficticio")
            z.writestr("plugins/Readme.txt", b"x")
        dados = buf.getvalue()
        sha = hashlib.sha256(dados).hexdigest()
        destino = os.path.join(self.tmp, "d", "iped.zip")
        with mock.patch.object(dep.urllib.request, "urlopen", return_value=Resposta(dados)):
            dep.baixar("https://exemplo/iped.zip", destino, len(dados), sha)
        dep.extrair(destino, os.path.join(self.tmp, "IPED"))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "IPED", "iped-4.3.1", "iped.jar")))
        os.remove(destino)
        with mock.patch.object(dep.urllib.request, "urlopen", return_value=Resposta(dados)):
            with self.assertRaises(RuntimeError):
                dep.baixar("https://exemplo/iped.zip", destino, len(dados), "0" * 64)
        self.assertFalse(os.path.exists(destino))  # SHA errado: arquivo apagado

    def test_zip_com_caminho_para_fora_e_recusado(self):
        z = os.path.join(self.tmp, "mau.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../fora.txt", b"x")
        with self.assertRaises(RuntimeError):
            dep.extrair(z, os.path.join(self.tmp, "alvo"))

    def test_situacao(self):
        raiz = os.path.join(self.tmp, "iped")
        os.makedirs(os.path.join(raiz, "python", "Lib", "site-packages", "faster_whisper"))
        open(os.path.join(raiz, "iped.jar"), "w").close()
        s = {i["id"]: i for i in dep.situacao(raiz)["itens"]}
        self.assertTrue(s["iped"]["ok"])
        self.assertTrue(s["plugins"]["ok"])
        self.assertIn(dep.modelo_sugerido(), ("qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b"))
        s = {i["id"]: i for i in dep.situacao(None)["itens"]}
        self.assertFalse(s["iped"]["ok"])
        self.assertTrue(s["iped"]["auto"])


if __name__ == "__main__":
    unittest.main()
