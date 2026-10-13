"""Visão do caso: números para os gráficos do painel, alertas e sugestões.

De onde vêm os dados (tudo dentro da pasta do caso, nada sai da máquina):
  - <caso>/iped-pcba-painel/visao.json: gerado pelo MCP (--exportar-visao), lendo o índice do IPED.
  - <caso>/iped-pcba-painel/telematica.json: gravado ao importar o CSV telemático (passo 5).
  - rascunho do RT e log de auditoria da IA.

Alertas e sugestões são regras fixas e explicáveis (cada uma diz de onde veio o número). Não
são conclusões: apontam onde o analista deve olhar primeiro.
"""

import json
import os
import re
import statistics

from .configurar import gravar_texto, ler_texto

PASTA = "iped-pcba-painel"
ARQ_VISAO = "visao.json"
ARQ_TEL = "telematica.json"

ALTO, MEDIO, INFO = "alto", "medio", "info"

_CRIPTO = re.compile(r"cript|encrypt", re.I)
_AUDIO = re.compile(r"áudio|audio", re.I)
_IMAGEM = re.compile(r"imag|foto|image|photo", re.I)
_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def pasta(caso):
    return os.path.join(caso, PASTA)


def _ler_json(caminho):
    try:
        return json.loads(ler_texto(caminho))
    except (OSError, ValueError):
        return None


def gravar_telematica(caso, dados, origem):
    dados = dict(dados, origem=os.path.abspath(origem))
    os.makedirs(pasta(caso), exist_ok=True)
    gravar_texto(os.path.join(pasta(caso), ARQ_TEL), json.dumps(dados, ensure_ascii=False, indent=1))


def mes_br(m):
    a, n = m.split("-")
    return "{}/{}".format(_MES[int(n) - 1], a)


def picos(meses, minimo=10):
    """Meses muito acima do normal: acima de média + 2 desvios e de 3x a mediana dos meses com itens."""
    vals = [m["total"] for m in meses if m["total"] > 0]
    if len(vals) < 4:
        return []
    media, desvio, mediana = statistics.mean(vals), statistics.pstdev(vals), statistics.median(vals)
    lim = max(media + 2 * desvio, 3 * mediana, minimo)
    return [dict(m, vezes=round(m["total"] / mediana, 1)) for m in meses if m["total"] > lim]


def _total(lista, nome_re):
    return sum(c["total"] for c in lista or [] if nome_re.search(c.get("nome") or ""))


