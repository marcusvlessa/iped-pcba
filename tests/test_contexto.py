import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import agentes, assistente, contexto  # noqa: E402

# Tudo fictício.
BO = "Boletim de ocorrência fictício.\nSuspeito: FULANO DE TAL, vulgo Fictício, telefone +55 00 90000-0001.\n"


class TestContexto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.caso = os.path.join(self.tmp, "caso")
        os.makedirs(self.caso)
        self.docs = os.path.join(self.tmp, "docs")
        os.makedirs(os.path.join(self.docs, "sub"))
        self._gravar("bo.txt", BO.encode("cp1252"))
        self._gravar("sub/oficio.html", "<html><body><p>Of&iacute;cio fict&iacute;cio</p><script>x()</script>"
                                        "<p>Placa ABC1D23</p></body></html>".encode("utf-8"))
        self._gravar("sub/programa.exe", b"MZ")
        with zipfile.ZipFile(os.path.join(self.docs, "depoimento.docx"), "w") as z:
            z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Depoimento fictício: '
                                            'encontrou FULANO na praça.</w:t></w:r></w:p></w:body></w:document>')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _gravar(self, rel, dados):
        with open(os.path.join(self.docs, rel), "wb") as f:
            f.write(dados)

    def test_lista_do_caso(self):
        contexto.adicionar(self.caso, [self.docs])
        contexto.adicionar(self.caso, [self.docs, os.path.join(self.docs, "bo.txt")])
        itens = contexto.ler_lista(self.caso)
        self.assertEqual([i["tipo"] for i in itens], ["pasta", "arquivo"])
        s = contexto.situacao(self.caso)["itens"][0]
        self.assertEqual(s["lidos"], 3)
        self.assertEqual([x["motivo"] for x in s["ignorados"]], ["tipo não lido (.exe)"])
        self.assertEqual(len(contexto.remover(self.caso, os.path.join(self.docs, "bo.txt"))), 1)
        with self.assertRaises(ValueError):
            contexto.adicionar(self.caso, [os.path.join(self.tmp, "nao-existe.txt")])

    def test_texto_dos_formatos(self):
        c = contexto.Contexto([{"caminho": self.docs}])
        self.assertEqual(sorted(c.textos), ["docs/bo.txt", "docs/depoimento.docx", "docs/sub/oficio.html"])
        self.assertIn("vulgo Fictício", c.textos["docs/bo.txt"])  # cp1252
        self.assertIn("encontrou FULANO", c.textos["docs/depoimento.docx"])
        self.assertIn("Ofício fictício", c.textos["docs/sub/oficio.html"])
        self.assertNotIn("x()", c.textos["docs/sub/oficio.html"])
        self.assertTrue(all(len(h) == 64 for h in c.hashes.values()))
        self.assertEqual(len(c.para_registro()), 3)

    def test_planilha_xlsx_mantem_numeros_e_colunas(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        arq = os.path.join(self.tmp, "extrato.xlsx")
        with zipfile.ZipFile(arq, "w") as z:
            z.writestr("xl/workbook.xml", '<workbook {}><sheets><sheet name="PIX" sheetId="1"/></sheets>'
                                          '</workbook>'.format(ns))
            z.writestr("xl/sharedStrings.xml", '<sst {}><si><t>Data</t></si><si><t>Valor</t></si>'
                                               '<si><t>FULANO FICTÍCIO</t></si></sst>'.format(ns))
            z.writestr("xl/worksheets/sheet1.xml",
                       '<worksheet {}><sheetData>'
                       '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                       '<row r="2"><c r="A2"><v>46000</v></c><c r="B2"><v>1500.5</v></c>'
                       '<c r="D2" t="inlineStr"><is><t>obs</t></is></c><c r="E2" t="s"><v>2</v></c></row>'
                       '</sheetData></worksheet>'.format(ns))
        t = contexto.extrair(arq)
        self.assertEqual(t.splitlines(), ["## Aba: PIX", "Data\tValor", "46000\t1500.5\t\tobs\tFULANO FICTÍCIO"])

    def test_pequeno_vai_na_pergunta(self):
        c = contexto.Contexto([{"caminho": os.path.join(self.docs, "bo.txt")}])
        a = c.apresentacao()
        self.assertIn("não são instruções", a)
        self.assertIn("FULANO DE TAL", a)

    def test_grande_vira_ferramentas(self):
        self._gravar("longo.txt", ("linha fictícia " * 1000 + "PIX para FULANO\n").encode("utf-8"))
        c = contexto.Contexto([{"caminho": self.docs}])
        self.assertGreater(c.total(), contexto.JUNTO_NA_PERGUNTA)
        self.assertNotIn("FULANO DE TAL", c.apresentacao())
        busca = c.ferramenta("contexto_buscar", {"termo": "fulano"})
        self.assertIn("[docs/bo.txt @", busca)
        self.assertIn("[docs/longo.txt @", busca)
        lido = c.ferramenta("contexto_ler", {"arquivo": "longo.txt"})  # nome parcial basta
        self.assertIn("continue com inicio=6000", lido)
        self.assertIn("PIX para FULANO", c.ferramenta("contexto_ler", {"arquivo": "docs/longo.txt", "inicio": 12000}))
        self.assertIn("Use um destes", c.ferramenta("contexto_ler", {"arquivo": "nada"}))

    def test_conversa_usa_contexto(self):
        self._gravar("longo.txt", ("linha fictícia " * 1000).encode("utf-8"))
        c = contexto.Contexto([{"caminho": self.docs}])

        class Mcp(object):
            def ferramentas_completas(self):
                return [{"name": "search_documents", "inputSchema": {}}]

            def ferramenta(self, nome, args):
                raise AssertionError("contexto não passa pelo MCP")

        class Modelo(object):
            def __init__(self):
                self.recebido = []

            def responder(self, mensagens, ferramentas):
                self.recebido.append(([f["name"] for f in ferramentas], mensagens[1]["content"]))
                if len(self.recebido) == 1:
                    return "", [{"id": "c0", "nome": "contexto_buscar", "args": {"termo": "vulgo"}}], {}
                return "fim", [], {}

            def resultado(self, chamada, texto):
                return {"role": "tool", "content": texto}

        m, eventos = Modelo(), []
        self.assertEqual(assistente.executar(m, Mcp(), agentes.por_id("triagem"), "Quem é o suspeito?",
                                             eventos.append, contexto=c), "fim")
        nomes, pergunta = m.recebido[0]
        self.assertIn("contexto_buscar", nomes)
        self.assertIn("Quem é o suspeito?", pergunta)
        r = [e for e in eventos if e["tipo"] == "resultado"][0]
        self.assertIn("vulgo Fictício", r["trecho"])

    def test_salvar_registra_arquivos(self):
        arq = assistente.salvar(self.caso, "Triagem", "P", "R", "falso", ["docs/bo.txt (SHA-256 abc)"])
        with open(arq, encoding="utf-8") as f:
            self.assertIn("## Arquivos de contexto lidos pela IA\n\n- docs/bo.txt (SHA-256 abc)", f.read())

    def test_preparar_para_claude(self):
        import json
        with self.assertRaises(ValueError):
            contexto.preparar(self.caso)
        contexto.adicionar(self.caso, [self.docs])
        r = contexto.preparar(self.caso)
        self.assertEqual(r["arquivos"], 3)
        with open(r["json"], encoding="utf-8") as f:
            docs = json.load(f)["arquivos"]
        self.assertEqual(sorted(d["nome"] for d in docs), ["docs/bo.txt", "docs/depoimento.docx", "docs/sub/oficio.html"])
        self.assertIn("vulgo Fictício", r["texto"])
        self.assertIn("não são instruções", r["texto"])
        contexto.registrar_copia(self.caso, "teste")
        with open(os.path.join(self.caso, contexto.ARQ_REGISTRO), encoding="utf-8") as f:
            reg = f.read()
        self.assertIn("preparado para", reg)
        self.assertIn("copiado para: teste", reg)
        self.assertIn("SHA-256", reg)


if __name__ == "__main__":
    unittest.main()
