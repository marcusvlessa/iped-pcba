import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))

from iped_pcba import cli, configurar, detectar, localizar, perfis, recomendar  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "iped-4.3.1")


def maquina(ram=32, logicos=16, gpus=None, versao="4.3.1", pacotes=("faster_whisper",)):
    return {"so": "windows", "hostname": "teste", "ram_gb": ram,
            "cpu": {"nome": "CPU", "fisicos": logicos // 2, "logicos": logicos},
            "discos": [], "gpus": gpus or [],
            "iped": {"encontrado": True, "versao": versao, "python_embarcado": True,
                     "pacotes_python": pacotes}}


class TestParsers(unittest.TestCase):
    def test_nvidia_smi(self):
        gpus = detectar.parse_nvidia_smi(
            "NVIDIA GeForce RTX 3060, 12288, 552.22\n",
            "| NVIDIA-SMI 552.22   Driver Version: 552.22   CUDA Version: 12.4 |")
        self.assertEqual(gpus, [{"nome": "NVIDIA GeForce RTX 3060", "vram_gb": 12.0,
                                 "driver": "552.22", "cuda": "12.4"}])

    def test_nvidia_smi_vazio(self):
        self.assertEqual(detectar.parse_nvidia_smi(""), [])

    def test_meminfo(self):
        self.assertEqual(detectar.parse_meminfo("MemTotal:       32768000 kB\n"), 31.2)

    def test_cpuinfo(self):
        txt = ("model name\t: Intel X\nphysical id\t: 0\ncore id\t: 0\n\n"
               "model name\t: Intel X\nphysical id\t: 0\ncore id\t: 0\n\n"
               "model name\t: Intel X\nphysical id\t: 0\ncore id\t: 1\n\n")
        self.assertEqual(detectar.parse_cpuinfo(txt), ("Intel X", 2))

    def test_lsblk(self):
        j = json.dumps({"blockdevices": [
            {"name": "nvme0n1", "rota": False, "size": 1024 ** 4, "model": "Samsung 980", "type": "disk"},
            {"name": "sda", "rota": "1", "size": 2 * 1024 ** 4, "model": "WD", "type": "disk"},
            {"name": "zram0", "rota": False, "size": 1, "model": None, "type": "disk"},
            {"name": "loop0", "rota": False, "size": 1, "model": None, "type": "loop"}]})
        d = detectar.parse_lsblk(j)
        self.assertEqual([(x["dispositivo"], x["tipo"], x["tamanho_gb"]) for x in d],
                         [("nvme0n1", "ssd", 1024), ("sda", "hdd", 2048)])

    def test_windows_json(self):
        j = json.dumps({"cpuNome": "Ryzen", "cpuFisicos": 8, "cpuLogicos": 16,
                        "ramBytes": 64 * 1024 ** 3,
                        "discos": {"FriendlyName": "NVMe", "MediaType": "SSD",
                                   "Size": 512 * 1024 ** 3, "Letras": "CD"}})
        r = detectar.parse_windows_json(j)
        self.assertEqual(r["ram_gb"], 64.0)
        self.assertEqual(r["discos"][0]["tipo"], "ssd")
        self.assertEqual(r["discos"][0]["letras"], "CD")

    def test_detectar_iped(self):
        info = detectar.detectar_iped(FIXTURE)
        self.assertTrue(info["encontrado"])
        self.assertEqual(info["versao"], "4.3.1")
        self.assertEqual(info["perfis"], ["forensic", "triage"])


class TestVolumes(unittest.TestCase):
    def test_windows_volumes(self):
        j = json.dumps({"cpuNome": "x", "cpuFisicos": 4, "cpuLogicos": 8, "ramBytes": 1,
                        "sistema": "C",
                        "discos": [{"FriendlyName": "A", "MediaType": "SSD", "Size": 1, "Letras": "C"},
                                   {"FriendlyName": "B", "MediaType": "HDD", "Size": 1, "Letras": "D"}],
                        "volumes": [{"Letra": "C", "Livre": 200 * 1024 ** 3, "Total": 500 * 1024 ** 3},
                                    {"Letra": "D", "Livre": 900 * 1024 ** 3, "Total": 1000 * 1024 ** 3}]})
        v = detectar.parse_windows_json(j)["volumes"]
        self.assertEqual([(x["raiz"], x["tipo"], x["sistema"], x["livre_gb"]) for x in v],
                         [("C:/", "ssd", True, 200), ("D:/", "hdd", False, 900)])

    def test_df(self):
        t = ("Filesystem 1B-blocks\n/dev/nvme0n1p2 / 100000000000 500000000000\n"
             "tmpfs /run 1 1\n/dev/sdb1 /dados 2000000000000 4000000000000\n"
             "/dev/nvme0n1p1 /boot/efi 1 1\n")
        self.assertEqual([x["raiz"] for x in detectar.parse_df(t)], ["/", "/dados"])


class TestEscolherTemp(unittest.TestCase):
    def m(self, vols, so="windows"):
        return {"so": so, "volumes": vols}

    def test_prefere_ssd_fora_do_sistema(self):
        c, tipo, _ = recomendar.escolher_temp(self.m([
            {"raiz": "C:/", "livre_gb": 300, "tipo": "ssd", "sistema": True},
            {"raiz": "D:/", "livre_gb": 900, "tipo": "hdd", "sistema": False},
            {"raiz": "E:/", "livre_gb": 120, "tipo": "ssd", "sistema": False}]))
        self.assertEqual((c, tipo), ("E:/IPEDTemp", "ssd"))

    def test_ssd_do_sistema_antes_de_hdd(self):
        c, tipo, _ = recomendar.escolher_temp(self.m([
            {"raiz": "C:/", "livre_gb": 300, "tipo": "ssd", "sistema": True},
            {"raiz": "D:/", "livre_gb": 900, "tipo": "hdd", "sistema": False}]))
        self.assertEqual(c, "C:/IPEDTemp")

    def test_sem_ssd_usa_maior(self):
        c, tipo, _ = recomendar.escolher_temp(self.m([
            {"raiz": "/", "livre_gb": 60, "tipo": "hdd", "sistema": True},
            {"raiz": "/dados", "livre_gb": 900, "tipo": "hdd", "sistema": False}], so="linux"))
        self.assertEqual((c, tipo), ("/dados/ipedtemp", "hdd"))

    def test_sem_espaco(self):
        c, _, _ = recomendar.escolher_temp(self.m([{"raiz": "C:/", "livre_gb": 10, "tipo": "ssd"}]))
        self.assertIsNone(c)


class TestLocalizar(unittest.TestCase):
    def test_acha_instalacoes_e_ordena_por_versao(self):
        tmp = tempfile.mkdtemp()
        try:
            for rel, ver in (("Tools/iped-4.3.1/iped-4.3.1", "4.3.1"), ("IPED/iped-4.2.2", "4.2.2"),
                             ("x/y/z/w/iped-4.4.0", "4.4.0")):
                pasta = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.join(pasta, "lib"))
                for f in ("IPEDConfig.txt", "iped.jar", os.path.join("lib", "iped-engine-%s.jar" % ver)):
                    open(os.path.join(pasta, f), "w").close()
            # só configuração, sem iped.jar: não é instalação
            os.makedirs(os.path.join(tmp, "Downloads"))
            open(os.path.join(tmp, "Downloads", "IPEDConfig.txt"), "w").close()
            # um IPED registrado em ~/.iped fora das bases não entra na busca
            fora = os.path.join(tempfile.mkdtemp(), "iped-4.3.1")
            os.makedirs(os.path.join(fora, "lib"))
            for f in ("IPEDConfig.txt", "iped.jar", os.path.join("lib", "iped-engine-4.3.1.jar")):
                open(os.path.join(fora, f), "w").close()
            home = tempfile.mkdtemp()
            os.makedirs(os.path.join(home, ".iped"))
            with open(os.path.join(home, ".iped", "ipedRoot.txt"), "w") as f:
                f.write(fora)
            with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
                os.environ.pop("IPED_ROOT", None)
                achados = localizar.localizar_iped(bases=[tmp])
            shutil.rmtree(home)
            shutil.rmtree(os.path.dirname(fora))
            self.assertEqual([a["versao"] for a in achados], ["4.3.1", "4.2.2"])  # 4.4.0 fundo demais

            # duas 4.3.1: vence a registrada pelo IPED como em uso
            outra = os.path.join(tmp, "A", "iped-4.3.1")
            os.makedirs(os.path.join(outra, "lib"))
            for f in ("IPEDConfig.txt", "iped.jar", os.path.join("lib", "iped-engine-4.3.1.jar")):
                open(os.path.join(outra, f), "w").close()
            antigo = os.environ.get("IPED_ROOT")
            os.environ["IPED_ROOT"] = outra
            try:
                achados = localizar.localizar_iped(bases=[tmp])
            finally:
                if antigo is None:
                    del os.environ["IPED_ROOT"]
                else:
                    os.environ["IPED_ROOT"] = antigo
            self.assertEqual(achados[0]["raiz"], os.path.abspath(outra))
            self.assertTrue(achados[0]["em_uso"])
        finally:
            shutil.rmtree(tmp)


