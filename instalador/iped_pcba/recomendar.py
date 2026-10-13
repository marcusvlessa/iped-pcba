"""Regras que transformam o retrato da máquina num plano de configuração.

Tudo aqui é puro (sem I/O): recebe o dicionário de detectar.detectar() e
devolve um Plano. Cada alteração carrega o motivo, que vai para o log e
para o relatório mostrado ao analista antes de aplicar.
"""

import math

VRAM_MIN_GPU = 6      # GB para Whisper em GPU (float16)
VRAM_LARGE = 10       # GB para large-v3
HEAP_TETO_GB = 30     # acima disso o GC piora
GB_POR_THREAD = 1.5   # RAM mínima por worker antes de limitar numThreads


class Alteracao(object):
    def __init__(self, arquivo, chave, valor, motivo):
        self.arquivo = arquivo      # relativo à raiz do IPED, com "/"
        self.chave = chave
        self.valor = str(valor)
        self.motivo = motivo

    def como_dict(self):
        return {"arquivo": self.arquivo, "chave": self.chave,
                "valor": self.valor, "motivo": self.motivo}


class Plano(object):
    def __init__(self):
        self.alteracoes = []
        self.avisos = []
        self.heap_gb = None
        self.transcricao = ""

    def definir(self, arquivo, chave, valor, motivo):
        self.alteracoes = [a for a in self.alteracoes
                           if not (a.arquivo == arquivo and a.chave == chave)]
        self.alteracoes.append(Alteracao(arquivo, chave, valor, motivo))

    def valor(self, arquivo, chave):
        for a in self.alteracoes:
            if a.arquivo == arquivo and a.chave == chave:
                return a.valor
        return None

    def como_dict(self):
        return {"heap_gb": self.heap_gb, "transcricao": self.transcricao,
                "alteracoes": [a.como_dict() for a in self.alteracoes],
                "avisos": list(self.avisos)}


LOCAL = "LocalConfig.txt"
AUDIO = "conf/AudioTranscriptConfig.txt"
HASH = "conf/HashTaskConfig.txt"

WHISPER = "iped.engine.task.transcript.WhisperTranscriptTask"
VOSK = "iped.engine.task.transcript.VoskTranscriptTask"
REMOTA = "iped.engine.task.transcript.RemoteTranscriptionTask"


def melhor_gpu(maquina):
    gpus = maquina.get("gpus") or []
    return max(gpus, key=lambda g: g.get("vram_gb", 0)) if gpus else None


def calcular_heap(ram_gb):
    """50% da RAM, teto de 30 GB, mínimo de 2 GB."""
    if not ram_gb:
        return None
    return int(max(2, min(math.floor(ram_gb * 0.5), HEAP_TETO_GB)))


def calcular_threads(ram_gb, logicos, heap_gb):
    """'default' quando há memória para todos os núcleos; senão limita."""
    if not logicos or not heap_gb:
        return "default"
    if heap_gb / float(logicos) >= GB_POR_THREAD / 2:
        return "default"
    return str(max(2, int(heap_gb / (GB_POR_THREAD / 2))))


