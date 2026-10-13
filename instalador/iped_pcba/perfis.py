"""Perfis de processamento da PCBA.

O IPED carrega primeiro a configuração da raiz e depois a do perfil
(-profile <nome>): um IPEDConfig.txt no perfil substitui o da raiz e cada
arquivo em profiles/<nome>/conf/ substitui o arquivo de mesmo nome em conf/.
Por isso cada perfil aqui é gerado como cópia completa do perfil-base com as
chaves da PCBA aplicadas por cima.
"""

import os
import shutil

from .configurar import definir_chave, gravar_texto, ler_texto

# Cada perfil: base do IPED, chaves do IPEDConfig.txt e chaves de arquivos em conf/.
PERFIS = {
    "pcba-celular": {
        "descricao": "Extrações de celular (UFDR, Cellebrite, Oxygen, backups). "
                     "Transcreve áudios de WhatsApp e gera grafo de contatos.",
        "base": None,
        "ipedconfig": {
            "enableAudioTranscription": "true",
            "enableGraphGeneration": "true",
            "enableQRCode": "true",
            "enableImageSimilarity": "true",
            "enableHTMLReport": "true",
            "enableOCR": "false",
            "enableCarving": "false",
        },
        "conf": {},
    },
    "pcba-computador": {
        "descricao": "Imagens de disco de computador. Recupera apagados (carving) e "
                     "transcreve áudios.",
        "base": "forensic",
        "ipedconfig": {
            "enableAudioTranscription": "true",
            "enableGraphGeneration": "true",
            "enableHTMLReport": "true",
            "enableOCR": "false",
        },
        "conf": {},
    },
    "pcba-telematica": {
        "descricao": "Retornos de provedores (Google, Meta/WhatsApp, Apple, operadoras). "
                     "Expande os pacotes, indexa conteúdo e regex; sem carving nem thumbs de vídeo.",
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
            "enableImageSimilarity": "false",
            "enableOCR": "false",
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
