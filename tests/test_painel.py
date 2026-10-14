import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import clientesia, mcp, painel, processar  # noqa: E402
from iped_pcba.configurar import Backup  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "iped-4.3.1")


class TestClientesIa(unittest.TestCase):
    def test_yaml_cria_secao(self):
        t = clientesia.mesclar_yaml("model:\n  x: 1\n", "C:\\IPED\\m.bat", [])
        self.assertIn("mcp_servers:\n  iped-pcba:\n    command: \"C:\\\\IPED\\\\m.bat\"", t)
        self.assertTrue(t.startswith("model:\n  x: 1\n"))

    def test_yaml_troca_so_a_entrada(self):
        orig = ("model: 1\nmcp_servers:\n    fs:\n        command: npx\n"
                "    iped-pcba:\n        command: velho\n        args: []\ntoolsets: []\n")
        t = clientesia.mesclar_yaml(orig, "/novo.sh", ["--case", "/c"])
        self.assertIn("    fs:\n        command: npx\n", t)
        self.assertIn("    iped-pcba:\n        command: \"/novo.sh\"\n        args: [\"--case\", \"/c\"]\n", t)
        self.assertNotIn("velho", t)
        self.assertTrue(t.endswith("toolsets: []\n"))

    def test_yaml_remover(self):
        t = clientesia.mesclar_yaml("model: 1\n", "/a", [])
        self.assertEqual(clientesia.remover_yaml(t), "model: 1\n")
        t = clientesia.mesclar_yaml("mcp_servers:\n  fs:\n    command: x\n", "/a", [])
        self.assertEqual(clientesia.remover_yaml(t), "mcp_servers:\n  fs:\n    command: x\n")

    def test_json_preserva_o_resto(self):
        d = clientesia.mesclar_json({"mcpServers": {"outro": {"command": "x"}}, "pref": 1}, "/m", [])
        self.assertEqual(d["pref"], 1)
        self.assertEqual(d["mcpServers"]["outro"], {"command": "x"})
        self.assertEqual(d["mcpServers"]["iped-pcba"], {"command": "/m", "args": []})
        self.assertNotIn("iped-pcba", clientesia.remover_json(d)["mcpServers"])


class TestProcessar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.evid = os.path.join(self.tmp, "evid.e01")
        open(self.evid, "w").close()

    def test_comando(self):
        cmd = processar.comando_processar("/iped", [self.evid], os.path.join(self.tmp, "caso"),
                                          perfil="pcba-celular", heap=12)
        self.assertEqual(cmd[1:3], ["-jar", os.path.join("/iped", "iped.jar")])
        self.assertEqual(cmd[3], "-Xmx12g")  # o IPED exige -Xmx depois do iped.jar
        self.assertIn("--nogui", cmd)
        self.assertEqual(cmd[cmd.index("-profile") + 1], "pcba-celular")
        self.assertEqual(cmd[cmd.index("-d") + 1], self.evid)

    def test_recusa_pasta_com_caso(self):
        caso = os.path.join(self.tmp, "caso")
        for d in ("index", "data", "lib"):
            os.makedirs(os.path.join(caso, "iped", d))
        with self.assertRaises(ValueError):
            processar.comando_processar("/iped", [self.evid], caso)
        cmd = processar.comando_processar("/iped", [self.evid], caso, adicionar=True)
        self.assertIn("--append", cmd)

    def test_recusa_evidencia_inexistente(self):
        with self.assertRaises(ValueError):
            processar.comando_processar("/iped", [self.evid + "x"], os.path.join(self.tmp, "c"))


class TestEscrita(unittest.TestCase):
    def test_lancador_le_o_arquivo_de_escrita(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        raiz = os.path.join(tmp, "iped")
        os.makedirs(os.path.join(raiz, "lib"))
        jar = os.path.join(tmp, "x.jar")
        open(jar, "w").close()
        pacote = {"jar": jar, "runtime": None, "origem": "teste"}
        for so, nome in (("windows", "iped-pcba-mcp.bat"), ("linux", "iped-pcba-mcp.sh")):
            r = mcp.instalar_mcp(raiz, so, tmp, Backup(raiz), java="/j/java", pacote=pacote,
                                 escrita=False)
            self.assertFalse(r["escrita"])
            with open(os.path.join(raiz, mcp.PASTA_MCP, nome), encoding="utf-8") as f:
                texto = f.read()
            self.assertIn(mcp.ARQ_ESCRITA, texto)
            self.assertIn("--permitir-escrita", texto)
        self.assertFalse(mcp.escrita_ativa(raiz))
        self.assertTrue(mcp.definir_escrita(raiz, True))
        self.assertFalse(mcp.definir_escrita(raiz, False))


class TestJanelaEscolha(unittest.TestCase):
    def test_windows_traz_janela_para_frente(self):
        chamadas = []

        class R(object):
            stdout = "C:\\Evid\n".encode("utf-8")

        antes = painel.WIN, painel.subprocess.run
        painel.WIN = True
        painel.subprocess.run = lambda cmd, **k: chamadas.append(cmd[-1]) or R()
        try:
            self.assertEqual(painel.escolher("pasta", "Pasta d'evidência"), ["C:\\Evid"])
            painel.escolher("arquivo", "Evidência", multiplos=True, filtro="evidencia")
        finally:
            painel.WIN, painel.subprocess.run = antes
        for ps in chamadas:
            # a janela-dona aparece e ganha foco antes do diálogo, senão ele nasce atrás do navegador
            self.assertLess(ps.index("$f.Activate()"), ps.index("ShowDialog($f)"))
            self.assertIn("TopMost=$true", ps)
            self.assertTrue(ps.endswith("$f.Close()"))
        self.assertIn("Description='Pasta devidência'", chamadas[0])
        self.assertIn("Multiselect=$true", chamadas[1])


class TestServidor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.raiz = os.path.join(self.tmp, "iped")
        shutil.copytree(FIXTURE, self.raiz)
        open(os.path.join(self.raiz, "iped.jar"), "w").close()
        estado = painel.Estado(self.raiz)
        with open(os.path.join(os.path.dirname(painel.__file__), "painel.html"), encoding="utf-8") as f:
            html = f.read()
        self.srv = painel.ThreadingHTTPServer(("127.0.0.1", 0), painel._handler(estado, html))
        estado.servidor = self.srv
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = "http://127.0.0.1:{}".format(self.srv.server_address[1])
        self.token = estado.token
        self.abrir = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def post(self, rota, dados=None, token=None):
        req = urllib.request.Request(self.base + "/api/" + rota, data=json.dumps(dados or {}).encode(),
                                     headers={"X-Token": token or self.token,
                                              "Content-Type": "application/json"})
        with self.abrir(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def test_token_obrigatorio(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("resumo", token="errado")
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError):
            self.abrir(self.base + "/?t=errado", timeout=10)
        with self.abrir(self.base + "/?t=" + self.token, timeout=10) as r:
            pagina = r.read().decode()
        self.assertIn(self.token, pagina)
        self.assertNotIn("__TOKEN__", pagina)

    def test_resumo(self):
        r = self.post("resumo")
        self.assertTrue(r["iped_ok"])
        self.assertEqual(r["versao_iped"], "4.3.1")
        self.assertFalse(r["configurado"])

    def test_erro_vira_mensagem(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("caso/ativar", {"pasta": self.tmp})
        self.assertEqual(e.exception.code, 400)
        self.assertIn("não é um caso", json.loads(e.exception.read().decode())["erro"])


if __name__ == "__main__":
    unittest.main()
