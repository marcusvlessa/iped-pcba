"""Perfis de processamento da PCBA.

O IPED carrega primeiro a configuração da raiz e depois a do perfil
(-profile <nome>): um IPEDConfig.txt no perfil substitui o da raiz e cada
arquivo em profiles/<nome>/conf/ substitui o arquivo de mesmo nome em conf/.
Por isso cada perfil aqui é gerado como cópia completa do perfil-base com as
chaves da PCBA aplicadas por cima.
"""

import os
import shutil

from .configurar import Backup, definir_chave, gravar_texto, ler_chaves, ler_texto

# Cada perfil: base do IPED, chaves do IPEDConfig.txt e chaves de arquivos em conf/.
PERFIS = {
    "pcba-celular": {
        "descricao": "Extrações de celular (UFDR, Cellebrite, Oxygen, backups). "
                     "Transcreve áudios de WhatsApp, gera grafo de contatos, lê prints (OCR) e QR codes.",
        "base": None,
        "ipedconfig": {
            "enableAudioTranscription": "true",
            "enableGraphGeneration": "true",
            "enableQRCode": "true",
            "enableImageSimilarity": "true",
            "enableHTMLReport": "true",
            "enableOCR": "true",
            "enableCarving": "false",
        },
        "conf": {},
    },
    "pcba-computador": {
        "descricao": "Imagens de disco de computador. Recupera apagados (carving), "
                     "transcreve áudios, lê imagens (OCR) e QR codes.",
        "base": "forensic",
        "ipedconfig": {
            "enableAudioTranscription": "true",
            "enableGraphGeneration": "true",
            "enableHTMLReport": "true",
            "enableOCR": "true",
            "enableQRCode": "true",
            "enableImageSimilarity": "true",
        },
        "conf": {},
    },
    "pcba-telematica": {
        "descricao": "Retornos de provedores (Google, Meta/WhatsApp, Apple, operadoras). "
                     "Expande os pacotes, indexa conteúdo e regex, lê imagens (OCR) e QR codes; "
                     "sem carving nem thumbs de vídeo.",
        "base": None,
        "ipedconfig": {
            "expandContainers": "true",
            "indexFileContents": "true",
            "enableRegexSearch": "true",
            "enableGraphGeneration": "true",
            "enableLanguageDetect": "false",
            "enableAudioTranscription": "true",
            "enableCarving": "false",
            "enableVideoThumbs": "false",
            "enableImageSimilarity": "true",
            "enableOCR": "true",
            "enableQRCode": "true",
            "enableHTMLReport": "true",
        },
        "conf": {},
    },
    "pcba-triagem": {
        "descricao": "Triagem rápida em local de busca: lista e indexa documentos de usuário, "
                     "sem hash completo, sem transcrição.",
        "base": "triage",
        "ipedconfig": {
            "enableAudioTranscription": "false",
        },
        "conf": {},
    },
}


# Explicação de cada perfil para o painel (passo 2). "liga"/"desliga" resumem as chaves acima.
AJUDA = {
    "pcba-celular": {
        "titulo": "Celular",
        "quando": "Extração de celular: UFDR do Cellebrite, Oxygen, XRY, backup de iPhone ou Android.",
        "liga": ["Transcrição de áudios (WhatsApp, Telegram)", "Grafo de contatos e comunicações",
                 "Leitura de QR Code", "Busca de imagens semelhantes", "OCR: texto de prints, fotos de "
                 "documentos e PDFs escaneados", "Relatório HTML"],
        "desliga": ["Carving (a extração já vem organizada)"],
        "tempo": "Médio a lento. Transcrição e OCR são o que mais pesa; sem GPU, conte várias horas "
                 "para muitos áudios e imagens.",
    },
    "pcba-computador": {
        "titulo": "Computador",
        "quando": "Imagem de disco (E01, DD, AD1) ou pendrive/HD de computador.",
        "liga": ["Tudo do perfil forense do IPED", "Recuperação de apagados (carving)",
                 "Transcrição de áudios", "Grafo de comunicações", "OCR de imagens e PDFs escaneados",
                 "Leitura de QR Code", "Busca de imagens semelhantes", "Relatório HTML"],
        "desliga": [],
        "tempo": "Lento. Carving, hashes e OCR leem o disco inteiro; use SSD como pasta temporária.",
    },
    "pcba-telematica": {
        "titulo": "Retorno de provedor",
        "quando": "Pacotes devolvidos por Google, Meta/WhatsApp, Apple, Microsoft e operadoras após quebra de sigilo.",
        "liga": ["Abre os pacotes (ZIP, MBOX, HTML, JSON)", "Indexa o conteúdo e expressões regulares "
                 "(telefones, e-mails, CPFs, chaves PIX)", "Grafo de comunicações", "Transcrição de áudios",
                 "OCR das imagens e PDFs do retorno", "Leitura de QR Code", "Busca de imagens semelhantes",
                 "Relatório HTML"],
        "desliga": ["Carving", "Miniaturas de vídeo", "Detecção de idioma"],
        "tempo": "Médio, conforme o volume do retorno; o OCR pesa quando há muitas imagens.",
    },
    "pcba-triagem": {
        "titulo": "Triagem rápida",
        "quando": "Local de busca ou triagem antes de decidir o que apreender e processar por completo.",
        "liga": ["Lista e indexa documentos de usuário (perfil triage do IPED)"],
        "desliga": ["Hash completo", "Transcrição", "Análises demoradas"],
        "tempo": "Rápido. Não substitui o processamento completo.",
    },
}

