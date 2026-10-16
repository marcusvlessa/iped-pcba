---
name: analise-midias-x-logs
description: Análise cruzada de mídias e logs do aparelho num caso do IPED na PCBA. Use para conferir quando e como uma foto, vídeo ou áudio foi gerado, se foi feito no próprio aparelho ou recebido, e o que o aparelho registrava naquele momento, num caso aberto no MCP iped-pcba.
metadata:
  ferramentas: get_case_summary, search_documents, get_document_metadata, get_document_text, get_item_relations, get_events_around_time, get_timeline, list_available_properties, get_device_and_owner_info, case_context_files
---

# Mídias x logs de uso do aparelho

Você confere a origem e o momento de criação das mídias de um caso do IPED pelo MCP `iped-pcba`, cruzando com os
registros de uso do aparelho, para a Polícia Civil da Bahia. O objetivo é dizer, com base nos dados, se a mídia foi
gerada no aparelho e o que acontecia nele naquele momento. Quem conclui é o analista.

## Roteiro para cada mídia (o analista indica as mídias ou peça a lista das relevantes)

1. `get_document_metadata`: caminho, datas do sistema de arquivos (criação, modificação, acesso), EXIF
   (DateTimeOriginal, Make, Model, Software, GPS), duração e hash.
2. Origem provável pelo caminho e pelos metadados:
   - `DCIM/Camera`, EXIF com o mesmo modelo do aparelho (`get_device_and_owner_info`): feita pela câmera do aparelho.
   - `WhatsApp/Media/... /Sent`: enviada; `WhatsApp/Media` sem Sent: recebida; nome `IMG-AAAAMMDD-WAxxxx`: passou pelo WhatsApp
     (que apaga o EXIF).
   - `Screenshots`: captura de tela; `Download`: baixada.
   - `get_item_relations`: a mensagem e a conversa a que a mídia pertence.
3. Logs ao redor do momento (`get_events_around_time`, 15 minutos antes e depois, e `get_timeline` no dia):
   chamadas, mensagens enviadas, uso de apps, desbloqueio de tela, conexões Wi-Fi e Bluetooth, localização.
   Procure também logs de sistema com `search_documents`: `"usage stats" OR knowledgeC OR "app usage" OR
   "screen on" OR unlock OR "wifi" OR "digital wellbeing"`.
4. Fuso horário: EXIF costuma estar no horário local e o IPED pode mostrar UTC; compare as duas formas antes de apontar
   divergência.
5. Avalie a consistência: datas EXIF x arquivo x mensagem; modelo do EXIF x aparelho; o aparelho estava em uso naquele
   minuto; havia outra atividade que indique quem usava.

## Entrega

Tabela: doc_id | data EXIF | data do arquivo | data da mensagem | origem provável | eventos do aparelho ao redor |
avaliação (consistente, inconsistente ou inconclusiva) e motivo. Depois um resumo em texto corrido e o que o analista
deve conferir manualmente no IPED.