def recomendar(maquina, papel="cliente", pasta_temp=None, tipo_disco_temp="desconhecido",
               servidor_transcricao=None, saida_em_ssd=False):
    """papel: 'cliente' (estação Windows do analista) ou 'servidor' (Linux central).
    servidor_transcricao: 'host:porta' do nó de descoberta da transcrição remota."""
    p = Plano()
    ram = maquina.get("ram_gb") or 0
    logicos = (maquina.get("cpu") or {}).get("logicos") or 0
    iped = maquina.get("iped") or {}

    # ---- LocalConfig.txt
    p.definir(LOCAL, "locale", "pt-BR", "Interface e transcrição em português.")
    if pasta_temp:
        p.definir(LOCAL, "indexTemp", pasta_temp.replace("\\", "/"),
                  "Pasta temporária escolhida na instalação.")
        if tipo_disco_temp == "ssd":
            p.definir(LOCAL, "indexTempOnSSD", "true",
                      "indexTemp está em SSD/NVMe (até 2x mais rápido).")
        else:
            p.definir(LOCAL, "indexTempOnSSD", "false",
                      "indexTemp não está em SSD confirmado; ligar em HDD piora o desempenho.")
            p.avisos.append("A pasta temporária não está num SSD confirmado. "
                            "Se houver SSD/NVMe na máquina, prefira colocá-la lá.")
    else:
        p.avisos.append("Nenhuma pasta temporária informada (--temp). O IPED usará o temp do "
                        "sistema, que costuma ficar no disco do Windows e sob antivírus.")
    p.definir(LOCAL, "outputOnSSD", "true" if saida_em_ssd else "false",
              "Saída do caso em SSD." if saida_em_ssd else "Saída do caso não confirmada em SSD.")

    p.heap_gb = calcular_heap(ram)
    threads = calcular_threads(ram, logicos, p.heap_gb)
    p.definir(LOCAL, "numThreads", threads,
              "Um worker por núcleo lógico." if threads == "default" else
              "RAM curta para {} núcleos; limitado para evitar OutOfMemoryError.".format(logicos))
    if ram and ram < 16:
        p.avisos.append("Máquina com {} GB de RAM: processe uma evidência por vez e evite "
                        "OCR e transcrição local.".format(ram))

    # ---- hashes: sha-256 é exigido para vincular anexos do WhatsApp
    p.definir(HASH, "hashes", "md5; sha-1; sha-256",
              "SHA-256 vincula anexos do WhatsApp e entra na cadeia de custódia (CPP 158-A a F).")

    # ---- transcrição
    gpu = melhor_gpu(maquina)
    vram = gpu.get("vram_gb", 0) if gpu else 0
    tem_whisper = "faster_whisper" in (iped.get("pacotes_python") or [])
    if papel == "servidor" and vram < VRAM_MIN_GPU:
        p.avisos.append("Servidor central sem GPU NVIDIA com {} GB ou mais: a transcrição "
                        "centralizada vai rodar em CPU e não compensa.".format(VRAM_MIN_GPU))
    if papel == "cliente" and servidor_transcricao:
        p.transcricao = "remota"
        p.definir(AUDIO, "implementationClass", REMOTA,
                  "Transcrição enviada ao servidor central (GPU compartilhada).")
        p.definir(AUDIO, "remoteServiceAddress", servidor_transcricao,
                  "Endereço do nó de descoberta no servidor Linux.")
    elif vram >= VRAM_MIN_GPU and tem_whisper:
        _whisper_gpu(p, vram, "Servidor central com GPU: transcreve para todas as estações."
                     if papel == "servidor" else "GPU local com {} GB de VRAM.".format(vram))
    elif logicos >= 8 and ram >= 16 and tem_whisper:
        p.transcricao = "whisper-cpu"
        p.definir(AUDIO, "implementationClass", WHISPER, "Sem GPU apta; Whisper em CPU.")
        p.definir(AUDIO, "device", "cpu", "Sem GPU NVIDIA com 6 GB ou mais.")
        p.definir(AUDIO, "precision", "int8", "int8 é o mais rápido em CPU.")
        p.definir(AUDIO, "whisperModel", "small",
                  "Modelo pequeno para caber no tempo em CPU; qualidade abaixo do medium.")
        p.avisos.append("Transcrição em CPU é lenta para o volume do Guardião. "
                        "Prefira apontar para o servidor central (--servidor-transcricao).")
    else:
        p.transcricao = "vosk"
        p.definir(AUDIO, "implementationClass", VOSK,
                  "Vosk embarcado no IPED (rápido, qualidade baixa).")
        if vram >= VRAM_MIN_GPU or (logicos >= 8 and ram >= 16):
            p.avisos.append("A máquina comporta Whisper ({}), mas o faster-whisper não está no "
                            "Python do IPED. Instale (scripts/whisper_gpu.ps1 ou pip install "
                            "faster-whisper) e rode o instalador de novo.".format(
                                "GPU" if vram >= VRAM_MIN_GPU else "CPU"))
        else:
            p.avisos.append("Transcrição local ficará com qualidade baixa (Vosk). "
                            "Use o servidor central sempre que possível.")
    p.definir(AUDIO, "language", "auto", "Segue o locale pt-BR.")

    if p.transcricao == "whisper-gpu":
        p.avisos.append("Whisper em GPU precisa de CUDA 12 e das DLLs cuBLAS/cuDNN no Python "
                        "do IPED. Rode scripts/whisper_gpu.ps1 (Windows) ou o passo do README (Linux).")

    if iped.get("versao") and not iped["versao"].startswith("4.3"):
        p.avisos.append("IPED {} detectado. O projeto mira a 4.3.1; atualize antes de usar em "
                        "caso real.".format(iped["versao"]))
    if not iped.get("encontrado"):
        p.avisos.append("Pasta do IPED não reconhecida (IPEDConfig.txt ausente).")
    return p


def _whisper_gpu(p, vram, motivo):
    p.transcricao = "whisper-gpu"
    p.definir(AUDIO, "implementationClass", WHISPER, motivo)
    p.definir(AUDIO, "device", "gpu", "GPU NVIDIA disponível.")
    p.definir(AUDIO, "precision", "float16", "Recomendado para GPU.")
    if vram >= VRAM_LARGE:
        p.definir(AUDIO, "whisperModel", "large-v3", "{} GB de VRAM comportam o large-v3.".format(vram))
    else:
        p.definir(AUDIO, "whisperModel", "medium", "{} GB de VRAM: medium.".format(vram))