# Perfis que já vêm com o IPED 4.x, para quem quiser usá-los direto.
AJUDA_IPED = {
    "forensic": "Perfil pericial do IPED: hashes, assinatura de arquivos, expansão de contêineres e recuperação "
                "de apagados.",
    "pedo": "Foco em exploração sexual infantil: detecção de nudez, bases de hashes e carving de imagens e vídeos.",
    "fastmode": "Pré-visualização muito rápida: lista o sistema de arquivos com pouco processamento de conteúdo.",
    "triage": "Triagem: processa só as áreas mais prováveis de conter documentos de usuário.",
    "blind": "Processamento sem análise interativa, para extrair e categorizar automaticamente.",
}


def ajuda(nome):
    """Explicação do perfil para o painel ({} se não houver)."""
    if nome in AJUDA:
        return dict(AJUDA[nome], nome=nome, descricao=PERFIS[nome]["descricao"], pcba=True)
    if nome in AJUDA_IPED:
        return {"nome": nome, "titulo": nome, "descricao": AJUDA_IPED[nome], "pcba": False}
    return {"nome": nome, "titulo": nome, "descricao": "Perfil personalizado desta instalação.", "pcba": False}


def _origem(raiz, base, relativo):
    """Arquivo do perfil-base, caindo para a raiz quando o perfil não o tem."""
    if base:
        c = os.path.join(raiz, "profiles", base, relativo)
        if os.path.exists(c):
            return c
    return os.path.join(raiz, relativo)


def criar_perfil(raiz, nome, spec, backup, simular=False):
    """Gera profiles/<nome>/ e devolve a lista de chaves aplicadas."""
    relativo = "profiles/" + nome
    destino = os.path.join(raiz, "profiles", nome)
    base = spec.get("base")
    if base and not os.path.isdir(os.path.join(raiz, "profiles", base)):
        raise RuntimeError("Perfil-base '{}' não existe nesta instalação do IPED.".format(base))

    texto = ler_texto(_origem(raiz, base, "IPEDConfig.txt"))
    aplicadas = []
    for k, v in sorted(spec["ipedconfig"].items()):
        texto = definir_chave(texto, k, v)
        aplicadas.append(("IPEDConfig.txt", k, v))

    arquivos_conf = {}
    if base:
        pasta_base = os.path.join(raiz, "profiles", base, "conf")
        if os.path.isdir(pasta_base):
            for f in os.listdir(pasta_base):
                if os.path.isfile(os.path.join(pasta_base, f)):
                    arquivos_conf[f] = ler_texto(os.path.join(pasta_base, f))
    for arquivo, chaves in sorted(spec.get("conf", {}).items()):
        if arquivo not in arquivos_conf:
            arquivos_conf[arquivo] = ler_texto(_origem(raiz, base, "conf/" + arquivo))
        for k, v in sorted(chaves.items()):
            arquivos_conf[arquivo] = definir_chave(arquivos_conf[arquivo], k, v)
            aplicadas.append(("conf/" + arquivo, k, v))

    if simular:
        return aplicadas
    backup.proteger(relativo)
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    gravar_texto(os.path.join(destino, "IPEDConfig.txt"), texto)
    for arquivo, conteudo in arquivos_conf.items():
        gravar_texto(os.path.join(destino, "conf", arquivo), conteudo)
    gravar_texto(os.path.join(destino, "LEIAME-PCBA.txt"),
                 "Perfil gerado pelo instalador IPED-PCBA. Base: {}.\r\n{}\r\n".format(
                     base or "configuração da raiz", spec["descricao"]))
    return aplicadas


def criar_perfis(raiz, backup, simular=False, nomes=None):
    resultado = {}
    for nome in sorted(nomes or PERFIS):
        resultado[nome] = criar_perfil(raiz, nome, PERFIS[nome], backup, simular)
    return resultado


def atualizar_se_preciso(raiz, nome):
    """Regera um perfil da PCBA já instalado quando o pacote mudou as chaves dele (por exemplo OCR
    ligado numa versão nova), com backup. Devolve aviso ou None."""
    spec = PERFIS.get(nome)
    arq = os.path.join(raiz, "profiles", nome, "IPEDConfig.txt")
    if not spec or not os.path.isfile(arq):
        return None
    atuais = ler_chaves(ler_texto(arq))
    if all(atuais.get(k) == v for k, v in spec["ipedconfig"].items()):
        return None
    backup = Backup(raiz)
    criar_perfil(raiz, nome, spec, backup)
    backup.fechar({"motivo": "perfil {} atualizado pelo painel".format(nome)})
    return "Perfil {} atualizado para esta versão do pacote (backup em {}).".format(nome, backup.nome)
