"""Relatório Técnico (RT) no modelo institucional da PCBA, gerado em .docx.

Ordem das seções (modelo do RT de interceptação/telemática):
CAPA → BLOCO DE QUALIFICAÇÃO → RESUMO EXECUTIVO (opcional) → DA APRESENTAÇÃO → DO OBJETIVO →
DOS FATOS E RELAÇÕES → DO CADASTRO TELEFÔNICO → DO CANCELAMENTO DOS TERMINAIS IMPRODUTIVOS
(opcional) → ANÁLISES POR PROVEDOR (tabela INVESTIGADO | CONTA | PERÍODO, texto, quadros e
conclusão) → DA METODOLOGIA DE ANÁLISE (IPED, MD5, SHA-256) → PROVIDÊNCIAS NECESSÁRIAS →
ASSINATURAS.

Os dados da unidade (cabeçalho, endereço, e-mails, analistas) ficam em ~/.iped-pcba/unidade.json
e servem para qualquer delegacia: nada aqui é fixo de uma unidade. Tudo o que estiver entre
colchetes, [ASSIM], sai em vermelho no Word para o analista completar.
"""

import copy
import datetime
import hashlib
import json
import os

from . import docxmin
from .configurar import gravar_texto, ler_texto

PASTA_MODELOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos")
LOGO_PADRAO = os.path.join(PASTA_MODELOS, "logo_pcba.jpeg")
ARQ_UNIDADE = os.path.join(os.path.expanduser("~"), ".iped-pcba", "unidade.json")
PASTA_CASO = "iped-pcba-relatorio"

SIGILO_CITACAO = (
    "“Todo aquele que tiver conhecimento, nos termos deste Decreto, de assuntos sigilosos, fica sujeito "
    "às sanções administrativas, civis e penais decorrentes da eventual divulgação dos mesmos” "
    "(Art. 37 § 1º do Decreto Federal nº 4.553, de 27 Dez 2002).")

UNIDADE_PADRAO = {
    "orgao": "POLÍCIA CIVIL DA BAHIA",
    "departamento": "[DEPARTAMENTO]",
    "unidade": "[UNIDADE]",
    "endereco": "[ENDEREÇO E TELEFONE DA UNIDADE]",
    "sigla_rt": "[SIGLA DA UNIDADE]/POLÍCIA CIVIL",
    "remetente_da": "[UNIDADE REMETENTE]",
    "origem": "[UNIDADE DE ORIGEM]",
    "nucleo": "[NÚCLEO RESPONSÁVEL]",
    "emails_obrigatorios": [],
    "analistas": [],
    "logo": "",
    "ferramenta_hash": "IPED-PCBA",
}

# Campos do RT, na ordem em que o painel mostra. (chave, rótulo, várias linhas?)
CAMPOS = [
    ("numero_rt", "Número do RT (ex.: 001/2026)", False),
    ("data_rt", "Data por extenso", False),
    ("nome_operacao", "Operação (e fase)", False),
    ("assunto", "Assunto (tipo penal)", False),
    ("destinatario_ao", "AO (autoridade destinatária)", False),
    ("processo", "Processo n.º", False),
    ("difusao", "Difusão (juiz/autoridade)", False),
    ("juiz_autorizador", "Juiz autorizador", False),
    ("vara_comarca", "Vara / Comarca", False),
    ("resumo_executivo", "Resumo executivo (opcional)", True),
    ("texto_apresentacao", "Da apresentação", True),
    ("texto_objetivo", "Do objetivo (vazio = texto padrão)", True),
    ("texto_fatos_relacoes", "Dos fatos e relações", True),
    ("texto_cadastro_telefonico", "Do cadastro telefônico", True),
    ("texto_cancelamento", "Do cancelamento dos terminais improdutivos (opcional)", True),
    ("metodologia", "Metodologia (vazio = texto padrão)", True),
    ("providencias_intro", "Providências: abertura (vazio = texto padrão)", True),
]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def data_extenso(d=None):
    d = d or datetime.date.today()
    return "{} de {} de {}".format(d.day, MESES[d.month - 1], d.year)


