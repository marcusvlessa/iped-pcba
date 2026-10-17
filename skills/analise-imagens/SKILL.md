---
name: analise-imagens
description: Análise de imagens de caso do IPED na PCBA. Use para fotos, prints de tela, documentos fotografados, armas, drogas, dinheiro, veículos, OCR, QR codes, imagens e rostos semelhantes num caso aberto no MCP iped-pcba.
metadata:
  ferramentas: get_case_summary, list_categories, search_documents, get_document_metadata, get_document_text, get_item_thumbnail, search_similar_images, search_similar_faces, list_ai_filters, query_ai_detections, get_item_relations, get_device_and_owner_info, get_events_around_time, case_context_files, bookmark_search_results
---

# Análise de imagens

Você analisa as imagens de um caso do IPED pelo MCP `iped-pcba`, para a Polícia Civil da Bahia. Cite o doc_id, o caminho
e a data de cada imagem. Descreva o que vê sem juízo de culpa; quem conclui é o analista.

## Roteiro

1. `get_case_summary` e `list_categories`: quantas imagens e vídeos existem e em quais categorias.
2. `list_ai_filters` e `query_ai_detections`: o que o IPED já classificou (nudez, documentos, armas, rostos, OCR, QR code).
3. Texto dentro das imagens (OCR, ligado nos perfis Celular, Computador e Retorno de provedor):
   `search_documents` com nomes, placas, CPFs, chaves PIX e palavras do caso, filtrando pelas categorias de imagem.
   Documentos fotografados: `rg OR cpf OR cnh OR "carteira de identidade" OR boleto OR comprovante`.
4. QR codes: busque o conteúdo decodificado (links, PIX copia e cola, carteiras de cripto).
5. Para cada imagem relevante: `get_document_metadata` (EXIF: aparelho, data original, GPS) e `get_item_thumbnail`
   para ver a imagem. Diga o que aparece: pessoas, armas, drogas, dinheiro, veículos e placas, locais reconhecíveis.
6. Imagens semelhantes (`search_similar_images`) a partir das relevantes: versões, recortes, a mesma cena em outras pastas.
7. Rostos (`search_similar_faces`) a partir de uma foto do investigado ou de um alvo que o analista indicar.
8. Cruze com os arquivos de contexto (`case_context_files`): pessoas, veículos e locais citados no BO e nos depoimentos.

## Entrega

Tabela: doc_id | caminho | data (EXIF e do arquivo) | origem provável (câmera, WhatsApp, captura de tela, download) | o que mostra |
relevância. Depois um resumo em texto corrido e os pontos que o analista deve conferir no IPED. Se a escrita estiver
liberada, ofereça marcar as relevantes no marcador "Imagens relevantes".
