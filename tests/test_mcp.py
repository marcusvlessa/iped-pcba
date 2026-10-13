import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import mcp  # noqa: E402
from iped_pcba.configurar import Backup, reverter  # noqa: E402


class TestVersaoJava(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(mcp.versao_java('openjdk version "21.0.4" 2024-07-16'), 21)
        self.assertEqual(mcp.versao_java('java version "1.8.0_501"'), 8)
        self.assertEqual(mcp.versao_java('openjdk version "11.0.13" 2021-10-19'), 11)
        self.assertEqual(mcp.versao_java('openjdk version "25" 2025-09-16'), 25)
        self.assertEqual(mcp.versao_java(""), 0)


class TestInstalarMcp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.raiz = os.path.join(self.tmp, "iped")
        os.makedirs(os.path.join(self.raiz, "lib"))
        self.repo = os.path.join(self.tmp, "repo")
        dist = os.path.join(self.repo, "mcp-dist")
        os.makedirs(os.path.join(dist, "runtime", "bin"))
        with open(os.path.join(dist, mcp.JAR), "wb") as f:
            f.write(b"jar")
        self.java_pacote = os.path.join(dist, "runtime", "bin", "java")
        with open(self.java_pacote, "w") as f:
            f.write("")

    def test_sem_pacote(self):
        r = mcp.instalar_mcp(self.raiz, "linux", os.path.join(self.tmp, "vazio"), Backup(self.raiz))
        self.assertFalse(r["instalado"])
        self.assertIn("pacote não encontrado", r["aviso"])

    def test_sem_java_21(self):
        orig = mcp.achar_java
        mcp.achar_java = lambda so, pacote=None: (None, 11)
        try:
            r = mcp.instalar_mcp(self.raiz, "windows", self.repo, Backup(self.raiz))
        finally:
            mcp.achar_java = orig
        self.assertFalse(r["instalado"])
        self.assertIn("Java 21", r["aviso"])

    def test_achar_java_prefere_runtime_do_pacote(self):
        pac = mcp.localizar_pacote(self.repo)
        java, v = mcp.achar_java("linux", pac, versao=lambda c: 21 if c == self.java_pacote else 8)
        self.assertEqual((java, v), (self.java_pacote, 21))

    def test_instala_com_runtime_e_reverte(self):
        b = Backup(self.raiz)
        r = mcp.instalar_mcp(self.raiz, "windows", self.repo, b, java=self.java_pacote)
        b.fechar()
        destino = os.path.join(self.raiz, "pcba", "mcp")
        self.assertTrue(r["instalado"])
        self.assertTrue(os.path.isfile(os.path.join(destino, mcp.JAR)))
        self.assertTrue(os.path.isdir(os.path.join(destino, "runtime")))
        with open(r["lancador"], "rb") as f:
            bat = f.read().decode("utf-8")
        self.assertIn("\r\n", bat)
        self.assertIn(r'"%MCP%runtime', bat)            # Java relativo à pasta do MCP
        self.assertIn(r"%IPED_ROOT%\lib\*", bat)          # bibliotecas do IPED instalado
        self.assertIn("--add-opens=java.base/java.lang=ALL-UNNAMED", bat)
        self.assertIn("-Dstdout.encoding=UTF-8", bat)
        with open(os.path.join(destino, "config-clientes-ia.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["mcpServers"]["iped-pcba"]["command"], r["lancador"])
        reverter(self.raiz)
        self.assertFalse(os.path.exists(destino))

    def test_simular_nao_grava(self):
        r = mcp.instalar_mcp(self.raiz, "linux", self.repo, Backup(self.raiz), simular=True,
                             java="/usr/bin/java")
        self.assertFalse(r["instalado"])
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "pcba")))


if __name__ == "__main__":
    unittest.main()
