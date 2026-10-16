# Skills de análise do IPED-PCBA

Cada pasta é uma skill no formato aberto `SKILL.md` (Agent Skills). Elas usam as ferramentas do MCP do IPED
(`iped-pcba`) e os arquivos de contexto do caso (`case_context_files`).

| Skill | Para quê |
|---|---|
| `analise-financeira` | PDFs, extratos, comprovantes PIX, SIMBA, RIF do COAF e planilhas: transações, contrapartes e sinais de lavagem |
| `analise-imagens` | Fotos, prints, documentos fotografados, OCR, QR codes, imagens e rostos semelhantes |
| `analise-audio` | Áudios e transcrições: quem fala, quando e sobre o quê |
| `analise-geolocalizacao` | Coordenadas de fotos, históricos de localização e apps de mobilidade |
| `analise-midias-x-logs` | Confere nos logs do aparelho quando e como cada mídia foi gerada |
| `analise-forense-completa` | Orquestra todas as outras e monta a análise completa do caso |

## Instalação

O painel instala sozinho (tela **Conectar IA > Skills de análise**):

- **IA local (Ollama, LM Studio)**: as skills aparecem como agentes no Assistente de IA, sem instalar nada.
- **Claude Code**: copia para `~/.claude/skills/`.
- **Hermes Agent**: copia para `~/.hermes/skills/iped-pcba/`.
- **Claude Desktop e claude.ai**: o painel gera um `.zip` por skill; envie em Configurações > Capacidades > Skills.

Pelo terminal: `python -m iped_pcba skills --instalar`.

As regras da PCBATech valem para todas: IA local para dados de investigação, a IA aponta indícios e quem conclui
é o analista, e todo texto da IA é revisado antes de entrar no relatório.
