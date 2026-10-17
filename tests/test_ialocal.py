import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import dependencias as dep, ialocal  # noqa: E402


class LmStudioFalso(object):
    """Responde /v1/models como o servidor do LM Studio."""

    def __init__(self, modelos):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                dados = json.dumps({"data": [{"id": m} for m in modelos]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:{}".format(self.srv.server_port)
        self.ligado = False

    def ligar(self, *a):
        self.ligado = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        if self.ligado:
            self.srv.shutdown()
        self.srv.server_close()


class TestIaLocal(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        livre = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.morta = "http://127.0.0.1:{}".format(livre.server_port)  # porta sem ninguém
        livre.server_close()
        self.p = [mock.patch.object(ialocal, "_home", lambda: self.home),
                  mock.patch.object(ialocal, "OLLAMA_URL", self.morta),
                  mock.patch.object(ialocal, "ollama_exe", lambda: None),
                  mock.patch.object(ialocal, "lms_cli", lambda: None),
                  mock.patch.object(ialocal, "lmstudio_app", lambda: None)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.home)

    def _modelo_no_disco(self, pasta, nome):
        d = os.path.join(pasta, *nome.split("/"))
        os.makedirs(d)
        open(os.path.join(d, "modelo-Q4_K_M.gguf"), "w").close()

    def test_escolhe_modelo_com_ferramentas(self):
        self.assertEqual(ialocal.escolher(["text-embedding-nomic-embed-text-v1.5", "google/gemma-2-9b",
                                           "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF", "qwen2.5-7b-instruct"]),
                         "qwen2.5-7b-instruct")
        self.assertTrue(ialocal.com_ferramentas("lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"))
        self.assertFalse(ialocal.com_ferramentas("nomic-embed-text:latest"))
        self.assertEqual(ialocal.escolher(["nomic-embed-text:latest"]), "")

    def test_acha_modelos_do_lm_studio_e_do_ollama_no_disco(self):
        self.assertFalse(ialocal.lmstudio_instalado())
        outra = os.path.join(self.home, "D", "modelos")  # pasta trocada nas configurações do LM Studio
        os.makedirs(os.path.join(self.home, ".lmstudio"))
        with open(os.path.join(self.home, ".lmstudio", "settings.json"), "w") as f:
            json.dump({"downloadsFolder": outra}, f)
        self._modelo_no_disco(outra, "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        self._modelo_no_disco(os.path.join(self.home, ".lmstudio", "models"), "nomic-ai/nomic-embed-text-v1.5-GGUF")
        self.assertTrue(ialocal.lmstudio_instalado())
        self.assertEqual(ialocal.lmstudio_baixados(), ["lmstudio-community/Qwen2.5-7B-Instruct-GGUF"])
        man = os.path.join(self.home, ".ollama", "models", "manifests", "registry.ollama.ai", "library", "qwen2.5")
        os.makedirs(man)
        open(os.path.join(man, "7b"), "w").close()
        with mock.patch.dict(os.environ, {"OLLAMA_MODELS": ""}):
            self.assertEqual(ialocal.ollama_baixados(), ["qwen2.5:7b"])

    def test_automatico_usa_lm_studio_ligado(self):
        lm = LmStudioFalso(["text-embedding-nomic-embed-text-v1.5", "google/gemma-3-4b", "qwen2.5-7b-instruct"])
        lm.ligar()
        avisos = []
        try:
            with mock.patch.object(ialocal, "LMSTUDIO_URL", lm.url):
                cfg = ialocal.preparar({"tipo": "auto"}, avisos.append)
        finally:
            lm.fechar()
        self.assertEqual(cfg, {"tipo": "openai", "url": lm.url, "modelo": "qwen2.5-7b-instruct"})
        self.assertTrue(any("qwen2.5-7b-instruct" in a for a in avisos))

    def test_liga_o_lm_studio_desligado(self):
        self._modelo_no_disco(os.path.join(self.home, ".lmstudio", "models"), "qwen/qwen3-8b")
        lm = LmStudioFalso(["qwen/qwen3-8b"])
        avisos = []
        try:
            with mock.patch.object(ialocal, "LMSTUDIO_URL", lm.url), mock.patch.object(ialocal, "ligar", lm.ligar):
                sv = {s["nome"]: s for s in ialocal.servidores()}["LM Studio"]
                self.assertEqual((sv["instalado"], sv["ativo"]), (True, False))
                cfg = ialocal.preparar({"tipo": "auto"}, avisos.append, espera=10)
        finally:
            lm.fechar()
        self.assertEqual(cfg["modelo"], "qwen/qwen3-8b")
        self.assertIn("Ligando o servidor do LM Studio…", avisos)

    def test_sem_ia_local(self):
        with mock.patch.object(ialocal, "LMSTUDIO_URL", self.morta):
            with self.assertRaises(RuntimeError) as e:
                ialocal.preparar({"tipo": "auto"})
        self.assertIn("Nenhuma IA local", str(e.exception))

    def test_dependencias_reconhece_lm_studio_e_skills(self):
        self._modelo_no_disco(os.path.join(self.home, ".lmstudio", "models"), "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        dep._MAIS_NOVA[:] = ["4.3.1"]
        with mock.patch.object(ialocal, "LMSTUDIO_URL", self.morta), mock.patch.object(dep, "ollama_exe", lambda: None):
            s = {i["id"]: i for i in dep.situacao(None)["itens"]}
        self.assertTrue(s["modelo"]["ok"])
        self.assertIn("LM Studio: lmstudio-community/Qwen2.5-7B-Instruct-GGUF", s["modelo"]["detalhe"])
        self.assertFalse(s["ollama"]["aplica"])  # com modelo no LM Studio, o Ollama não é instalado pelo "tudo"
        self.assertIn("skills", s)
        self.assertTrue(s["skills"]["auto"])


class TestRapido(unittest.TestCase):
    def test_servidores_nao_chama_o_lms(self):
        """A tela do Assistente não pode esperar o 'lms ls' (vários segundos)."""
        with mock.patch.object(ialocal, "lms_cli", lambda: "/x/lms"), \
                mock.patch("subprocess.run", side_effect=AssertionError("chamou o lms")):
            ialocal.servidores(timeout=0.2)

    def test_skills_ok_sem_os_zips_do_claude_desktop(self):
        sit = {"skills": [1, 2], "destinos": [
            {"id": "claude-code", "nome": "Claude Code", "detectado": True,
             "itens": [{"estado": "instalada"}, {"estado": "instalada"}]},
            {"id": "zip", "nome": "Claude Desktop", "detectado": True, "manual": True,
             "itens": [{"estado": "falta"}, {"estado": "falta"}]}]}
        with mock.patch("iped_pcba.skills.situacao", return_value=sit):
            item = dep._item_skills()
        self.assertTrue(item["ok"])
        self.assertIn("0 de 2 enviadas", item["detalhe"])


if __name__ == "__main__":
    unittest.main()
