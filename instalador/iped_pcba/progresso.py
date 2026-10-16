"""Progresso do processamento do IPED, lido do log da tarefa (saída do console com --nogui).

O IPED escreve a cada segundo uma linha do ProgressConsole, por exemplo
    2026-10-16 10:00:00  [MSG]  [processing.ui.ProgressConsole]  Processando 1234/5678 (21%) 36GB/h Termino em 0h 12m 34s
e, a cada tanto, uma linha por worker com a tarefa e o item em andamento:
    Worker-3 [ParsingTask] [evidencia.E01>>Particao>>Users/x/foto.jpg] [123.456 bytes]
Aceita as mensagens em português, inglês e espanhol. Lê o log aos pedaços, sem reler o começo.
"""

import datetime
import re

PROC = re.compile(r"(?:Processando|Processing|Procesando)\s+(\d+)\s*/\s*(\d+)(?:\s*\((\d+)%\))?(?:\s+(\d+)\s*GB/h)?")
ACHADOS = re.compile(r"(?:Localizados|Found|Encontrado)\s+(\d+)")
TERMINO = re.compile(r"(?:Termino em|Término em|Finish in|Finalizar en)\s+(\d+)h\s+(\d+)m\s+(\d+)s")
INICIO = re.compile(r"(?:Inicializando|Starting|Iniciando)\.\.\.")
WORKER = re.compile(r"(Worker-\d+)\s+\[([^\]]+)\]\s+\[([^\]]*)\](?:\s+\[([\d.,]+) bytes\])?")
DATA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
NIVEL = re.compile(r"\[(ERROR|FATAL|WARN)\]")
MSG = re.compile(r"\[MSG\]\s+\[[^\]]*\]\s+(.*)$")

# nomes das tarefas do IPED (classe) para o painel
TAREFAS = {
    "SkipCommitedTask": "Retomada: pulando itens já processados",
    "HashTask": "Calculando hashes",
    "HashDBLookupTask": "Consultando bases de hashes",
    "LedKFFTask": "Consultando LED/KFF", "KFFTask": "Consultando KFF", "PhotoDNATask": "PhotoDNA",
    "PhotoDNALookup": "Consultando PhotoDNA", "DuplicateTask": "Marcando duplicados",
    "SignatureTask": "Identificando tipos de arquivo", "SetTypeTask": "Classificando tipos",
    "SetCategoryTask": "Classificando categorias", "ParsingTask": "Extraindo conteúdo e metadados (inclui OCR)",
    "ExpandContainerTask": "Expandindo contêineres (ZIP, bancos de dados, apps)",
    "RegexTask": "Buscando padrões (CPF, telefones, e-mails...)", "LanguageDetectTask": "Detectando idioma",
    "NamedEntityTask": "Reconhecendo nomes e entidades", "CarverTask": "Recuperando arquivos apagados (carving)",
    "KnownMetCarveTask": "Carving de arquivos conhecidos", "LedCarveTask": "Carving LED",
    "ImageThumbTask": "Gerando miniaturas de imagens", "VideoThumbTask": "Gerando miniaturas de vídeos",
    "DocThumbTask": "Gerando miniaturas de documentos", "MakePreviewTask": "Gerando visualizações",
    "AudioTranscriptTask": "Transcrevendo áudios", "QRCodeTask": "Lendo QR codes",
    "ImageSimilarityTask": "Calculando semelhança de imagens", "FaceRecognitionTask": "Reconhecendo rostos",
    "NudityDetectTask": "Detectando nudez", "YahooNSFWNudityDetectTask": "Detectando nudez",
    "DIETask": "Detectando nudez (DIE)", "AgeEstimationTask": "Estimando idade",
    "EntropyTask": "Calculando entropia", "ExportFileTask": "Exportando arquivos",
    "IndexTask": "Indexando texto", "ElasticSearchIndexTask": "Indexando no ElasticSearch",
    "GraphTask": "Montando o grafo de vínculos", "MinIOTask": "Enviando ao MinIO",
    "SplitLargeBinaryTask": "Dividindo arquivos grandes", "HTMLReportTask": "Gerando relatório HTML",
    "LocalEvidenceDetectorTask": "Analisando evidências locais",
}


def nome_tarefa(classe):
    if classe in ("no task", ""):
        return "aguardando item"
    return TAREFAS.get(classe, classe)


def _segundos(texto):
    m = DATA.match(texto)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