def regras(visao, tel, rt_info, aud, ambiente):
    """Devolve (alertas, sugestoes). Cada item: nivel, titulo, detalhe, fonte e, se houver,
    'ir' (seção do painel) e 'prompt' (pergunta pronta para a IA)."""
    alertas, sug = [], []

    def a(nivel, titulo, detalhe, fonte, **kw):
        alertas.append(dict(nivel=nivel, titulo=titulo, detalhe=detalhe, fonte=fonte, **kw))

    def s(titulo, detalhe, **kw):
        sug.append(dict(titulo=titulo, detalhe=detalhe, **kw))

    if aud and aud.get("existe") and not aud.get("integra"):
        a(ALTO, "Log de auditoria da IA com a cadeia quebrada",
          "{} problema(s) na verificação. Alguma linha foi apagada, inserida ou alterada.".format(
              len(aud.get("problemas") or [])), "auditoria do MCP", ir="casos")

    if visao:
        esp = visao.get("especiais") or {}
        ia = {f.get("id"): f.get("total") or 0 for f in visao.get("ia_filtros") or []}
        cats = visao.get("categorias") or []
        if esp.get("alerta_hash"):
            a(ALTO, "{} item(ns) na base de hashes de alerta".format(esp["alerta_hash"]),
              "Arquivos idênticos a material já catalogado como ilícito. Revise com prioridade e "
              "preserve a cadeia de custódia.", "IPED: hashDb:status=alert")
        if ia.get("csam"):
            a(ALTO, "{} item(ns) com indício de exploração sexual infantil".format(ia["csam"]),
              "Detecção por hash ou pelo classificador do IPED. Confirmação visual obrigatória.",
              "IPED: filtro CSAM", prompt="Liste os itens do filtro csam com nome, caminho e pontuação, "
                                          "sem mostrar miniaturas.")
        for chave, rotulo in (("weapons", "armas de fogo ou munição"), ("drugs", "drogas"),
                              ("crypto_wallets", "carteiras de criptomoeda")):
            if ia.get(chave):
                a(MEDIO, "{} item(ns) com {}".format(ia[chave], rotulo),
                  "Detecção automática do IPED; pode ter falso positivo.", "IPED: filtro " + chave,
                  prompt="Mostre os itens do filtro {} com caminho e data.".format(chave))
        cripto = _total(cats, _CRIPTO)
        if cripto:
            a(MEDIO, "{} arquivo(s) criptografado(s)".format(cripto),
              "Podem esconder conteúdo relevante. Tente senhas encontradas no próprio caso.",
              "IPED: categoria de criptografados",
              prompt="Procure no caso senhas, PINs e frases-senha anotadas que possam abrir os arquivos "
                     "criptografados.")
        if esp.get("apagados"):
            a(INFO, "{} item(ns) apagado(s) recuperado(s)".format(esp["apagados"]),
              "Apagar pode indicar tentativa de ocultação; veja datas e pastas.", "IPED: deleted=true",
              prompt="Resuma os itens apagados por categoria e mostre os mais recentes.")
        if esp.get("recuperados_carving"):
            a(INFO, "{} item(ns) recuperado(s) por carving".format(esp["recuperados_carving"]),
              "Fragmentos recuperados do espaço livre; sem nome nem data originais.", "IPED: carved=true")
        meses = (visao.get("linha_do_tempo") or {}).get("meses") or []
        for p in picos(meses)[:3]:
            a(MEDIO, "Pico de atividade em {}".format(mes_br(p["mes"])),
              "{} itens com data no mês, {} vezes a mediana dos meses.".format(p["total"], p["vezes"]),
              "IPED: linha do tempo", prompt="O que aconteceu no dispositivo em {}? Use a linha do tempo "
                                             "e destaque comunicações.".format(mes_br(p["mes"])))
        contatos = visao.get("contatos") or []
        soma = sum(c.get("total_interactions") or 0 for c in contatos)
        if contatos and soma >= 20:
            c0 = contatos[0]
            parte = round(100.0 * (c0.get("total_interactions") or 0) / soma)
            nome = c0.get("name") or c0.get("identifier")
            if parte >= 35:
                a(INFO, "{} concentra {}% das comunicações".format(nome, parte),
                  "Entre os {} contatos mais ativos.".format(len(contatos)), "IPED: contatos")
            s("Mapear a rede em torno de {}".format(nome),
              "É o interlocutor mais frequente do caso.",
              prompt="Mostre a rede de comunicações em torno de {} e resuma as conversas mais "
                     "recentes.".format(c0.get("identifier") or nome))
        for nome, msg in (visao.get("erros") or {}).items():
            a(INFO, "Parte da visão não foi calculada: " + nome, msg, "MCP")

        if not visao.get("marcadores"):
            s("Criar marcadores", "O caso ainda não tem marcadores. Com a escrita liberada, a IA pode "
              "marcar resultados de busca para você revisar no IPED.",
              prompt="Procure conversas sobre pagamentos, PIX e transferências e marque os resultados "
                     "no marcador 'Financeiro - revisar'.")
        if _total(cats, _AUDIO) and not ia.get("audio_transcripts"):
            s("Transcrever os áudios", "O caso tem {} áudio(s) e nenhuma transcrição. Instale o "
              "faster-whisper no passo 1 e reprocesse com o perfil que transcreve.".format(_total(cats, _AUDIO)),
              ir="config")
        if _total(cats, _IMAGEM) and not ia.get("faces"):
            s("Ativar detecção de faces", "Há imagens e nenhuma face indexada; sem isso a busca por "
              "rosto semelhante não funciona.", ir="config")
    else:
        s("Gerar a visão do caso", "Clique em \"Atualizar números do caso\" para o MCP ler o índice do IPED.")

    if tel:
        noite = sum((tel.get("por_hora") or [0] * 24)[0:6])
        if tel.get("total", 0) >= 20 and noite >= 0.25 * tel["total"]:
            a(MEDIO, "{}% dos registros telemáticos entre 0h e 6h".format(round(100.0 * noite / tel["total"])),
              "Atividade de madrugada acima do comum.", "CSV telemático (horário de Brasília)")
        for c in tel.get("contas") or []:
            if len(c.get("dispositivos") or []) > 1:
                a(INFO, "{} {} usada em {} dispositivos".format(c["provedor"], c["conta"], len(c["dispositivos"])),
                  ", ".join(c["dispositivos"]), "CSV telemático")
        if tel.get("n_ips", 0) > 1:
            s("Pedir cadastro dos IPs", "{} IP(s) distintos nos registros. Os mais frequentes estão no quadro "
              "abaixo; peça à operadora o assinante de cada um com data, hora e porta.".format(tel["n_ips"]),
              ir="relatorio")
    else:
        s("Importar registros telemáticos", "Com o CSV padronizado dos provedores, o painel mostra dias, "
          "horários, interlocutores e IPs.", ir="relatorio")

    if rt_info:
        if rt_info.get("ia_editou"):
            a(MEDIO, "{} campo(s) do RT escritos pela IA aguardando revisão".format(rt_info["ia_editou"]),
              "Revise antes de gerar o documento final.", "rascunho do RT", ir="relatorio")
        if rt_info.get("lacunas"):
            s("Completar o relatório", "{} lacuna(s) em vermelho no rascunho do RT.".format(rt_info["lacunas"]),
              ir="relatorio")

    if ambiente.get("mcp") and not ambiente.get("ia_ligada"):
        s("Ligar a IA ao caso", "Nenhum programa de IA está ligado ao MCP. Use o passo 4.", ir="ia")

    ordem = {ALTO: 0, MEDIO: 1, INFO: 2}
    alertas.sort(key=lambda x: ordem[x["nivel"]])
    return alertas, sug


def ler(caso, ambiente=None):
    from . import auditoria as aud_mod, rt
    visao = _ler_json(os.path.join(pasta(caso), ARQ_VISAO))
    tel = _ler_json(os.path.join(pasta(caso), ARQ_TEL))
    rt_info = None
    arq_rt = os.path.join(caso, rt.PASTA_CASO, "rt.json")
    if os.path.isfile(arq_rt):
        d = rt.ler_rt(caso)
        rt_info = {"lacunas": len(rt.lacunas(d, rt.ler_unidade())), "ia_editou": len(d.get("ia_editou") or {})}
    aud = None
    arq_aud = os.path.join(caso, "iped-pcba-auditoria", "mcp-auditoria.jsonl")
    if os.path.isfile(arq_aud):
        n, problemas = aud_mod.verificar(arq_aud)
        aud = {"existe": True, "registros": n, "problemas": problemas, "integra": not problemas}
    alertas, sugestoes = regras(visao, tel, rt_info, aud, ambiente or {})
    return {"caso": caso, "visao": visao, "telematica": tel, "rt": rt_info, "auditoria": aud,
            "alertas": alertas, "sugestoes": sugestoes}


def comando_exportar(lancador, caso):
    return [lancador, "--case", caso, "--exportar-visao", os.path.join(pasta(caso), ARQ_VISAO)]
