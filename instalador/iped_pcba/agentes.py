"""Agentes de IA prontos para o painel: cada um tem um papel, as ferramentas do MCP que pode usar
e perguntas prontas. Funcionam com a IA local (Ollama, LM Studio) pelo próprio painel e também
podem ser copiados para Claude Desktop, Antigravity ou Hermes.

Texto entre [COLCHETES] numa pergunta é para o analista trocar antes de enviar.
"""

REGRAS = """Você é um assistente de análise de evidências digitais da Polícia Civil da Bahia (PCBA). \
Trabalha sobre um caso processado pelo IPED, consultado pelas ferramentas do MCP iped-pcba.

Regras:
- Responda em português do Brasil, em texto corrido e objetivo.
- Use só o que as ferramentas devolverem. Não invente nomes, números, datas nem conteúdo. Se não achou, diga que não achou.
- Cite sempre o ID do item (doc_id) e a data de cada fato que relatar, para o analista conferir no IPED.
- Datas: diga se estão em UTC ou no horário de Brasília (GMT-3).
- Você aponta indícios; quem conclui é o analista. Não faça juízo de culpa.
- Prefira poucas chamadas bem feitas: comece pelo resumo e pela busca, depois leia só os itens relevantes.
- Buscas (search_documents) usam a sintaxe do IPED/Lucene: palavras, "frases entre aspas", OR, AND, category:"Nome".
"""

LEITURA_BASICA = ["get_case_summary", "list_sources", "list_categories", "search_documents",
                  "get_document_text", "get_document_metadata"]

