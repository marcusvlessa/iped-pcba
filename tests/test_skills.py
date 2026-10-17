import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import agentes, skills  # noqa: E402

ESPERADAS = {"analise-financeira", "analise-imagens", "analise-audio", "analise-geolocalizacao",
             "analise-midias-x-logs", "analise-forense-completa"}


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.zips = skills.ZIPS
        skills.ZIPS = os.path.join(self.home, "zips")

    def tearDown(self):
        skills.ZIPS = self.zips
        shutil.rmtree(self.home)

    def test_formato_das_skills(self):
        sk = {s["id"]: s for s in skills.listar()}
        self.assertEqual(set(sk), ESPERADAS)
        for s in sk.values():
            self.assertRegex(s["id"], r"^[a-z0-9-]{1,64}$")
            self.assertTrue(0 < len(s["descricao"]) <= 1024)
            self.assertNotIn("<", s["descricao"])
            self.assertTrue(s["ferramentas"])
            self.assertIn("iped-pcba", s["corpo"])
        self.assertEqual(sk["analise-forense-completa"]["ferramentas"], "todas")
        self.assertIn("case_context_files", sk["analise-financeira"]["ferramentas"])

    def test_viram_agentes_da_ia_local(self):
        ids = [a["id"] for a in agentes.para_painel()]
        self.assertIn("triagem", ids)
        self.assertIn("skill:analise-financeira", ids)
        a = agentes.por_id("skill:analise-forense-completa")
        self.assertIn("SIMBA", agentes.sistema(agentes.por_id("skill:analise-financeira")))
        self.assertEqual(a["passos"], 40)

    def test_instala_com_backup(self):
        os.makedirs(os.path.join(self.home, ".claude"))
        feito = skills.instalar(home=self.home)
        destinos = {f["destino"] for f in feito}
        self.assertEqual(destinos, {"claude-code", "zip"})  # Hermes não está nesta máquina
        alvo = os.path.join(self.home, ".claude", "skills", "analise-audio", "SKILL.md")
        self.assertTrue(os.path.isfile(alvo))
        with zipfile.ZipFile(os.path.join(skills.ZIPS, "analise-audio.zip")) as z:
            self.assertEqual(z.namelist(), ["analise-audio/SKILL.md"])
        sit = {d["id"]: d for d in skills.situacao(home=self.home)["destinos"]}
        self.assertTrue(all(i["estado"] == "instalada" for i in sit["claude-code"]["itens"]))
        with open(alvo, "a", encoding="utf-8") as f:
            f.write("mudança local\n")
        self.assertEqual({i["skill"]: i["estado"] for i in skills.situacao(home=self.home)["destinos"][0]["itens"]}
                         ["analise-audio"], "desatualizada")
        feito = skills.instalar(["claude-code"], home=self.home)
        acoes = {f["skill"]: f["acao"] for f in feito}
        self.assertTrue(acoes["analise-audio"].startswith("atualizada"))
        self.assertEqual(acoes["analise-imagens"], "já estava")
        bk = os.path.join(self.home, ".iped-pcba", "backup-skills")
        achados = [os.path.join(r, a) for r, _, fs in os.walk(bk) for a in fs]
        self.assertEqual(len(achados), 1)

    def test_envio_ao_claude_desktop(self):
        skills.instalar(["zip"], home=self.home)
        zips = lambda: {i["skill"]: i["estado"] for i in
                        {d["id"]: d for d in skills.situacao(home=self.home)["destinos"]}["zip"]["itens"]}
        self.assertEqual(zips()["analise-audio"], "gerado")
        skills.marcar_enviada("analise-audio", home=self.home)
        self.assertEqual(zips()["analise-audio"], "enviada")
        with mock.patch.object(skills, "_hash", lambda s: "outra versão"):
            self.assertEqual(zips()["analise-audio"], "reenviar")  # a skill mudou depois do envio
        skills.marcar_enviada("analise-audio", False, home=self.home)
        self.assertEqual(zips()["analise-audio"], "gerado")
        with self.assertRaises(ValueError):
            skills.marcar_enviada("nao-existe", home=self.home)
        self.assertEqual(skills.texto_feito({"destino": "claude-code", "skill": "analise-audio", "acao": "já estava"}),
                         "Claude Code: Análise de áudios já estava atualizada")


if __name__ == "__main__":
    unittest.main()
