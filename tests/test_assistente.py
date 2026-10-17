import glob
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import agentes, assistente, clientesia, perfis  # noqa: E402
from iped_pcba.mcpcliente import ClienteMcp  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
MCP_FALSO = os.path.join(AQUI, "fixtures", "assistente", "mcp_falso.py")
FONTES_MCP = os.path.join(AQUI, "..", "mcp", "src", "main", "java")


class IaFalsa(object):
    """Servidor HTTP no lugar do Ollama ou do LM Studio: na 1ª vez pede uma busca, depois responde."""

    def __init__(self, tipo):
        self.pedidos = []
        dono = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                dono.pedidos.append((self.path, corpo))
                resultado = [m for m in corpo["messages"] if m["role"] == "tool"]
                if tipo == "ollama":
                    if resultado:
                        msg = {"role": "assistant", "content": "Achei: " + resultado[-1]["content"]}
                    else:
                        msg = {"role": "assistant", "content": "", "tool_calls": [
                            {"function": {"name": "search_documents", "arguments": {"query": "pix"}}}]}
                    r = {"message": msg}
                else:
                    if resultado:
                        msg = {"role": "assistant", "content": "Achei: " + resultado[-1]["content"]}
                    else:
                        msg = {"role": "assistant", "content": None, "tool_calls": [
                            {"id": "call_1", "type": "function",
                             "function": {"name": "search_documents", "arguments": "{\"query\": \"pix\"}"}}]}
                    r = {"choices": [{"message": msg}]}
                dados = json.dumps(r).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:{}".format(self.srv.server_port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestAgentes(unittest.TestCase):
    def test_ferramentas_existem_no_mcp(self):
        nomes = set()
        for arq in glob.glob(os.path.join(FONTES_MCP, "**", "*.java"), recursive=True):
            with open(arq, encoding="utf-8") as f:
                nomes.update(re.findall(r'@Tool\(\s*name\s*=\s*"([a-z_]+)"', f.read()))
        self.assertGreater(len(nomes), 20)
        for a in agentes.AGENTES:
            self.assertEqual(set(a["ferramentas"]) - nomes, set(), a["id"])

    def test_agentes_completos(self):
        ids = [a["id"] for a in agentes.AGENTES]
        self.assertEqual(len(ids), len(set(ids)))
        for a in agentes.para_painel():
            self.assertTrue(a["prompts"] and a["descricao"])
            self.assertIn("doc_id", a["sistema"])
        self.assertIn("Pergunta:\nX", agentes.texto_para_copiar(agentes.por_id("triagem"), "X"))
        with self.assertRaises(ValueError):
            agentes.por_id("nao-existe")

    def test_escrita_so_nos_agentes_de_escrita(self):
        escrita = {"bookmark_search_results", "add_to_bookmark", "set_bookmark_comment", "update_report_field",
                   "update_report_analysis"}
        for a in agentes.AGENTES:
            if not a.get("escrita"):
                self.assertEqual(set(a["ferramentas"]) & escrita, set(), a["id"])


