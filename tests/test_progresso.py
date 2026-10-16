import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "instalador"))
from iped_pcba import progresso  # noqa: E402

# Saída imitando o console do IPED 4.3 com --nogui (ProgressConsole); caminhos fictícios.
LOG = """$ java -jar iped.jar -d celular.ufdr -o caso --nogui

2026-10-16 10:00:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tInicializando...
2026-10-16 10:00:05\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tLocalizados 5000 arquivos
2026-10-16 10:01:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tProcessando 1200/9000 (12%) 35GB/h Termino em 0h 20m 5s
2026-10-16 10:01:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tWorker-0 [ParsingTask] [celular.ufdr>>WhatsApp/Media/foto.jpg] [1.234 bytes]
2026-10-16 10:01:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tWorker-1 [AudioTranscriptTask] [celular.ufdr>>PTT-1.opus] [99 bytes]
2026-10-16 10:01:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tWorker-2 [ParsingTask] [celular.ufdr>>doc.pdf] [5 bytes]
2026-10-16 10:01:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tWorker-3 [no task] [no item]
2026-10-16 10:01:01\t[ERROR]\t[engine.task.ParsingTask]\t\t\tFalha ao ler item corrompido
2026-10-16 10:01:02\t[WARN]\t[engine.core.Worker]\t\t\tMemória baixa
2026-10-16 10:02:00\t[MSG]\t[processing.ui.ProgressConsole]\t\t\tProcessando 4500/9000 (50%) 40GB/h Termino em 0h 10m 0s
"""


class TestProgresso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "t.log")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _gravar(self, texto, modo="w"):
        with open(self.log, modo, encoding="utf-8") as f:
            f.write(texto)

    def test_le_o_console_do_iped(self):
        meio = LOG.index("2026-10-16 10:01:00")
        self._gravar(LOG[:meio + 30])  # linha cortada no meio: espera o resto
        lt = progresso.Leitor().ler(self.log)
        self.assertEqual(lt.estado()["fase"], "descobrindo")
        self.assertEqual(lt.estado()["total"], 5000)
        self._gravar(LOG[meio + 30:], "a")
        e = lt.ler(self.log).estado()
        self.assertEqual((e["fase"], e["percentual"], e["processados"], e["total"]), ("processando", 50, 4500, 9000))
        self.assertEqual(e["restante_s"], 600)
        self.assertEqual(e["gb_por_hora"], 40)
        self.assertEqual(e["decorrido_s"], 120)
        self.assertEqual((e["erros"], e["avisos"]), (1, 1))
        at = {a["tarefa"]: a["workers"] for a in e["atividades"]}
        self.assertEqual(at["Extraindo conteúdo e metadados (inclui OCR)"], 2)
        self.assertEqual(at["Transcrevendo áudios"], 1)
        self.assertEqual(e["serie"][-1], (120, 50))

    def test_fim_e_ingles(self):
        self._gravar("2026-10-16 10:00:00\t[MSG]\t[x.ProgressConsole]\t\t\tProcessing 10/10 (100%) 3GB/h Finish in 0h 0m 0s\n"
                     "\n[fim: código 0]\n")
        e = progresso.Leitor().ler(self.log).estado(rodando=False, codigo=0)
        self.assertEqual((e["fase"], e["percentual"], e["restante_s"]), ("concluido", 100, None))
        e = progresso.Leitor().ler(self.log).estado(rodando=False, codigo=1)
        self.assertEqual(e["fase"], "erro")


if __name__ == "__main__":
    unittest.main()
