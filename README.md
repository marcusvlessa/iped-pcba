# IPED-PCBA

Instalação, autoconfiguração e extensões do [IPED](https://github.com/sepinf-inc/IPED) para a
Polícia Civil da Bahia. O núcleo do IPED não é alterado: tudo aqui atua sobre os arquivos de
configuração, perfis e scripts que o próprio IPED já prevê.

Este repositório segue o plano "Plano IPED + IA para a PCBA". Fases prontas: **1, instalador**,
**2, MCP com auditoria** (pasta [`mcp/`](mcp/README.md)) e o **Painel IPED-PCBA**, que conduz o
analista por todo o fluxo no navegador.

## Para quem é

Qualquer policial da PCBA com o IPED instalado, em qualquer pasta e em qualquer máquina. O
instalador não traz nada fixo de um computador: ele descobre onde está o IPED, que hardware a
máquina tem e o que já está instalado, e configura a partir disso.

## Instalar numa estação Windows

1. Baixe o `iped-pcba-windows.zip` da página de Releases e descompacte em qualquer pasta.
   (O "Download ZIP" do código também serve, mas sem o MCP, que precisa ser compilado.)
2. Dê dois cliques em `instalar.bat`. Ele acha o IPED e abre o **Painel IPED-PCBA** no navegador.
3. Siga os passos do painel.

Não precisa instalar Python nem nada: o painel usa o Python que vem dentro do IPED. A janela
preta do `instalar.bat` precisa ficar aberta enquanto o painel estiver em uso.

## Painel IPED-PCBA

Página local (só em `127.0.0.1`, com código de acesso aleatório na URL) com quatro passos:

| Passo | O que faz |
|---|---|
| 1. Máquina e configuração | Mostra o hardware e a configuração proposta, com o valor atual e o motivo de cada item. Dá para desmarcar ou editar qualquer valor antes de aplicar. Aplica com backup, restaura qualquer backup, instala o `faster-whisper` com um clique e cria um atalho do painel na Área de Trabalho. |
| 2. Processar evidências | Escolhe evidências (arquivos ou pastas), pasta do caso e perfil, e roda o IPED mostrando o log. Acrescentar a um caso, continuar processamento interrompido e caso portátil. O processamento continua se o painel for fechado. |
| 3. Casos | Lista os casos, abre no IPED, escolhe qual caso a IA vai ler e mostra o log de auditoria da IA com a conferência da cadeia de hashes. |
| 4. IA (MCP) | Liga e desliga a escrita da IA no caso, liga o MCP ao Claude Desktop, ao LM Studio e ao Hermes Agent (com cópia do arquivo antes de alterar), procura Ollama e LM Studio rodando na máquina e testa o MCP com o caso ativo. |

Depois de aplicar, o painel fica dentro do IPED: `<IPED>\pcba\painel-pcba.bat` abre de novo,
mesmo que a pasta baixada seja apagada. Pelo console: `python -m iped_pcba painel`.

O `instalar.bat -Texto` faz só a configuração pelo console, como antes (pergunta S/N).
Tudo o que o instalador escreve no console fica em `%TEMP%\iped-pcba-instalar.log`.

## O que a configuração faz

Nessa ordem:

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
5. **Mostra o plano** e só grava quando você manda, com backup em `<IPED>\pcba\backup\<data-hora>\`.
6. **Gera os perfis** `pcba-celular`, `pcba-computador`, `pcba-telematica` e `pcba-triagem`.
7. **Gera o lançador** `<IPED>\pcba\iped-pcba.bat` e grava `<IPED>\pcba\maquina.json` com o
   retrato da máquina e o que mudou.
8. **Instala o MCP** (IA) em `<IPED>\pcba\mcp\`, com o lançador `iped-pcba-mcp.bat` e o trecho
   de configuração para o Claude Desktop e o LM Studio. Com escrita liberada (a IA cria
   marcadores e comentários; desligue no painel ou com `--somente-leitura`) e com log de
   auditoria no próprio caso. Detalhes em [mcp/README.md](mcp/README.md).
9. **Instala o painel** em `<IPED>\pcba\app\` e o lançador `<IPED>\pcba\painel-pcba.bat`.

Opções do `scripts\instalar.ps1` (o `instalar.bat` repassa todas):

| Opção | Efeito |
|---|---|
| `-IpedRoot <pasta>` | usa esta instalação em vez de procurar |
| `-Temp <pasta>` | usa esta pasta temporária em vez de escolher |
| `-ServidorTranscricao IP:PORTA` | manda a transcrição para o servidor central |
| `-Texto` | configuração pelo console, sem o painel |
| `-Simular` | mostra o que mudaria, sem gravar |
| `-Aplicar` | aplica sem perguntar (implantação em lote, GPO) |
| `-Reverter` | desfaz a última aplicação (inclusive o MCP) |

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
cd mcp && mvn package          # depois de scripts/preparar-libs-iped.sh <IPED>
```

O GitHub Actions roda os testes no Windows (Python 3.9, o mesmo do IPED) e no Linux, compila o
MCP contra o código-fonte oficial do IPED 4.3.1 e gera os pacotes `iped-pcba-windows.zip` e
`iped-pcba-linux.tar.gz` com o Java 21 embutido. Uma tag `v*` publica os pacotes em Releases.

Os testes usam cópias dos arquivos de configuração reais do IPED 4.3.1 em
`tests/fixtures/iped-4.3.1` e verificam, entre outras coisas, que aplicar duas vezes não muda nada
na segunda e que reverter devolve os arquivos byte a byte.

## Regras do projeto

- Nenhum dado real de investigação entra neste repositório, em testes ou em prompts.
- IA local por padrão; Claude Desktop e Hermes Agent são opções do analista, não do instalador.
- Toda conclusão de IA passa por revisão humana antes de ir para um relatório.

## Próximas fases

3. Parsers de retornos de provedores e importador do Guardião (Dígitro).
4. Gerador de relatórios no padrão da 9ª COORPIN.

## Licença

GPLv3, a mesma do IPED.