def rt_vazio():
    return {
        "numero_rt": "", "data_rt": data_extenso(), "nome_operacao": "", "assunto": "",
        "destinatario_ao": "", "processo": "", "difusao": "", "juiz_autorizador": "", "vara_comarca": "",
        "resumo_executivo": "", "texto_apresentacao": "", "texto_objetivo": "", "texto_fatos_relacoes": "",
        "texto_cadastro_telefonico": "", "texto_cancelamento": "", "analises": [], "metodologia": "",
        "hashes": [], "providencias_intro": "", "pedidos": [], "incluir_clausulas": True,
        "emails_investigadores": [], "analistas": [],
    }


# ------------------------------------------------------------------ unidade e caso

def ler_unidade(caminho=None):
    u = copy.deepcopy(UNIDADE_PADRAO)
    try:
        u.update(json.loads(ler_texto(caminho or ARQ_UNIDADE)))
    except (OSError, ValueError):
        pass
    return u


def gravar_unidade(dados, caminho=None):
    u = copy.deepcopy(UNIDADE_PADRAO)
    u.update({k: v for k, v in dados.items() if k in UNIDADE_PADRAO})
    caminho = caminho or ARQ_UNIDADE
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    gravar_texto(caminho, json.dumps(u, indent=2, ensure_ascii=False))
    return u


def arq_rt(caso):
    return os.path.join(caso, PASTA_CASO, "rt.json")


def ler_rt(caso):
    d = rt_vazio()
    try:
        d.update(json.loads(ler_texto(arq_rt(caso))))
    except (OSError, ValueError):
        pass
    return d


def gravar_rt(caso, dados):
    d = rt_vazio()
    d.update(dados)
    caminho = arq_rt(caso)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    if os.path.isfile(caminho):
        # guarda a versão anterior: o rascunho é editado por pessoas e pela IA
        hist = os.path.join(os.path.dirname(caminho), "historico")
        os.makedirs(hist, exist_ok=True)
        carimbo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        gravar_texto(os.path.join(hist, "rt-{}.json".format(carimbo)), ler_texto(caminho))
    gravar_texto(caminho, json.dumps(d, indent=2, ensure_ascii=False))
    return d


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest().upper()


def lista_de_arquivos(caso):
    """Arquivos 'Lista de Arquivos.csv' (ou FileList.csv) exportados do IPED dentro do caso."""
    achados = []
    for raiz, dirs, arqs in os.walk(caso):
        dirs[:] = [d for d in dirs if d not in ("index", "data", "lib", "jre", "tools", "thumbs", "conf")]
        for a in arqs:
            if a.lower() in ("lista de arquivos.csv", "filelist.csv"):
                achados.append(os.path.join(raiz, a))
        if len(achados) > 20:
            break
    return achados


# ------------------------------------------------------------------ texto padrão

def _g(valor, rotulo):
    v = valor.strip() if isinstance(valor, str) else valor
    return v if v else "[{}]".format(rotulo)


