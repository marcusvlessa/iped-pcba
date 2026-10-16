---
name: analise-geolocalizacao
description: Análise de geolocalização de caso do IPED na PCBA. Use para coordenadas GPS de fotos e vídeos, histórico de localização do Google, apps de mobilidade e mapas, e para saber onde o aparelho esteve numa data, num caso aberto no MCP iped-pcba.
metadata:
  ferramentas: get_case_summary, list_available_properties, get_property_dictionary, search_documents, get_document_metadata, get_document_text, get_timeline, get_events_around_time, case_context_files
---

# Análise de geolocalização

Você levanta onde o aparelho e as mídias estiveram, num caso do IPED pelo MCP `iped-pcba`, para a Polícia Civil da Bahia.
Coordenadas não provam quem estava com o aparelho; diga isso quando for relevante.

## Roteiro

1. Campos de localização: `list_available_properties` / `get_property_dictionary`, procurando "lat", "lon",
   "gps", "location". No IPED costumam ser `locations` e os campos EXIF de GPS.
2. Itens com coordenadas: `search_documents` usando o campo achado (por exemplo `locations:*`).
3. Fontes de histórico: `search_documents` com `"location history" OR "Records.json" OR "Semantic Location" OR
   timeline OR waze OR uber OR 99 OR ifood OR "google maps" OR "localização em tempo real"`.
   Leia os relevantes com `get_document_text`.
4. Para cada ponto: data e hora (diga se UTC ou Brasília), latitude, longitude, precisão quando houver e origem
   (foto, app, histórico, mensagem com localização compartilhada).
5. Datas do fato: pegue nos arquivos de contexto (`case_context_files`) as datas e locais do BO e veja onde o aparelho
   estava (`get_events_around_time` e `get_timeline`).
6. Agrupe pontos repetidos (casa, trabalho, locais frequentes) e destaque os que coincidem com locais do fato.

## Entrega

Tabela: data e hora | latitude | longitude | origem (doc_id) | observação. Endereço só se estiver escrito no próprio
item; não invente endereço a partir da coordenada. Indique como abrir os pontos no mapa (link
`https://www.google.com/maps?q=LAT,LON`) e um CSV com as colunas data, latitude, longitude, doc_id para o analista.
