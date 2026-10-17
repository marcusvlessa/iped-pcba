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

No painel, tela **1. Configurar a máquina > Skills de análise**, botão **Instalar e atualizar as skills**:

- **IA local (Ollama, LM Studio)**: cada skill vira um agente do **Assistente de IA**, sem instalar nada.
- **Claude Code**: copia as pastas para `~/.claude/skills/`.
- **Hermes Agent**: copia as pastas para `~/.hermes/skills/iped-pcba/`.
- **Claude Desktop e claude.ai**: as skills ficam na conta Claude, não numa pasta do PC. O painel gera um `.zip`
  por skill em `skills-zip/` e você envia cada um uma vez em **Personalizar > Skills > +** (em algumas versões:
  Configurações > Capacidades > Skills). O botão **Mostrar o .zip** abre a pasta com o arquivo selecionado.

Se uma skill já instalada estiver diferente, a versão anterior é guardada em `~/.iped-pcba/backup-skills/` antes
de ser trocada.

Pelo terminal: `python -m iped_pcba skills --instalar`.

As regras da PCBATech valem para todas: IA local para dados de investigação, a IA aponta indícios e quem conclui
é o analista, e todo texto da IA é revisado antes de entrar no relatório.