def preparar(dados, unidade):
    """Aplica os textos padrão do modelo e devolve o RT completo que será impresso."""
    d = rt_vazio()
    d.update(dados or {})
    u = unidade
    d["numero_rt"] = _g(d["numero_rt"], "Nº/ANO")
    d["nome_operacao"] = _g(d["nome_operacao"], "OPERAÇÃO")
    d["data_rt"] = _g(d["data_rt"], "DATA")
    d["remetente_da"] = d.get("remetente_da") or u["remetente_da"]
    d["origem"] = d.get("origem") or u["origem"]
    if not (d["texto_objetivo"] or "").strip():
        d["texto_objetivo"] = (
            "O presente relatório tem por objetivo levar ao conhecimento da autoridade policial os fatos "
            "relevantes obtidos a partir do monitoramento dos terminais móveis celulares interceptados com "
            "autorização expedida pelo Excelentíssimo {}, {}, detalhados abaixo:".format(
                _g(d["juiz_autorizador"], "JUIZ AUTORIZADOR"), _g(d["vara_comarca"], "VARA / COMARCA")))
    if not (d["metodologia"] or "").strip():
        d["metodologia"] = (
            "Importante frisar que a análise do conteúdo extraído foi realizada por meio do IPED – Indexador "
            "e Processador de Evidências Digitais, desenvolvido pela Polícia Federal. Os arquivos extraídos "
            "foram submetidos a processamento e indexação pelo IPED, que realiza a categorização dos dados, "
            "permite buscas indexadas e pré-visualização do conteúdo, apresentando atributos como datas de "
            "criação e acesso, localização no sistema de arquivos e o valor da função de resumo criptográfico "
            "MD5 (hash). Para possibilitar a verificação da integridade, o IPED gerou, para cada material, uma "
            "lista com o nome de cada arquivo e o respectivo código de integridade (hash) MD5, copiada para o "
            "arquivo “Lista de Arquivos.csv”, o qual foi submetido ao algoritmo SHA-256 ({}), conforme "
            "abaixo:".format(u.get("ferramenta_hash") or "IPED-PCBA"))
    if not d["hashes"]:
        d["hashes"] = ["Lista de Arquivos.csv — SHA-256: [HASH SHA-256]"]
    if not (d["providencias_intro"] or "").strip():
        d["providencias_intro"] = ("Diante de todo o conhecimento produzido pela equipe do {}, sugere-se à "
                                   "autoridade policial:".format(u["nucleo"]))
    if not d["analistas"]:
        d["analistas"] = u["analistas"] or [{"nome": "[NOME DO ANALISTA]", "papel": "Analista do Caso"}]
    emails = list(d.get("emails_investigadores") or [])
    for e in u.get("emails_obrigatorios") or []:
        if e not in emails:
            emails.append(e)
    d["_emails"] = emails or ["[E-MAILS INSTITUCIONAIS]"]
    return d


def lacunas(dados, unidade):
    """Lista (onde, texto) de cada lacuna [ENTRE COLCHETES] que vai sair em vermelho."""
    d = preparar(dados, unidade)
    achadas = []

    def varrer(onde, v):
        if isinstance(v, str):
            for m in docxmin.LACUNA.findall(v):
                achadas.append((onde, m))
        elif isinstance(v, dict):
            for k, x in v.items():
                if not k.startswith("_") or k == "_emails":
                    varrer("{}.{}".format(onde, k) if onde else k, x)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                varrer("{}[{}]".format(onde, i), x)

    obrig = {"destinatario_ao": "NOME E CARGO DA AUTORIDADE DESTINATÁRIA", "assunto": "TIPO PENAL / ASSUNTO",
             "processo": "NÚMERO DO PROCESSO", "difusao": "NOME E CARGO DO DESTINATÁRIO DA DIFUSÃO",
             "texto_apresentacao": "SÍNTESE DA INVESTIGAÇÃO",
             "texto_fatos_relacoes": "ORDEM JUDICIAL, PERÍODO, LINHAS E OPERADORAS"}
    for k, rot in obrig.items():
        if not (d.get(k) or "").strip():
            achadas.append((k, "[{}]".format(rot)))
    varrer("", {k: v for k, v in d.items() if not k.startswith("_") or k == "_emails"})
    for k in ("orgao", "departamento", "unidade", "endereco", "sigla_rt", "nucleo"):
        for m in docxmin.LACUNA.findall(unidade.get(k) or ""):
            achadas.append(("unidade." + k, m))
    return achadas


# ------------------------------------------------------------------ montagem

def _paragrafos(bloco, texto):
    for c in [x.strip() for x in str(texto or "").replace("\r", "").split("\n") if x.strip()]:
        bloco.paragrafo(c)


def _titulo(bloco, texto):
    bloco.paragrafo(texto, negrito=True, alinhar="centro", antes=10, depois=8)


def _sigilo(bloco):
    bloco.paragrafo("SIGILO LEGAL", negrito=True, alinhar="centro", tam=11, antes=8, depois=0)
    bloco.paragrafo(SIGILO_CITACAO, italico=True, alinhar="centro", tam=9, depois=6)


