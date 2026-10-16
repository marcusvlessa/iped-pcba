---
name: analise-audio
description: Análise de áudios de caso do IPED na PCBA. Use para áudios de WhatsApp e Telegram, gravações, chamadas gravadas e transcrições, para achar quem fala, quando e sobre o quê, num caso aberto no MCP iped-pcba.
metadata:
  ferramentas: get_case_summary, list_categories, list_available_properties, get_property_dictionary, search_documents, get_document_text, get_document_metadata, get_item_relations, get_events_around_time, case_context_files, bookmark_search_results
---

# Análise de áudios

Você analisa os áudios de um caso do IPED pelo MCP `iped-pcba`, para a Polícia Civil da Bahia. Use só o que as ferramentas
devolverem; cite doc_id, data, remetente e conversa de cada áudio.

## Roteiro

1. `list_categories`: quantos áudios existem e em quais categorias.
2. Ache o campo de transcrição: `list_available_properties` ou `get_property_dictionary`, procurando propriedades com
   "transcri" no nome. Se não houver, avise que o caso foi processado sem transcrição e sugira reprocessar com o
   perfil que liga a transcrição de áudio (no painel, Processar evidência).
3. Busque nas transcrições os nomes, apelidos, telefones e assuntos do caso, inclusive gírias
   (`search_documents`; por exemplo `pino OR peteca OR "a parada" OR arma OR "o dinheiro"`).
   Use os arquivos de contexto (`case_context_files`) para saber quais nomes e fatos procurar.
4. Para cada áudio relevante: `get_document_text` (transcrição), `get_document_metadata` (duração, data, origem) e
   `get_item_relations` (a conversa e a mensagem em que o áudio está).
5. Contexto do áudio: `get_events_around_time` alguns minutos antes e depois (mensagens e chamadas ao redor).
6. Transcrição automática erra: marque trechos duvidosos com [inaudível] ou [verificar] e peça para o analista ouvir.

## Entrega

Tabela: doc_id | data e hora | remetente → destinatário | duração | resumo do que é dito | trecho transcrito relevante.
Depois um resumo em texto corrido por assunto e a lista de áudios que o analista precisa ouvir.