class TestRecomendar(unittest.TestCase):
    def test_heap(self):
        self.assertEqual(recomendar.calcular_heap(16), 8)
        self.assertEqual(recomendar.calcular_heap(128), 30)
        self.assertEqual(recomendar.calcular_heap(3), 2)

    def test_threads_limitadas_com_pouca_ram(self):
        self.assertEqual(recomendar.calcular_threads(32, 16, 16), "default")
        self.assertEqual(recomendar.calcular_threads(16, 32, 8), "10")

    def test_gpu_boa_usa_whisper_gpu(self):
        p = recomendar.recomendar(maquina(gpus=[{"nome": "RTX", "vram_gb": 12, "driver": "", "cuda": ""}]))
        self.assertEqual(p.transcricao, "whisper-gpu")
        self.assertEqual(p.valor(recomendar.AUDIO, "device"), "gpu")
        self.assertEqual(p.valor(recomendar.AUDIO, "whisperModel"), "large-v3")

    def test_cliente_com_servidor_central(self):
        p = recomendar.recomendar(maquina(), servidor_transcricao="10.0.0.5:11111")
        self.assertEqual(p.transcricao, "remota")
        self.assertEqual(p.valor(recomendar.AUDIO, "remoteServiceAddress"), "10.0.0.5:11111")

    def test_sem_faster_whisper_cai_para_vosk(self):
        p = recomendar.recomendar(maquina(ram=40, logicos=12, pacotes=()))
        self.assertEqual(p.transcricao, "vosk")
        self.assertTrue(any("faster-whisper" in a for a in p.avisos))

    def test_linux_sem_tsk_jar_avisa(self):
        m = maquina()
        self.assertFalse(any("tskJarPath" in a for a in recomendar.recomendar(m).avisos))
        m["so"] = "linux"
        self.assertTrue(any("tskJarPath" in a for a in recomendar.recomendar(m).avisos))
        m["iped"]["tsk_jar"] = "/usr/local/share/java/sleuthkit-4.12.0.jar"
        self.assertFalse(any("tskJarPath" in a for a in recomendar.recomendar(m).avisos))

    def test_cpu_forte_com_whisper(self):
        p = recomendar.recomendar(maquina(ram=40, logicos=12))
        self.assertEqual(p.transcricao, "whisper-cpu")

    def test_servidor_sem_gpu_avisa(self):
        p = recomendar.recomendar(maquina(), papel="servidor")
        self.assertTrue(any("Servidor central sem GPU" in a for a in p.avisos))

    def test_maquina_modesta_usa_vosk(self):
        p = recomendar.recomendar(maquina(ram=8, logicos=4))
        self.assertEqual(p.transcricao, "vosk")
        self.assertTrue(any("8 GB" in a for a in p.avisos))

    def test_temp_em_ssd(self):
        p = recomendar.recomendar(maquina(), pasta_temp="D:\\IPEDTemp", tipo_disco_temp="ssd")
        self.assertEqual(p.valor(recomendar.LOCAL, "indexTemp"), "D:/IPEDTemp")
        self.assertEqual(p.valor(recomendar.LOCAL, "indexTempOnSSD"), "true")

    def test_aviso_versao_antiga(self):
        p = recomendar.recomendar(maquina(versao="4.2.2"))
        self.assertTrue(any("4.2.2" in a for a in p.avisos))

    def test_sha256_sempre(self):
        p = recomendar.recomendar(maquina())
        self.assertIn("sha-256", p.valor(recomendar.HASH, "hashes"))


