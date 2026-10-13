# IPED-PCBA

Instalação, autoconfiguração e extensões do [IPED](https://github.com/sepinf-inc/IPED) para a
Polícia Civil da Bahia. O núcleo do IPED não é alterado: tudo aqui atua sobre os arquivos de
configuração, perfis e scripts que o próprio IPED já prevê.

Este repositório segue o plano "Plano IPED + IA para a PCBA". Fase atual: **1, instalador**.

## O que a fase 1 entrega

`instalador/iped_pcba` é um pacote Python sem dependências externas (roda no Python que já vem
dentro do IPED no Windows, 3.9, e no `python3` do Linux). Ele:

1. **Reconhece a máquina**: CPU, RAM, discos (SSD ou HDD, e em qual letra), GPU NVIDIA, VRAM,
   driver e CUDA, versão do IPED, Python e Java embarcados, pacotes de IA instalados.
2. **Monta um plano** com motivo para cada mudança:
   - `LocalConfig.txt`: `locale = pt-BR`, `indexTemp`, `indexTempOnSSD` só se o temp estiver em
     SSD, `outputOnSSD`, `numThreads` limitado quando a RAM é curta;
   - `conf/HashTaskConfig.txt`: inclui SHA-256 (anexos do WhatsApp e cadeia de custódia);
   - `conf/AudioTranscriptConfig.txt`: Whisper em GPU (medium ou large-v3 conforme a VRAM),
     Whisper em CPU, transcrição remota no servidor central ou Vosk, conforme o hardware e o que
     está instalado. Nunca liga o Whisper se o `faster-whisper` não estiver no Python do IPED;
   - heap da JVM: 50% da RAM com teto de 30 GB, passado como `-Xmx` depois de `iped.jar`.
3. **Gera os perfis PCBA** em `profiles/`: `pcba-celular`, `pcba-computador` (base forensic),
   `pcba-telematica` e `pcba-triagem` (base triage).
4. **Gera lançadores** em `<IPED>/pcba/`: `iped-pcba.bat` (Windows) ou `iped-pcba.sh` (Linux) e,
   no servidor, `transcricao-servidor.sh` para a transcrição centralizada.
5. **Grava `pcba/maquina.json`** com o retrato da máquina, o plano e o que mudou.
6. **Faz backup de tudo** em `pcba/backup/<data-hora>/` e desfaz com `reverter`.

## Uso no Windows (estação do analista)

```powershell
# só olha e mostra o plano
.\scripts\instalar.ps1 -IpedRoot "C:\Tools\iped-4.3.1\iped-4.3.1" -Temp "E:\IPEDTemp"

# mostra o que mudaria, arquivo por arquivo, sem gravar
.\scripts\instalar.ps1 -IpedRoot "C:\Tools\iped-4.3.1\iped-4.3.1" -Temp "E:\IPEDTemp" -Aplicar -Simular

# aplica (com backup); com servidor central de transcrição
.\scripts\instalar.ps1 -IpedRoot "C:\Tools\iped-4.3.1\iped-4.3.1" -Temp "E:\IPEDTemp" -ServidorTranscricao 10.0.0.5:11111 -Aplicar

# desfaz a última aplicação
.\scripts\instalar.ps1 -IpedRoot "C:\Tools\iped-4.3.1\iped-4.3.1" -Reverter
```

Depois de aplicado, o processamento fica:

```bat
C:\Tools\iped-4.3.1\iped-4.3.1\pcba\iped-pcba.bat pcba-celular E:\extracoes\aparelho1.ufdr E:\casos\op-x\aparelho1
```

## Uso no Linux (servidor central)

```bash
bash scripts/instalar.sh /opt/iped-4.3.1 diagnosticar --papel servidor --temp /srv/ipedtemp
bash scripts/instalar.sh /opt/iped-4.3.1 aplicar      --papel servidor --temp /srv/ipedtemp
/opt/iped-4.3.1/pcba/transcricao-servidor.sh 11111 11112   # descoberta + serviço de transcrição
```

As estações apontam para `IP-do-servidor:11111` com `-ServidorTranscricao`.

### Whisper em GPU

- Windows: `scripts/whisper_gpu.ps1 -IpedRoot <pasta>` (simula por padrão; `-Execute` aplica).
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
