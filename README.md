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

Página local (só em `127.0.0.1`, com código de acesso aleatório na URL). O topo mostra o
**caso em análise**, escolhido uma vez e usado em todas as telas. A tela **Início** diz qual é o
próximo passo e mostra o andamento. O menu segue o trabalho:

| Grupo | Tela | O que faz |
|---|---|---|
| Preparar | 1. Configurar a máquina | Mostra o hardware e a configuração proposta, com o valor atual e o motivo de cada item. Dá para desmarcar ou editar qualquer valor antes de aplicar. Aplica com backup, restaura qualquer backup, instala o `faster-whisper` com um clique e cria um atalho do painel na Área de Trabalho. |
| Preparar | 2. Processar evidência | Escolhe evidências, pasta do caso e perfil (em cartões que explicam quando usar cada perfil, o que liga, o que desliga e quanto demora) e roda o IPED mostrando o log. |
| Analisar | 3. Casos | Lista os casos, abre no IPED, escolhe o caso em análise e mostra o log de auditoria da IA com a conferência da cadeia de hashes. |
| Analisar | Visão do caso | Gráficos, alertas e sugestões do caso (veja abaixo). |
| Analisar | Assistente de IA | Agentes prontos que mandam a pergunta à IA local pelo próprio painel (veja abaixo). |
| Concluir | 4. Relatório técnico | Monta o RT do caso no modelo da PCBA e gera o `.docx` (veja abaixo). |
| Sistema | Conexões de IA (MCP) | Liga e desliga a escrita da IA no caso, liga o MCP ao Claude Desktop, ao Antigravity, ao LM Studio e ao Hermes Agent (com cópia do arquivo antes de alterar), procura Ollama e LM Studio na máquina e testa o MCP com o caso ativo. |

### Assistente de IA

Oito agentes, cada um com seu papel, as ferramentas do MCP que pode usar e perguntas prontas:
Triagem inicial, Comunicações, Financeiro, Linha do tempo, Localização, Mídias e detecções,
Marcação no caso e Redator do RT (os dois últimos escrevem no caso e precisam da escrita
liberada). O texto entre `[COLCHETES]` numa pergunta é para trocar antes de enviar.