class TestDefinirChave(unittest.TestCase):
    def test_substitui_ativa(self):
        self.assertEqual(configurar.definir_chave("a = 1\nb = 2\n", "b", "3"), "a = 1\nb = 3\n")

    def test_ativa_comentada(self):
        t = "#x = 1\n# y = 2\n"
        self.assertEqual(configurar.definir_chave(t, "y", "9"), "#x = 1\ny = 9\n")

    def test_prefere_ativa_a_comentada(self):
        t = "#impl = A\nimpl = B\n#impl = C\n"
        self.assertEqual(configurar.definir_chave(t, "impl", "C"), "#impl = A\nimpl = C\n#impl = C\n")

    def test_acrescenta_no_fim(self):
        self.assertEqual(configurar.definir_chave("a = 1\n", "z", "0"), "a = 1\nz = 0\n")

    def test_preserva_crlf_e_bom(self):
        t = u"\ufeffa = 1\r\nb = 2\r\n"
        self.assertEqual(configurar.definir_chave(t, "a", "5"), u"\ufeffa = 5\r\nb = 2\r\n")

    def test_nao_confunde_prefixo(self):
        t = "enableOCR = false\nenableOCRx = false\n"
        self.assertEqual(configurar.definir_chave(t, "enableOCRx", "true"),
                         "enableOCR = false\nenableOCRx = true\n")


class TestAplicarNaInstalacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.raiz = os.path.join(self.tmp, "iped")
        shutil.copytree(FIXTURE, self.raiz)
        self.original = {}
        for base, _, arqs in os.walk(self.raiz):
            for a in arqs:
                c = os.path.join(base, a)
                with open(c, "rb") as f:
                    self.original[os.path.relpath(c, self.raiz)] = f.read()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _chaves(self, rel):
        return configurar.ler_chaves(configurar.ler_texto(os.path.join(self.raiz, rel)))

    def _rodar(self, *extra):
        saida = io.StringIO()
        antigo = sys.stdout
        sys.stdout = saida
        try:
            codigo = cli.main(["aplicar", "--iped", self.raiz, "--json"] + list(extra))
        finally:
            sys.stdout = antigo
        self.assertEqual(codigo, 0)
        return json.loads(saida.getvalue())

    def test_simular_no_console(self):
        # o instalar.ps1 -Simular / -Aplicar usa a saída em texto, não o JSON
        saida = io.StringIO()
        with mock.patch("sys.stdout", saida):
            codigo = cli.main(["aplicar", "--iped", self.raiz, "--simular"])
        self.assertEqual(codigo, 0)
        self.assertIn("SIMULAÇÃO: nada foi gravado.", saida.getvalue())
        self.assertIn("  perfil pcba-celular", saida.getvalue())

    def test_simular_nao_grava(self):
        r = self._rodar("--simular")
        self.assertTrue(r["mudancas"])
        self.assertIsNone(r["backup"])
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "pcba")))
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "profiles", "pcba-celular")))

    def test_aplicar_e_reverter(self):
        r = self._rodar("--temp", os.path.join(self.tmp, "temp"),
                        "--servidor-transcricao", "10.0.0.5:11111")
        self.assertEqual(self._chaves("LocalConfig.txt")["locale"], "pt-BR")
        audio = self._chaves("conf/AudioTranscriptConfig.txt")
        self.assertEqual(audio["implementationClass"], recomendar.REMOTA)
        self.assertEqual(audio["remoteServiceAddress"], "10.0.0.5:11111")
        self.assertEqual(self._chaves("conf/HashTaskConfig.txt")["hashes"], "md5; sha-1; sha-256")

        # perfis: cópia completa da base + chaves PCBA
        cel = self._chaves("profiles/pcba-celular/IPEDConfig.txt")
        self.assertEqual(cel["enableAudioTranscription"], "true")
        self.assertEqual(cel["enableHash"], "true")
        comp = self._chaves("profiles/pcba-computador/IPEDConfig.txt")
        self.assertEqual(comp["enableCarving"], "true")  # herdado do forensic
        self.assertTrue(os.path.isfile(os.path.join(
            self.raiz, "profiles", "pcba-computador", "conf", "CarverConfig.xml")))
        tri = self._chaves("profiles/pcba-triagem/IPEDConfig.txt")
        self.assertEqual(tri["enableHash"], "false")  # herdado do triage

        # BOM do original preservado
        with open(os.path.join(self.raiz, "LocalConfig.txt"), "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))

        maq = json.loads(configurar.ler_texto(os.path.join(self.raiz, "pcba", "maquina.json")))
        self.assertIn("plano", maq)
        self.assertTrue(r["lancadores"])

        # segunda execução não deve mudar nada nos arquivos de configuração
        r2 = self._rodar("--temp", os.path.join(self.tmp, "temp"),
                         "--servidor-transcricao", "10.0.0.5:11111")
        self.assertEqual(r2["mudancas"], [])

        # reverter as duas execuções volta tudo ao original
        configurar.reverter(self.raiz)
        configurar.reverter(self.raiz, configurar.listar_backups(self.raiz)[0])
        for rel, conteudo in self.original.items():
            with open(os.path.join(self.raiz, rel), "rb") as f:
                self.assertEqual(f.read(), conteudo, rel)
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "profiles", "pcba-celular")))
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "pcba", "maquina.json")))

    def test_pasta_que_nao_e_iped(self):
        vazio = os.path.join(self.tmp, "vazio")
        os.makedirs(vazio)
        antigo = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(cli.main(["aplicar", "--iped", vazio]), 1)
        finally:
            sys.stderr = antigo