def gerar_docx(dados, saida, unidade=None):
    u = unidade or ler_unidade()
    d = preparar(dados, u)
    logo = u.get("logo") or LOGO_PADRAO
    logo = logo if os.path.isfile(logo) else None
    doc = docxmin.Documento()

    # ---- capa (sem cabeçalho) ----
    capa, _, _ = doc.nova_secao(margens=(3.0, 2.5, 2.5, 3.0))
    if logo:
        capa.imagem(logo, 3.2)
    capa.paragrafo(" ", depois=18)
    capa.paragrafo("RELATÓRIO TÉCNICO", negrito=True, alinhar="centro", tam=34, depois=4)
    capa.paragrafo("Nº: " + d["numero_rt"], negrito=True, alinhar="centro", tam=18, depois=24)
    capa.paragrafo("OPERAÇÃO: {}.".format(d["nome_operacao"].upper()), negrito=True, alinhar="centro",
                   tam=14, depois=18)
    capa.paragrafo("DIFUSÃO: " + _g(d["difusao"], "NOME E CARGO DO DESTINATÁRIO DA DIFUSÃO"), negrito=True,
                   alinhar="centro", depois=40)
    _sigilo(capa)

    # ---- corpo ----
    c, cab, rod = doc.nova_secao(margens=(4.2, 2.5, 2.8, 3.0), cabecalho=True, rodape=True)
    cab.paragrafo("SIGILO LEGAL", negrito=True, alinhar="centro", tam=9, depois=0)
    if logo:
        cab.imagem(logo, 2.0)
    for txt, neg, tam in ((u["orgao"], True, 11), (u["departamento"], True, 11), (u["unidade"], True, 11),
                          (u["endereco"], False, 8)):
        if txt:
            cab.paragrafo(txt, negrito=neg, alinhar="centro", tam=tam, depois=0)
    cab.paragrafo("_" * 70, alinhar="centro", tam=6, depois=2, cor="888888")
    rod.paragrafo("SIGILO LEGAL", negrito=True, alinhar="centro", tam=8, depois=0)
    rod.paragrafo(SIGILO_CITACAO, italico=True, alinhar="centro", tam=7, depois=0)
    rod.campos_pagina()

    c.paragrafo("RELATÓRIO TÉCNICO N.º {} – {}".format(d["numero_rt"], u["sigla_rt"]), negrito=True,
                alinhar="centro", depois=8)
    for rot, val in (("DATA:", d["data_rt"]), ("DA:", d["remetente_da"]),
                     ("AO:", _g(d["destinatario_ao"], "NOME E CARGO DA AUTORIDADE DESTINATÁRIA")),
                     ("OPERAÇÃO:", d["nome_operacao"].upper()),
                     ("ASSUNTO:", _g(d["assunto"], "TIPO PENAL / ASSUNTO")), ("ORIGEM:", d["origem"]),
                     ("PROCESSO N.º:", _g(d["processo"], "NÚMERO DO PROCESSO")),
                     ("DIFUSÃO:", _g(d["difusao"], "NOME E CARGO DO DESTINATÁRIO DA DIFUSÃO"))):
        c.rotulo(rot, val)

    if (d["resumo_executivo"] or "").strip():
        _titulo(c, "RESUMO EXECUTIVO")
        _paragrafos(c, d["resumo_executivo"])
    _titulo(c, "DA APRESENTAÇÃO")
    _paragrafos(c, _g(d["texto_apresentacao"],
                      "INSERIR A SÍNTESE DA INVESTIGAÇÃO: INSTAURAÇÃO, FATOS, AUTORIA E MATERIALIDADE"))
    _titulo(c, "DO OBJETIVO")
    _paragrafos(c, d["texto_objetivo"])
    _titulo(c, "DOS FATOS E RELAÇÕES")
    _paragrafos(c, _g(d["texto_fatos_relacoes"],
                      "INSERIR A DESCRIÇÃO DA ORDEM JUDICIAL, PERÍODO DA INTERCEPTAÇÃO, LINHAS E OPERADORAS"))
    if d.get("texto_cadastro_telefonico") is not None:
        _titulo(c, "DO CADASTRO TELEFÔNICO")
        _paragrafos(c, _g(d["texto_cadastro_telefonico"],
                          "INSERIR DADOS CADASTRAIS DOS TERMINAIS (TITULAR, CPF, ENDEREÇO, IMEI, ALVO)"))
    if (d.get("texto_cancelamento") or "").strip():
        _titulo(c, "DO CANCELAMENTO DOS TERMINAIS IMPRODUTIVOS")
        _paragrafos(c, d["texto_cancelamento"])

    for an in d.get("analises") or []:
        prov = str(an.get("provedor") or "[PROVEDOR]").upper()
        _titulo(c, an.get("titulo") or "DA ANÁLISE DOS DADOS TELEMÁTICOS – " + prov)
        if an.get("tabela"):
            c.tabela(["INVESTIGADO", "CONTA", "PERÍODO"],
                     [[l.get("investigado", ""), l.get("conta", ""), l.get("periodo", "")] for l in an["tabela"]],
                     larguras_cm=[6.0, 4.5, 5.0], alinhamentos=["esq", "centro", "esq"])
        _paragrafos(c, an.get("texto"))
        for q in an.get("quadros") or []:
            c.paragrafo(q.get("titulo", ""), negrito=True, alinhar="esq", tam=10, antes=4, depois=2)
            c.tabela(q["colunas"], q["linhas"], tam=9)
        if an.get("conclusao"):
            c.paragrafo("CONCLUSÃO DA ANÁLISE — " + prov, negrito=True, alinhar="esq", tam=11, antes=6, depois=4)
            _paragrafos(c, an["conclusao"])

    _titulo(c, "DA METODOLOGIA DE ANÁLISE")
    _paragrafos(c, d["metodologia"])
    for h in d["hashes"]:
        c.paragrafo("• " + str(h), alinhar="esq", tam=11, depois=2)
    _sigilo(c)

    _titulo(c, "PROVIDÊNCIAS NECESSÁRIAS")
    _paragrafos(c, d["providencias_intro"])
    for p in d.get("pedidos") or []:
        if p.get("titulo"):
            c.paragrafo(p["titulo"], negrito=True, alinhar="esq", tam=11, antes=6, depois=4)
        _paragrafos(c, p.get("texto"))
    if d.get("incluir_clausulas", True):
        c.paragrafo(
            "É importante ressaltar que, para fins da interceptação das comunicações telefônicas e do fluxo "
            "de dados telemáticos em tempo real, deve constar expressamente na decisão judicial uma data "
            "futura, estipulada no prazo de até 15 dias a partir do recebimento formal da ordem pelo provedor, "
            "para o início efetivo do monitoramento eletrônico, garantindo-se a viabilidade operacional e o "
            "cumprimento integral e contínuo do prazo de 15 dias para a interceptação do fluxo telemático.",
            antes=6)
        c.paragrafo(
            "Requer-se que todas as respostas e pacotes de dados digitais sejam remetidos diretamente aos "
            "e-mails institucionais dos investigadores responsáveis na estrutura da Polícia Civil da Bahia, a "
            "saber: " + ", ".join(d["_emails"]) + "; que as empresas observem o caráter estritamente SIGILOSO "
            "da medida, vedada qualquer notificação ao usuário alvo ou a terceiros; a fixação de multa diária "
            "sancionatória em favor do Estado da Bahia (art. 537 do CPC) para o caso de descumprimento "
            "injustificado ou atendimento parcial da ordem após 48 horas da remessa oficial; e a manutenção "
            "do sigilo absoluto dos autos judiciais.", depois=8)

    c.paragrafo(" ", depois=16)
    an = d["analistas"]
    for i in range(0, len(an), 2):
        grupo = an[i:i + 2]
        c.tabela([a.get("nome") or "[NOME]" for a in grupo],
                 [[(a.get("papel") or "Analista do Caso")
                         + (" — Matrícula {}".format(a["matricula"]) if a.get("matricula") else "") for a in grupo]],
                 larguras_cm=[7.5] * len(grupo), bordas=False, alinhamentos=["centro"] * len(grupo), tam=11,
                 fundo_cabecalho=None)
    return doc.salvar(saida)