AGENTES = [
    {
        "id": "triagem",
        "nome": "Triagem inicial",
        "descricao": "Visão geral do caso: titular, fontes, categorias, contatos principais e o que priorizar.",
        "papel": "Faça a triagem inicial do caso, como um analista experiente faria no primeiro contato com a evidência.",
        "ferramentas": LEITURA_BASICA + ["get_device_and_owner_info", "get_top_contacts", "list_ai_filters",
                                         "list_bookmarks"],
        "prompts": [
            {"titulo": "Resumo inicial do caso",
             "texto": "Faça um resumo inicial do caso: fontes de evidência, provável titular de cada dispositivo, "
                      "categorias com mais itens, os 10 contatos mais ativos e as detecções automáticas do IPED. "
                      "Termine com 5 pontos para priorizar na análise."},
            {"titulo": "Quem é o titular?",
             "texto": "Identifique o provável titular de cada dispositivo do caso (nome, telefones, e-mails e contas), "
                      "dizendo de onde veio cada informação."},
            {"titulo": "O que existe sobre [ASSUNTO]?",
             "texto": "Procure no caso tudo sobre [ASSUNTO] e diga em quais categorias aparece, quantos itens e quais "
                      "os mais relevantes, com ID e data."},
        ],
    },
    {
        "id": "comunicacoes",
        "nome": "Comunicações",
        "descricao": "WhatsApp, Telegram, SMS, chamadas e e-mails: interlocutores, grupos e conversas.",
        "papel": "Analise as comunicações do caso: quem fala com quem, quando e sobre o quê.",
        "ferramentas": LEITURA_BASICA + ["get_top_contacts", "get_communications_graph", "get_timeline",
                                         "get_item_relations"],
        "prompts": [
            {"titulo": "Principais interlocutores",
             "texto": "Liste os 15 interlocutores mais ativos com número de mensagens e chamadas, primeiro e último "
                      "contato, e o assunto predominante de cada um."},
            {"titulo": "Conversas com [CONTATO]",
             "texto": "Mostre a rede de comunicações em torno de [CONTATO] e resuma as conversas com ele, em ordem "
                      "cronológica, destacando combinados de encontro, pagamentos e menções a terceiros."},
            {"titulo": "Mensagens sobre [ASSUNTO]",
             "texto": "Procure mensagens sobre [ASSUNTO] (use sinônimos e gírias) e transcreva os trechos relevantes "
                      "com ID, data, remetente e destinatário."},
            {"titulo": "Grupos do titular",
             "texto": "Liste os grupos de mensagens do caso, com participantes mais ativos e o tema de cada grupo."},
        ],
    },
    {
        "id": "financeiro",
        "nome": "Financeiro",
        "descricao": "PIX, transferências, comprovantes, contas bancárias e criptoativos.",
        "papel": "Levante a movimentação financeira citada no caso.",
        "ferramentas": LEITURA_BASICA + ["query_ai_detections", "list_ai_filters", "get_timeline"],
        "prompts": [
            {"titulo": "Comprovantes e PIX",
             "texto": "Procure comprovantes de PIX, TED, DOC e transferências (inclusive imagens com OCR). Para cada um: "
                      "ID, data, valor, pagador, recebedor, banco e chave PIX, em tabela."},
            {"titulo": "Chaves PIX e contas citadas",
             "texto": "Liste as chaves PIX, contas bancárias, agências e CPFs/CNPJs citados em mensagens e documentos, "
                      "com quem citou e quando."},
            {"titulo": "Criptoativos",
             "texto": "Procure carteiras de criptomoeda, endereços de carteira, exchanges e frases-semente no caso."},
        ],
    },
    {
        "id": "linha_tempo",
        "nome": "Linha do tempo",
        "descricao": "Reconstrói o que aconteceu no dispositivo num dia ou ao redor de um horário.",
        "papel": "Reconstrua a cronologia de eventos do dispositivo.",
        "ferramentas": LEITURA_BASICA + ["get_timeline", "get_events_around_time"],
        "prompts": [
            {"titulo": "O que aconteceu em [DATA]",
             "texto": "Monte a linha do tempo do dia [DATA] (horário de Brasília): mensagens, chamadas, fotos, "
                      "navegação e localizações, em ordem."},
            {"titulo": "Ao redor de [DATA HORA]",
             "texto": "Reconstrua a atividade do dispositivo 60 minutos antes e depois de [DATA HORA] (horário de Brasília)."},
        ],
    },
    {
        "id": "localizacao",
        "nome": "Localização",
        "descricao": "Locais, coordenadas, fotos com GPS e deslocamentos.",
        "papel": "Levante as informações de localização do caso.",
        "ferramentas": LEITURA_BASICA + ["get_timeline"],
        "prompts": [
            {"titulo": "Locais entre [DATA] e [DATA]",
             "texto": "Liste os registros de localização e fotos com GPS entre [DATA] e [DATA], com coordenadas, "
                      "endereço quando houver e horário."},
            {"titulo": "Endereços citados",
             "texto": "Procure endereços, pontos de referência e links de mapas citados em mensagens."},
        ],
    },
    {
        "id": "midias",
        "nome": "Mídias e detecções",
        "descricao": "Armas, drogas, nudez, faces e imagens semelhantes detectadas pelo IPED.",
        "papel": "Revise as detecções automáticas de imagens e vídeos. Nunca descreva conteúdo sexual envolvendo menores; "
                 "apenas informe IDs e caminhos.",
        "ferramentas": ["get_case_summary", "list_ai_filters", "query_ai_detections", "get_document_metadata",
                        "search_similar_images", "search_similar_faces"],
        "prompts": [
            {"titulo": "Armas e drogas detectadas",
             "texto": "Liste as imagens com armas e com drogas detectadas, com ID, caminho, data e pontuação."},
            {"titulo": "Imagens parecidas com o item [ID]",
             "texto": "Procure imagens parecidas com o item [ID] e diga de onde vieram e quando."},
        ],
    },
    {
        "id": "marcador",
        "nome": "Marcação no caso",
        "descricao": "Cria marcadores no caso com os resultados de uma busca (precisa da escrita liberada).",
        "papel": "Organize os achados em marcadores do IPED para revisão humana. Sempre explique no comentário do "
                 "marcador qual busca foi usada.",
        "escrita": True,
        "ferramentas": ["search_documents", "list_bookmarks", "bookmark_search_results", "add_to_bookmark",
                        "set_bookmark_comment"],
        "prompts": [
            {"titulo": "Marcar [ASSUNTO]",
             "texto": "Procure itens sobre [ASSUNTO], mostre quantos achou e marque-os no marcador \"[NOME DO MARCADOR] - "
                      "revisar\", com comentário explicando a busca."},
        ],
    },
    {
        "id": "redator",
        "nome": "Redator do RT",
        "descricao": "Lê os achados e escreve partes do relatório técnico, marcadas para sua revisão.",
        "papel": "Ajude a redigir o Relatório Técnico (RT) no modelo da PCBA: texto formal, impessoal, em terceira pessoa, "
                 "sem conclusões que caibam ao analista. Deixe [ENTRE COLCHETES] o que não estiver nos dados.",
        "escrita": True,
        "ferramentas": LEITURA_BASICA + ["get_report_draft", "update_report_field", "update_report_analysis",
                                         "get_top_contacts"],
        "prompts": [
            {"titulo": "Apresentação e objetivo",
             "texto": "Leia o rascunho do RT e o resumo do caso e escreva os campos texto_apresentacao e texto_objetivo."},
            {"titulo": "Lacunas do RT",
             "texto": "Leia o rascunho do RT e liste as lacunas que faltam preencher, dizendo onde no caso eu posso achar "
                      "cada informação."},
            {"titulo": "Análise de [PROVEDOR]",
             "texto": "Com base nos achados do caso, rascunhe o texto da análise do provedor [PROVEDOR] no RT."},
        ],
    },
]


def por_id(agente_id):
    for a in AGENTES:
        if a["id"] == agente_id:
            return a
    raise ValueError("Agente desconhecido: {}".format(agente_id))


def sistema(agente):
    return REGRAS + "\nSeu papel agora: " + agente["papel"]


def texto_para_copiar(agente, pergunta):
    """Instruções + pergunta numa mensagem só, para colar em Claude Desktop, Antigravity ou Hermes."""
    return "{}\n\nPergunta:\n{}".format(sistema(agente), pergunta)


def para_painel():
    return [dict(a, sistema=sistema(a)) for a in AGENTES]