class TestPerfis(unittest.TestCase):
    def test_todos_os_perfis_tem_descricao(self):
        for nome, spec in perfis.PERFIS.items():
            self.assertTrue(nome.startswith("pcba-"))
            self.assertTrue(spec["descricao"])

    def test_ocr_qrcode_e_semelhantes_nos_perfis_de_analise(self):
        for nome in ("pcba-celular", "pcba-computador", "pcba-telematica"):
            for chave in ("enableOCR", "enableQRCode", "enableImageSimilarity"):
                self.assertEqual(perfis.PERFIS[nome]["ipedconfig"].get(chave), "true", (nome, chave))

    def test_perfil_antigo_e_regerado(self):
        tmp = tempfile.mkdtemp()
        try:
            raiz = os.path.join(tmp, "iped")
            shutil.copytree(FIXTURE, raiz)
            perfis.criar_perfis(raiz, configurar.Backup(raiz))
            self.assertIsNone(perfis.atualizar_se_preciso(raiz, "pcba-celular"))
            arq = os.path.join(raiz, "profiles", "pcba-celular", "IPEDConfig.txt")
            texto = configurar.definir_chave(configurar.ler_texto(arq), "enableOCR", "false")
            configurar.gravar_texto(arq, texto)  # como ficou instalado pela versão anterior
            self.assertIn("atualizado", perfis.atualizar_se_preciso(raiz, "pcba-celular"))
            self.assertEqual(configurar.ler_chaves(configurar.ler_texto(arq))["enableOCR"], "true")
            self.assertIsNone(perfis.atualizar_se_preciso(raiz, "forensic"))
            self.assertIsNone(perfis.atualizar_se_preciso(raiz, ""))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.name == "nt", "o instalar.ps1 só roda no Windows")
class TestInstalarPs1(unittest.TestCase):
    """O instalar.ps1 só acha um Python e passa a palavra ao pacote (mesma lógica do painel)."""
    PS1 = os.path.join(os.path.dirname(__file__), "..", "scripts", "instalar.ps1")

    def test_sem_erro_de_sintaxe(self):
        cmd = ("$e=$null; [System.Management.Automation.Language.Parser]::ParseFile('{}', [ref]$null, [ref]$e) "
               "| Out-Null; $e | ForEach-Object {{ $_.ToString() }}; exit $e.Count").format(os.path.abspath(self.PS1))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_simular_pelo_pacote(self):
        tmp = tempfile.mkdtemp()
        try:
            raiz = os.path.join(tmp, "iped")
            shutil.copytree(FIXTURE, raiz)  # sem python\python.exe: usa o Python da máquina
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                os.path.abspath(self.PS1), "-IpedRoot", raiz, "-Simular", "-Json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('"mudancas"', r.stdout)
            self.assertFalse(os.path.exists(os.path.join(raiz, "pcba")))  # simulação não grava
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
