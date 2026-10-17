import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import multicasos  # noqa: E402

# Dois casos fictícios: o titular do caso B aparece como contato no caso A; um contato é comum aos dois.
A = {"rede": {"nodes": [{"id": "TITULAR A", "label": "TITULAR A"}, {"id": "5571999990001@s.whatsapp.net", "label": "Beltrano"},
                        {"id": "+55 71 98888-0002", "label": "Comum"}, {"id": "Fulano Silva", "label": "Fulano Silva"}],
             "edges": [{"source": "TITULAR A", "target": "5571999990001@s.whatsapp.net", "weight": 30, "messages_count": 30,
                        "calls_count": 0, "channels": ["WhatsApp"]},
                       {"source": "+55 71 98888-0002", "target": "TITULAR A", "weight": 5, "messages_count": 5,
                        "calls_count": 0, "channels": ["WhatsApp"]},
                       {"source": "TITULAR A", "target": "Fulano Silva", "weight": 2, "channels": ["SMS"]}]},
     "dispositivos": [{"likely_owners": ["TITULAR A"], "owner_phone_numbers": ["+5571900000000"]}]}
B = {"rede": {"nodes": [{"id": "TITULAR B", "label": "Beltrano (titular)"}],
              "edges": [{"source": "TITULAR B", "target": "(71) 8888-0002", "weight": 12, "messages_count": 2,
                         "calls_count": 10, "channels": ["Chamadas"]},
                        {"source": "TITULAR B", "target": "fulano  silva", "weight": 3, "channels": ["SMS"]}]},
     "dispositivos": [{"likely_owners": ["TITULAR B"], "owner_phone_numbers": ["71 99999-0001"]}]}


class TestMulticasos(unittest.TestCase):
    def test_chave(self):
        k = lambda x: multicasos.chave(x)
        self.assertEqual(k("5571999990001@s.whatsapp.net"), k("71 99999-0001"))
        self.assertEqual(k("+55 71 98888-0002"), k("(71) 8888-0002"))
        self.assertNotEqual(k("+55 71 98888-0002"), k("+55 75 98888-0002"))
        self.assertEqual(k("Fulano@Example.com"), ("email", "fulano@example.com"))
        self.assertEqual(k("Fulano  Silva!"), ("nome", "fulano silva"))
        self.assertEqual(k(""), (None, None))

    def test_chave_formatos_de_telefone(self):
        k = lambda x: multicasos.chave(x)
        self.assertEqual(k("0 41 71 99999-0001"), k("71 99999-0001"))      # 0 + operadora
        self.assertEqual(k("071 99999-0001"), k("71 99999-0001"))          # 0 + DDD
        self.assertEqual(k("+1 555 123 4567"), ("telefone", "+15551234567"))
        self.assertNotEqual(k("+1 555 123 4567"), k("15 5512-34567"))      # estrangeiro ≠ DDD 15
        self.assertEqual(k("0055 71 99999-0001"), k("71 99999-0001"))
        self.assertEqual(k("120363012345678901@g.us"), ("grupo", "120363012345678901"))
        self.assertEqual(k("557199990001-1612345678@g.us")[0], "grupo")

    def test_cruzar(self):
        r = multicasos.cruzar(["/casos/A", "/casos/B"], ler={"/casos/A": A, "/casos/B": B}.get)
        self.assertEqual(r["resumo"]["com_dados"], 2)
        por = {x["chave"]: x for x in r["comuns"]}
        beltrano = por[multicasos.chave("71 99999-0001")[1]]
        self.assertEqual(beltrano["titular_em"], ["B"])  # titular de B é contato em A
        self.assertEqual(beltrano["interacoes"]["A"], 30)
        self.assertEqual(r["comuns"][0]["chave"], beltrano["chave"])  # titular cruzado vem primeiro
        self.assertIn(multicasos.chave("(71) 8888-0002")[1], por)
        self.assertEqual(por["fulano silva"]["forca"], "fraca (só o nome)")
        self.assertEqual(r["resumo"]["titulares_cruzados"], 1)
        ids = {n["id"]: n for n in r["rede"]["nodes"]}
        self.assertEqual(sorted(ids["telefone:7188880002"]["casos"]), ["A", "B"])
        md = multicasos.relatorio_md(r)
        self.assertIn("| 7199990001 | telefone | A, B |", md)

    def test_caso_sem_numeros(self):
        r = multicasos.cruzar(["/casos/A", "/casos/X"], ler={"/casos/A": A}.get)
        self.assertFalse(r["casos"][1]["ok"])
        self.assertEqual(r["comuns"], [])
        with self.assertRaises(ValueError):
            multicasos.cruzar(["/casos/A"], ler=lambda c: A)


if __name__ == "__main__":
    unittest.main()
