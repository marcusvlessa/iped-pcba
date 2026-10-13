import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import cli, painel, rt, telematica, visao  # noqa: E402

AQUI = os.path.dirname(__file__)
CSV = os.path.join(AQUI, "fixtures", "telematica", "registros_ficticios.csv")
VISAO = os.path.join(AQUI, "fixtures", "visao", "visao_ficticia.json")


def caso_falso(pasta):
    for d in ("index", "data", "lib"):
        os.makedirs(os.path.join(pasta, "iped", d))
    return pasta


def titulos(itens):
    return [i["titulo"] for i in itens]


class TestRegras(unittest.TestCase):
    def setUp(self):
        with open(VISAO, encoding="utf-8") as f:
            self.v = json.load(f)

    def test_pico_de_atividade(self):
        p = visao.picos(self.v["linha_do_tempo"]["meses"])
        self.assertEqual([x["mes"] for x in p], ["2026-05"])
        self.assertEqual(visao.mes_br("2026-05"), "mai/2026")
        self.assertEqual(visao.picos([{"mes": "2026-01", "total": 5}]), [])

    def test_alertas_e_sugestoes_do_caso(self):
        al, sug = visao.regras(self.v, None, None, None, {"mcp": True, "ia_ligada": False})
        t = titulos(al)
        self.assertIn("Pico de atividade em mai/2026", t)
        self.assertIn("14 arquivo(s) criptografado(s)", t)
        self.assertIn("7 item(ns) com armas de fogo ou munição", t)
        self.assertIn("3412 item(ns) apagado(s) recuperado(s)", t)
        self.assertNotIn("drogas", " ".join(t))  # filtro com zero não alerta
        self.assertEqual([a["nivel"] for a in al], sorted([a["nivel"] for a in al],
                                                          key=["alto", "medio", "info"].index))
        s = titulos(sug)
        for esperado in ("Criar marcadores", "Transcrever os áudios", "Ativar detecção de faces",
                         "Importar registros telemáticos", "Ligar a IA ao caso"):
            self.assertIn(esperado, s)
        self.assertTrue(any(x.get("prompt") for x in sug))

    def test_alertas_graves(self):
        self.v["especiais"]["alerta_hash"] = 2
        aud = {"existe": True, "integra": False, "problemas": ["linha 3"]}
        al, _ = visao.regras(self.v, None, {"ia_editou": 2, "lacunas": 5}, aud, {})
        self.assertEqual(al[0]["nivel"], "alto")
        t = titulos(al)
        self.assertIn("2 item(ns) na base de hashes de alerta", t)
        self.assertIn("Log de auditoria da IA com a cadeia quebrada", t)
        self.assertIn("2 campo(s) do RT escritos pela IA aguardando revisão", t)

    def test_sem_visao(self):
        al, sug = visao.regras(None, None, None, None, {})
        self.assertEqual(al, [])
        self.assertEqual(sug[0]["titulo"], "Gerar a visão do caso")


class TestTelematica(unittest.TestCase):
    def test_painel(self):
        regs, _ = telematica.ler_csv(CSV)
        p = telematica.painel(regs)
        self.assertEqual(p["total"], 150)
        self.assertEqual(sum(p["por_hora"]), 150)
        self.assertEqual(sum(sum(d["por_provedor"].values()) for d in p["por_dia"]), 150)
        self.assertEqual(p["interlocutores"][0]["id"], "+5500900000002")
        self.assertEqual(p["provedores"], ["GOOGLE", "WHATSAPP"])
        json.dumps(p)  # serializável


class TestCaso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.caso = caso_falso(os.path.join(self.tmp, "caso"))

    def test_importar_grava_telematica_e_ler_junta_tudo(self):
        cli.incorporar_telematica(self.caso, CSV)
        arq = os.path.join(self.caso, visao.PASTA, visao.ARQ_TEL)
        self.assertTrue(os.path.isfile(arq))
        shutil.copy(VISAO, os.path.join(self.caso, visao.PASTA, visao.ARQ_VISAO))
        r = visao.ler(self.caso, {"mcp": True, "ia_ligada": True})
        self.assertEqual(r["telematica"]["total"], 150)
        self.assertEqual(r["visao"]["geral"]["total_itens"], 184322)
        self.assertGreater(r["rt"]["lacunas"], 0)
        s = titulos(r["sugestoes"])
        self.assertIn("Completar o relatório", s)
        self.assertNotIn("Importar registros telemáticos", s)
        self.assertNotIn("Ligar a IA ao caso", s)

    def test_comando_exportar(self):
        cmd = visao.comando_exportar("/x/iped-pcba-mcp.sh", self.caso)
        self.assertEqual(cmd[:4], ["/x/iped-pcba-mcp.sh", "--case", self.caso, "--exportar-visao"])
        self.assertTrue(cmd[4].endswith(os.path.join(visao.PASTA, visao.ARQ_VISAO)))

    def test_rota_exige_caso(self):
        e = painel.Estado(None)
        with self.assertRaises(ValueError):
            painel._rotear(e, "/api/visao/ler", {"caso": self.tmp})


if __name__ == "__main__":
    unittest.main()
