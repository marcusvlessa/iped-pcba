import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import cli, docxmin, painel, rt, telematica  # noqa: E402

CSV = os.path.join(os.path.dirname(__file__), "fixtures", "telematica", "registros_ficticios.csv")


def caso_falso(pasta):
    for d in ("index", "data", "lib"):
        os.makedirs(os.path.join(pasta, "iped", d))
    return pasta


class TestTelematica(unittest.TestCase):
    def test_datas_viram_horario_de_brasilia(self):
        self.assertEqual(telematica.ler_data("2026-03-01T13:00:00Z").hour, 10)
        self.assertEqual(telematica.ler_data("2026-03-01 13:00:00").hour, 10)  # sem fuso = UTC
        self.assertEqual(telematica.ler_data("2026-03-01T13:00:00-03:00").hour, 13)

    def test_resumo(self):
        regs, rejeitadas = telematica.ler_csv(CSV)
        self.assertEqual(len(regs), 150)
        self.assertEqual(len(rejeitadas), 1)
        res = {s["provedor"]: s for s in telematica.resumir(regs)}
        wa = res["WHATSAPP"]
        self.assertEqual(wa["total"], 120)
        self.assertEqual(sum(wa["tipos"].values()), 120)
        self.assertEqual(wa["interlocutores"][0][0], "+5500900000002")
        self.assertTrue(all(ip in ("203.0.113.10", "203.0.113.45", "198.51.100.7", "2001:db8::1a")
                            for ip, _ in wa["ips"]))
        texto = telematica.texto_analise(wa)
        self.assertIn("+5500900000001", texto)
        self.assertIn("horário de Brasília", texto)
        self.assertNotIn("\n-", texto)  # prosa corrida, sem tópicos

    def test_analises_deixam_conclusao_para_o_analista(self):
        regs, _ = telematica.ler_csv(CSV)
        an = telematica.analises_para_rt(telematica.resumir(regs), {"+5500900000001": "FULANO (FICTÍCIO)"})
        self.assertEqual([a["provedor"] for a in an], ["GOOGLE", "WHATSAPP"])
        wa = an[1]
        self.assertEqual(wa["tabela"][0]["investigado"], "FULANO (FICTÍCIO)")
        self.assertTrue(wa["conclusao"].startswith("["))
        self.assertEqual(an[0]["tabela"][0]["investigado"], "[INVESTIGADO]")


class TestDocx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.unidade = rt.ler_unidade(os.path.join(self.tmp, "nao-existe.json"))

    def test_tamanho_do_logo(self):
        larg, alt = docxmin.tamanho_imagem(rt.LOGO_PADRAO)
        self.assertGreater(larg, 10)
        self.assertGreater(alt, 10)

    def test_gera_docx_valido_com_lacunas_em_vermelho(self):
        regs, _ = telematica.ler_csv(CSV)
        d = rt.rt_vazio()
        d.update(numero_rt="999/2026", nome_operacao="Exemplo <fictício> & teste",
                 analises=telematica.analises_para_rt(telematica.resumir(regs)))
        saida = rt.gerar_docx(d, os.path.join(self.tmp, "RT.docx"), self.unidade)
        with zipfile.ZipFile(saida) as z:
            nomes = z.namelist()
            doc = z.read("word/document.xml").decode("utf-8")
            self.assertIn("word/header2.xml", nomes)
            self.assertIn("word/footer2.xml", nomes)
            self.assertTrue(any(n.startswith("word/media/") for n in nomes))
            self.assertIn("word/_rels/header2.xml.rels", nomes)
            import xml.dom.minidom
            for n in nomes:
                if n.endswith(".xml") or n.endswith(".rels"):
                    xml.dom.minidom.parseString(z.read(n))  # XML bem formado
        self.assertIn("EXEMPLO &lt;FICTÍCIO&gt; &amp; TESTE", doc)
        self.assertIn('<w:color w:val="FF0000"/>', doc)
        self.assertIn("DA ANÁLISE DOS DADOS TELEMÁTICOS – WHATSAPP", doc)
        self.assertIn("NUMPAGES", zipfile.ZipFile(saida).read("word/footer2.xml").decode())

    def test_lacunas(self):
        faltas = dict((t, o) for o, t in rt.lacunas(rt.rt_vazio(), self.unidade))
        self.assertIn("[NÚMERO DO PROCESSO]", faltas)
        self.assertIn("[UNIDADE]", faltas)
        d = rt.rt_vazio()
        d.update(processo="0000000-00.2026.8.05.0000")
        self.assertNotIn("[NÚMERO DO PROCESSO]", [t for _, t in rt.lacunas(d, self.unidade)])

    def test_unidade_e_emails(self):
        arq = os.path.join(self.tmp, "u.json")
        rt.gravar_unidade({"unidade": "UNIDADE FICTÍCIA", "emails_obrigatorios": ["a@example.com"],
                           "chave_estranha": 1}, arq)
        u = rt.ler_unidade(arq)
        self.assertEqual(u["unidade"], "UNIDADE FICTÍCIA")
        self.assertNotIn("chave_estranha", u)
        d = rt.preparar({"emails_investigadores": ["b@example.com"]}, u)
        self.assertEqual(d["_emails"], ["b@example.com", "a@example.com"])


class TestCaso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.caso = caso_falso(os.path.join(self.tmp, "caso"))

    def test_importar_preserva_analise_editada(self):
        cli.incorporar_telematica(self.caso, CSV)
        d = rt.ler_rt(self.caso)
        self.assertEqual(len(d["analises"]), 2)
        d["analises"][1]["texto"] = "Texto revisado pelo analista."
        del d["analises"][1]["gerado_automaticamente"]
        rt.gravar_rt(self.caso, d)
        cli.incorporar_telematica(self.caso, CSV)
        d = rt.ler_rt(self.caso)
        textos = {a["provedor"]: a["texto"] for a in d["analises"]}
        self.assertEqual(textos["WHATSAPP"], "Texto revisado pelo analista.")
        self.assertEqual(len(d["analises"]), 2)
        hist = os.listdir(os.path.join(self.caso, rt.PASTA_CASO, "historico"))
        self.assertGreaterEqual(len(hist), 2)

    def test_cli_gerar(self):
        cli.incorporar_telematica(self.caso, CSV)
        self.assertEqual(cli.main(["relatorio", "gerar", "--caso", self.caso,
                                   "--unidade", os.path.join(self.tmp, "x.json")]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.caso, rt.PASTA_CASO, "RT.docx")))

    def test_painel_hash(self):
        lista = os.path.join(self.caso, "Lista de Arquivos.csv")
        with open(lista, "w") as f:
            f.write("nome;md5\n")
        r = painel._rotear_rt("/api/rt/ler", {"caso": self.caso})
        self.assertEqual(r["listas"], [lista])
        r = painel._rotear_rt("/api/rt/hash", {"caso": self.caso, "arquivo": lista})
        self.assertEqual(r["dados"]["hashes"], ["Lista de Arquivos.csv — SHA-256: " + rt.sha256(lista)])
        with self.assertRaises(ValueError):
            painel._rotear_rt("/api/rt/ler", {"caso": self.tmp})


if __name__ == "__main__":
    unittest.main()