**Enviar para a IA local** manda a pergunta ao Ollama ou ao LM Studio desta máquina (o painel
recusa qualquer endereço que não seja `127.0.0.1` ou `localhost`). A IA consulta o caso pelo MCP
e o painel mostra cada passo; toda chamada fica no log de auditoria do caso. A resposta pode ser
copiada ou salva em `<caso>\iped-pcba-ia\conversas\`. O modelo precisa aceitar ferramentas
(por exemplo qwen2.5, qwen3, llama3.1 ou mistral-nemo).

**Copiar para Claude/Antigravity/Hermes** copia as instruções do agente e a pergunta para colar
no programa ligado ao MCP. Claude Desktop e Antigravity usam modelos na nuvem: o painel avisa
antes de ligá-los, e dados reais devem ficar na IA local.

Depois de aplicar, o painel fica dentro do IPED: `<IPED>\pcba\painel-pcba.bat` abre de novo,
mesmo que a pasta baixada seja apagada. Pelo console: `python -m iped_pcba painel`.

O `instalar.bat -Texto` faz só a configuração pelo console, como antes (pergunta S/N).
Tudo o que o instalador escreve no console fica em `%TEMP%\iped-pcba-instalar.log`.

## Visão do caso

O botão "Atualizar números do caso" roda o MCP em modo de exportação
(`iped-pcba-mcp --case <caso> --exportar-visao`), que só lê o índice do IPED e grava
`<caso>\iped-pcba-painel\visao.json`. Os registros telemáticos importados no passo 5 ficam em
`<caso>\iped-pcba-painel\telematica.json`. Nada sai da máquina e os gráficos funcionam sem
internet.

Alertas e sugestões são regras fixas, cada uma com a fonte do número; não são conclusões:

| Alerta | Quando aparece |
|---|---|
| Base de hashes de alerta, CSAM | qualquer item em `hashDb:status=alert` ou no filtro CSAM do IPED (nível alto) |
| Log de auditoria da IA adulterado | a cadeia de hashes do log não confere (nível alto) |
| Armas, drogas, carteiras de criptomoeda | filtros de IA do IPED com itens |
| Arquivos criptografados | categoria de criptografados com itens |
| Pico de atividade | mês acima de média + 2 desvios e de 3x a mediana dos meses |
| Apagados e carving | itens `deleted:true` e `carved:true` |
| Contato dominante | um contato com 35% ou mais das interações dos mais ativos |
| Madrugada | 25% ou mais dos registros telemáticos entre 0h e 6h |
| Conta em vários dispositivos | a mesma conta com mais de um dispositivo nos registros |
| RT escrito pela IA | campos marcados para revisão no rascunho |

As sugestões apontam o próximo passo (criar marcadores, transcrever áudios, ativar faces,
importar telemática, pedir cadastro de IPs, completar o RT, ligar a IA) e várias trazem uma
pergunta pronta para copiar e colar no programa de IA ligado ao MCP.

## Relatório técnico (RT)

O passo 5 do painel monta o RT na estrutura do modelo institucional: capa, bloco de qualificação,
apresentação, objetivo, fatos e relações, cadastro telefônico, terminais improdutivos, uma análise
por provedor (tabela INVESTIGADO | CONTA | PERÍODO, texto, quadros e conclusão), metodologia (IPED,
MD5, SHA-256), providências e assinaturas, com cabeçalho institucional e rodapé SIGILO LEGAL em
todas as páginas. O que estiver entre colchetes, `[ASSIM]`, sai em vermelho para o analista
completar, e o painel lista essas lacunas antes de gerar.

- O rascunho fica dentro do caso, em `<caso>\iped-pcba-relatorio\rt.json`, com cada versão anterior
  em `historico\`. O `.docx` sai em `<caso>\iped-pcba-relatorio\RT.docx`.
- Os dados da unidade (cabeçalho, endereço, sigla, núcleo, e-mails que entram em todo pedido e
  analistas padrão) são preenchidos uma vez no painel e ficam em `~\.iped-pcba\unidade.json`.
  Nada da unidade está fixo no código: cada delegacia preenche os seus.
- "Calcular SHA-256" faz o hash da `Lista de Arquivos.csv` exportada do IPED e o põe na metodologia.
- A IA pode escrever o rascunho pelo MCP (`get_report_draft`, `update_report_field`,
  `update_report_analysis`). Tudo o que ela escreve aparece no painel como "Escrito pela IA:
  revise". A conclusão de cada análise começa como lacuna: quem conclui é o analista.
- O `.docx` é gerado só com a biblioteca padrão do Python, então funciona com o Python que já vem
  no IPED, sem instalar nada.

Pelo console: `python -m iped_pcba relatorio gerar --caso <pasta>` (também `lacunas` e `telematica`).

### Registros telemáticos padronizados

Todo retorno de provedor vira o mesmo CSV (separador `;` ou `,`), um registro por linha:

| Coluna | Conteúdo |
|---|---|
| `provedor` | WhatsApp, Google, Apple, Meta, operadora… |
| `conta` | conta investigada (telefone, e-mail, ID) |
| `tipo` | `mensagem`, `chamada`, `conexao`, `login`, `localizacao`, `contato`, `grupo` ou `outro` |
| `data_hora` | ISO 8601 com fuso (`2026-03-01T13:05:00Z`); sem fuso é tratado como UTC |
| `interlocutor`, `direcao` | outra ponta da mensagem ou chamada, `enviada`/`recebida` |
| `ip`, `porta` | IP e porta lógica do registro de conexão |
| `dispositivo`, `grupo`, `duracao_s`, `local`, `fonte` | quando o provedor informa; `fonte` é o arquivo de origem |

"Importar e resumir" no passo 5 lê esse CSV e cria, por provedor, a tabela de contas, um texto de
rascunho em prosa (período em horário de Brasília, volume por tipo, principais interlocutores, IPs
mais recorrentes com portas, dispositivos, grupos e faixa horária) e os quadros de interlocutores e
de IPs. Análises que o analista já editou não são substituídas numa nova importação. Os conversores
de cada provedor para esse CSV são a fase 3. Exemplo com dados fictícios:
`tests/fixtures/telematica/registros_ficticios.csv`.

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

A tela Processar evidência explica cada perfil (quando usar, o que liga e desliga, tempo) e os
perfis do próprio IPED (`forensic`, `pedo`, `fastmode`, `triage`, `blind`).

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

3. Conversores dos retornos de provedores (WhatsApp, Google, Apple, Meta) para o CSV padronizado e
   importador do Guardião (Dígitro). Dependem de amostras anonimizadas.

## Licença

GPLv3, a mesma do IPED.
