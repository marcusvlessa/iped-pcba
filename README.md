# IPED-PCBA

Instalação, autoconfiguração e extensões do [IPED](https://github.com/sepinf-inc/IPED) para a
Polícia Civil da Bahia. O núcleo do IPED não é alterado: tudo aqui atua sobre os arquivos de
configuração, perfis e scripts que o próprio IPED já prevê.

Este repositório segue o plano "Plano IPED + IA para a PCBA". Fase atual: **1, instalador**.

## Para quem é

Qualquer policial da PCBA com o IPED instalado, em qualquer pasta e em qualquer máquina. O
instalador não traz nada fixo de um computador: ele descobre onde está o IPED, que hardware a
máquina tem e o que já está instalado, e configura a partir disso.

## Instalar numa estação Windows

1. Baixe este repositório (Code, Download ZIP) e descompacte em qualquer pasta.
2. Dê dois cliques em `instalar.bat`.
3. Confira o plano que aparece na tela e responda `S` para aplicar.

Pronto. Não precisa instalar Python nem nada: o instalador usa o Python que vem dentro do IPED.

O que ele faz, nessa ordem:

1. **Acha o IPED**: primeiro o caminho que o próprio IPED registra em `~\.iped\ipedRoot.txt`,
   depois a variável `IPED_ROOT`, depois procura em todos os discos (raiz, `Tools`,
   `Program Files`, Área de Trabalho, Downloads, Documentos) até três níveis. Se houver mais de
   uma instalação, usa a de versão mais nova e lista as outras.
2. **Reconhece a máquina**: CPU, RAM, discos e espaço livre, SSD ou HDD, GPU NVIDIA com VRAM,
   driver e CUDA, versão do IPED e pacotes de IA no Python do IPED.
3. **Escolhe a pasta temporária**: o SSD fora do disco do sistema com mais espaço livre (mínimo
   50 GB); se não houver, o SSD do sistema; se não houver SSD, o disco com mais espaço.
4. **Monta o plano**, com o motivo de cada mudança:
   - `LocalConfig.txt`: `locale = pt-BR`, `indexTemp`, `indexTempOnSSD` só em SSD,
     `outputOnSSD`, `numThreads` limitado quando a RAM é curta;
   - `conf/HashTaskConfig.txt`: inclui SHA-256 (anexos do WhatsApp e cadeia de custódia);
   - `conf/AudioTranscriptConfig.txt`: Whisper em GPU (medium ou large-v3 conforme a VRAM),
     Whisper em CPU, transcrição no servidor central ou Vosk. Nunca liga o Whisper se o
     `faster-whisper` não estiver no Python do IPED, para não quebrar o processamento;
   - heap da JVM: 50% da RAM com teto de 30 GB.
5. **Pergunta** e só então grava, com backup em `<IPED>\pcba\backup\<data-hora>\`.
6. **Gera os perfis** `pcba-celular`, `pcba-computador`, `pcba-telematica` e `pcba-triagem`.
7. **Gera o lançador** `<IPED>\pcba\iped-pcba.bat` e grava `<IPED>\pcba\maquina.json` com o
   retrato da máquina e o que mudou.

Opções do `scripts\instalar.ps1` (o `instalar.bat` repassa todas):

| Opção | Efeito |
|---|---|
| `-IpedRoot <pasta>` | usa esta instalação em vez de procurar |
| `-Temp <pasta>` | usa esta pasta temporária em vez de escolher |
| `-ServidorTranscricao IP:PORTA` | manda a transcrição para o servidor central |
| `-Simular` | mostra o que mudaria, sem gravar |
| `-Aplicar` | aplica sem perguntar (implantação em lote, GPO) |
| `-Reverter` | desfaz a última aplicação |

Se o IPED estiver em `Program Files`, rode como administrador.

Depois de aplicado, para processar:

```bat
<pasta do IPED>\pcba\iped-pcba.bat pcba-celular <evidência> <pasta do caso>
```

## Instalar no servidor Linux central

```bash
bash scripts/instalar.sh <pasta do IPED> diagnosticar --papel servidor
bash scripts/instalar.sh <pasta do IPED> aplicar      --papel servidor
<pasta do IPED>/pcba/transcricao-servidor.sh 11111 11112   # descoberta + serviço de transcrição
```

As estações passam a usar o servidor com `instalar.bat -ServidorTranscricao IP-do-servidor:11111`.

### Whisper em GPU

- Windows: `scripts\\whisper_gpu.ps1 -IpedRoot <pasta do IPED>` (simula por padrão; `-Execute` aplica).
  Pré-requisitos manuais: Visual C++ Redistributable x64 e driver NVIDIA com CUDA 12.
- Linux: `pip install faster-whisper` no Python usado pelo IPED, com CUDA 12 e cuDNN do sistema.

Depois de instalar, rode o instalador de novo: ele passa a detectar o `faster-whisper` e liga o
Whisper.

## Perfis

| Perfil | Base | Para quê |
|---|---|---|
| `pcba-celular` | raiz | Extrações de celular. Transcrição, grafo, QR code, similaridade de imagens. |
| `pcba-computador` | forensic | Imagens de disco. Carving, transcrição, grafo. |
| `pcba-telematica` | raiz | Retornos de provedores. Expande pacotes, indexa conteúdo e regex, sem carving. |
| `pcba-triagem` | triage | Triagem em local de busca, sem transcrição. |

O IPED aplica a raiz e depois o perfil: o `IPEDConfig.txt` do perfil substitui o da raiz e cada
arquivo em `profiles/<perfil>/conf/` substitui o de mesmo nome em `conf/`. Por isso os perfis são
gerados como cópia completa da base com as chaves da PCBA por cima, e o que depende da máquina
(transcrição, hashes, temp) fica na raiz, valendo para todos os perfis.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes usam cópias dos arquivos de configuração reais do IPED 4.3.1 em
`tests/fixtures/iped-4.3.1` e verificam, entre outras coisas, que aplicar duas vezes não muda nada
na segunda e que reverter devolve os arquivos byte a byte.

## Regras do projeto

- Nenhum dado real de investigação entra neste repositório, em testes ou em prompts.
- IA local por padrão; Claude Desktop e Hermes Agent são opções do analista, não do instalador.
- Toda conclusão de IA passa por revisão humana antes de ir para um relatório.

## Próximas fases

2. Fork do `iped-tools-mcp` com log de auditoria, modo somente leitura e transporte HTTP.
3. Parsers de retornos de provedores e importador do Guardião (Dígitro).
4. Gerador de relatórios no padrão da 9ª COORPIN.

## Licença

GPLv3, a mesma do IPED.