class Leitor(object):
    """Estado do processamento, atualizado com cada novo pedaço do log."""

    def __init__(self):
        self.pos = 0
        self.resto = ""
        self.fase = "iniciando"
        self.processados = self.total = self.percentual = self.gbh = None
        self.restante_s = None
        self.inicio = self.ultima = None
        self.workers = {}
        self.mensagens = []
        self.erros = 0
        self.avisos = 0
        self.ult_erros = []
        self.serie = []          # (segundos desde o início, percentual)

    def ler(self, caminho):
        with open(caminho, "rb") as f:
            f.seek(self.pos)
            dados = f.read(8 * 1024 * 1024)
        self.pos += len(dados)
        texto = self.resto + dados.decode("utf-8", "replace")
        linhas = texto.split("\n")
        self.resto = linhas.pop()
        for linha in linhas:
            self.linha(linha.rstrip("\r"))
        return self

    def linha(self, l):
        t = _segundos(l)
        if t:
            self.inicio = self.inicio or t
            self.ultima = t
        nv = NIVEL.search(l)
        if nv:
            if nv.group(1) == "WARN":
                self.avisos += 1
            else:
                self.erros += 1
                self.ult_erros = (self.ult_erros + [l[-300:]])[-5:]
        m = PROC.search(l)
        if m:
            self.fase = "processando"
            self.processados, self.total = int(m.group(1)), int(m.group(2))
            if m.group(3) is not None:
                self.percentual = int(m.group(3))
            if m.group(4) is not None:
                self.gbh = int(m.group(4))
            self._termino(l)
            self._ponto(t)
            return
        m = ACHADOS.search(l)
        if m and ("[MSG]" in l or not t):
            self.fase = "descobrindo"
            self.total = int(m.group(1))
            self._termino(l)
            return
        if INICIO.search(l):
            return
        m = WORKER.search(l)
        if m:
            self.workers[m.group(1)] = {"tarefa": m.group(2), "item": m.group(3), "bytes": m.group(4)}
            return
        m = MSG.search(l)
        if m and m.group(1).strip():
            txt = m.group(1).strip()
            low = txt.lower()
            if "commit" in low or "índice" in low or "indice" in low or "index" in low:
                if self.percentual is not None and self.percentual >= 99:
                    self.fase = "finalizando"
            if low.startswith(("finalizado", "finished")) or "processamento finalizado" in low:
                self.fase = "finalizando"
            self.mensagens = (self.mensagens + [txt[:240]])[-8:]
        if l.startswith("[fim: código"):
            cod = re.findall(r"-?\d+", l)
            self.fase = "concluido" if cod and cod[0] == "0" else "erro"

    def _termino(self, l):
        m = TERMINO.search(l)
        if m:
            self.restante_s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))

    def _ponto(self, t):
        if t is None or self.percentual is None or self.inicio is None:
            return
        s = int((t - self.inicio).total_seconds())
        if not self.serie or s - self.serie[-1][0] >= 30 or self.percentual != self.serie[-1][1] and s - self.serie[-1][0] >= 5:
            self.serie.append((s, self.percentual))
            if len(self.serie) > 400:
                self.serie = self.serie[::2]

    def estado(self, rodando=True, codigo=None):
        if not rodando:
            self.fase = "concluido" if codigo == 0 else "erro"
        ativos = {}
        for w in self.workers.values():
            n = nome_tarefa(w["tarefa"])
            a = ativos.setdefault(n, {"tarefa": n, "classe": w["tarefa"], "workers": 0, "itens": []})
            a["workers"] += 1
            if w["item"] and w["item"] != "no item" and len(a["itens"]) < 3:
                a["itens"].append(w["item"][-160:])
        decorrido = int((self.ultima - self.inicio).total_seconds()) if self.inicio and self.ultima else None
        return {"fase": self.fase, "percentual": 100 if self.fase == "concluido" else self.percentual,
                "processados": self.processados, "total": self.total, "gb_por_hora": self.gbh,
                "restante_s": None if self.fase in ("concluido", "erro") else self.restante_s,
                "decorrido_s": decorrido, "atividades": sorted(ativos.values(), key=lambda a: -a["workers"]),
                "mensagens": self.mensagens, "erros": self.erros, "avisos": self.avisos,
                "ultimos_erros": self.ult_erros,
                "serie": self.serie + ([(decorrido, self.percentual)] if decorrido is not None and self.percentual is not None
                                       and (not self.serie or self.serie[-1][0] < decorrido) else [])}