class TestConfigIa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.arq = os.path.join(self.tmp, "ia.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_padrao_e_gravacao(self):
        self.assertEqual(assistente.ler_config(self.arq), {"tipo": "auto", "url": "", "modelo": ""})
        assistente.gravar_config({"tipo": "openai", "url": "http://localhost:1234/", "modelo": " qwen "}, self.arq)
        self.assertEqual(assistente.ler_config(self.arq),
                         {"tipo": "openai", "url": "http://localhost:1234", "modelo": "qwen"})

    def test_so_ia_local(self):
        for url in ("https://api.exemplo.com", "http://127.0.0.1.exemplo.com", "http://localhost.exemplo.com:80",
                    "http://usuario@127.0.0.1", "http://10.0.0.5:11434"):
            with self.assertRaises(ValueError, msg=url):
                assistente.gravar_config({"tipo": "ollama", "url": url}, self.arq)
        with self.assertRaises(ValueError):
            assistente.modelo_de({"tipo": "ollama", "url": "http://10.0.0.5", "modelo": "x"})
        with self.assertRaises(ValueError):
            assistente.gravar_config({"tipo": "nuvem"}, self.arq)
        with self.assertRaises(ValueError):
            assistente.modelo_de({"tipo": "ollama", "url": "", "modelo": ""})


class TestConversa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _executar(self, tipo, agente="financeiro", escrita=False):
        ia = IaFalsa(tipo)
        mcp = ClienteMcp([sys.executable, MCP_FALSO], timeout=30)
        eventos = []
        try:
            mcp.iniciar()
            modelo = assistente.modelo_de({"tipo": tipo, "url": ia.url, "modelo": "falso"})
            texto = assistente.executar(modelo, mcp, agentes.por_id(agente), "Procure PIX", eventos.append, escrita)
        finally:
            mcp.fechar()
            ia.fechar()
        return texto, eventos, ia.pedidos

    def test_ollama(self):
        texto, eventos, pedidos = self._executar("ollama")
        self.assertIn("doc_id 11", texto)
        self.assertEqual([p for p, _ in pedidos], ["/api/chat", "/api/chat"])
        # só as ferramentas do agente que o MCP oferece
        self.assertEqual(sorted(t["function"]["name"] for t in pedidos[0][1]["tools"]),
                         ["get_case_summary", "search_documents"])
        tool = [m for m in pedidos[1][1]["messages"] if m["role"] == "tool"][0]
        self.assertEqual(tool["tool_name"], "search_documents")
        self.assertEqual([e["tipo"] for e in eventos], ["pensando", "ferramenta", "resultado", "pensando", "resposta"])
        self.assertEqual(pedidos[0][1]["messages"][0]["role"], "system")

    def test_openai(self):
        texto, eventos, pedidos = self._executar("openai")
        self.assertIn("'pix'", texto)
        self.assertEqual(pedidos[0][0], "/v1/chat/completions")
        msgs = pedidos[1][1]["messages"]
        self.assertEqual(msgs[2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(msgs[3], {"role": "tool", "tool_call_id": "call_1",
                                   "content": msgs[3]["content"]})

    def test_agente_de_escrita_avisa_sem_escrita(self):
        _, eventos, pedidos = self._executar("ollama", agente="marcador", escrita=False)
        self.assertEqual(eventos[0]["tipo"], "aviso")

    def test_ferramenta_fora_do_agente_nao_roda(self):
        class Modelo(object):
            n = 0

            def responder(self, mensagens, ferramentas):
                self.n += 1
                if self.n == 1:
                    return "", [{"id": "c0", "nome": "bookmark_search_results", "args": {}}], {"role": "assistant"}
                return "fim", [], {"role": "assistant", "content": "fim"}

            def resultado(self, chamada, texto):
                return {"role": "tool", "content": texto}

        mcp = ClienteMcp([sys.executable, MCP_FALSO], timeout=30)
        eventos = []
        try:
            mcp.iniciar()
            assistente.executar(Modelo(), mcp, agentes.por_id("triagem"), "x", eventos.append)
        finally:
            mcp.fechar()
        r = [e for e in eventos if e["tipo"] == "resultado"][0]
        self.assertIn("não permitida", r["trecho"])

    def test_conversas_em_segundo_plano_e_salvar(self):
        if os.name == "nt":
            lanc = os.path.join(self.tmp, "mcp.bat")
            with open(lanc, "w") as f:
                f.write('@"{}" "{}" %*\n'.format(sys.executable, MCP_FALSO))
        else:
            lanc = os.path.join(self.tmp, "mcp.sh")
            with open(lanc, "w") as f:
                f.write('#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, MCP_FALSO))
            os.chmod(lanc, 0o755)
        ia = IaFalsa("ollama")
        conv = assistente.Conversas()
        try:
            cid = conv.iniciar(lanc, self.tmp, "triagem", "Resumo", {"tipo": "ollama", "url": ia.url,
                                                                     "modelo": "falso"}, False)
            limite = time.time() + 30
            while conv.ler(cid)["rodando"] and time.time() < limite:
                time.sleep(0.1)
            r = conv.ler(cid)
        finally:
            ia.fechar()
        self.assertFalse(r["rodando"])
        self.assertIn("Achei:", r["resposta"])
        self.assertEqual(conv.ler(cid, desde=r["pos"])["eventos"], [])
        with self.assertRaises(ValueError):
            conv.iniciar(lanc, self.tmp, "triagem", "  ", {"tipo": "ollama", "modelo": "x"}, False)
        arq = assistente.salvar(self.tmp, "Triagem inicial", "Resumo", r["resposta"], "falso")
        self.assertTrue(arq.endswith("-triagem-inicial.md"))
        with open(arq, encoding="utf-8") as f:
            self.assertIn("revisar antes de usar", f.read())


class TestAntigravityEPerfis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home_antes = os.environ.get("HOME"), os.environ.get("USERPROFILE")
        os.environ["HOME"] = os.environ["USERPROFILE"] = self.tmp

    def tearDown(self):
        for k, v in zip(("HOME", "USERPROFILE"), self.home_antes):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp)

    def test_antigravity(self):
        cam = clientesia.caminho_cliente("antigravity")
        self.assertEqual(cam, os.path.join(self.tmp, ".gemini", "antigravity", "mcp_config.json"))
        os.makedirs(os.path.dirname(cam))
        with open(cam, "w") as f:
            json.dump({"mcpServers": {"outro": {"command": "x"}}}, f)
        clientesia.configurar("antigravity", "/opt/iped/pcba/mcp/iped-pcba-mcp.sh")
        with open(cam) as f:
            d = json.load(f)
        self.assertIn("outro", d["mcpServers"])
        self.assertEqual(d["mcpServers"]["iped-pcba"]["command"], "/opt/iped/pcba/mcp/iped-pcba-mcp.sh")
        s = {c["cliente"]: c for c in clientesia.situacao("/opt/iped/pcba/mcp/iped-pcba-mcp.sh")}
        self.assertTrue(s["antigravity"]["aponta_para_este"])
        self.assertTrue(s["antigravity"]["nuvem"] and s["claude"]["nuvem"])
        self.assertFalse(s["lmstudio"]["nuvem"])

    def test_ajuda_dos_perfis(self):
        for nome in perfis.PERFIS:
            a = perfis.ajuda(nome)
            self.assertTrue(a["pcba"])
            self.assertTrue(a["quando"] and a["liga"] and a["tempo"], nome)
        self.assertFalse(perfis.ajuda("forensic")["pcba"])


if __name__ == "__main__":
    unittest.main()
