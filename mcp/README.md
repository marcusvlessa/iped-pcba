# MCP do IPED para a PCBA

Fork do [iped-tools-mcp](https://github.com/thiagofuer/iped-tools-mcp) (GPLv3), versão 1.0.1
(commit `bc651224`). O texto original está em [README-UPSTREAM.md](README-UPSTREAM.md).

O MCP deixa uma IA (Claude Desktop, LM Studio, Ollama via cliente MCP, Hermes Agent) consultar um
caso processado pelo IPED: buscar, ler textos, ver linha do tempo, contatos, categorias. O que
este fork muda:

| | Original | PCBA |
|---|---|---|
| Versão do IPED | 4.4.0-SNAPSHOT (desenvolvimento) | a instalada na máquina (4.3.1) |
| Bibliotecas do IPED | dentro do executável | lidas de `<IPED>/lib` em execução |
| Auditoria | não tem | cada chamada da IA registrada, com cadeia de hashes |
| Escrita no caso | liberada | controlada pelo painel; bloqueada se o MCP for iniciado sem `--permitir-escrita` |
| Ferramentas de marcadores | criar e marcar itens | também marcar resultados de busca, comentar e desmarcar |
| Transporte | só STDIO | STDIO e HTTP com token |

## Instalação

O instalador da raiz do repositório (`instalar.bat`) já instala o MCP quando encontra o pacote:
copia para `<IPED>\pcba\mcp\`, gera o lançador `iped-pcba-mcp.bat` e o arquivo
`config-clientes-ia.json` com o trecho para colar na configuração do Claude Desktop ou do
LM Studio.

O pacote vem da página de Releases (pasta `mcp-dist`, com o Java 21 embutido). O IPED 4.3 traz
Java 11, que não serve para o MCP.

### Claude Desktop / LM Studio

Acrescente ao `claude_desktop_config.json` (ou ao `mcp.json` do LM Studio):

```json
{
  "mcpServers": {
    "iped-pcba": {
      "command": "C:\\caminho\\do\\IPED\\pcba\\mcp\\iped-pcba-mcp.bat",
      "args": ["--case", "D:\\Casos\\caso-x"]
    }
  }
}
```

Sem `--case`, a IA abre o caso com a ferramenta `open_case`.

### Hermes Agent

No `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  iped-pcba:
    command: "/opt/iped/pcba/mcp/iped-pcba-mcp.sh"
    args: ["--case", "/casos/caso-x"]
```

### Servidor Linux central (HTTP)

```bash
export PCBA_MCP_TOKEN="$(openssl rand -hex 32)"
<IPED>/pcba/mcp/iped-pcba-mcp.sh --http --host 0.0.0.0 --porta 8765 --case /casos/caso-x
```

O endpoint é `http://servidor:8765/mcp` e toda requisição precisa do cabeçalho
`Authorization: Bearer <token>`. Sem `PCBA_MCP_TOKEN` o servidor só aceita escutar em
`127.0.0.1`; pedir outro endereço sem token faz o MCP recusar a subida. Uma instância atende um
caso por vez.

No Linux o IPED exige `tskJarPath` no `LocalConfig.txt` para abrir casos; o instalador avisa se
estiver faltando.

## Auditoria

Cada chamada de ferramenta vira uma linha JSON em
`<caso>\iped-pcba-auditoria\mcp-auditoria.jsonl` (ou em `~/.iped-pcba/auditoria/` se a pasta do
caso não aceitar gravação, ou na pasta de `PCBA_AUDITORIA_PASTA`):

```json
{"seq":4,"ts":"2026-10-13T15:03:41Z","sessao":"…","usuario":"PCIVIL","maquina":"DESKTOP-X",
 "transporte":"stdio","caso":"D:\\Casos\\caso-x","ferramenta":"search_documents",
 "argumentos":{"query":"pix","limit":30},"situacao":"ok","resposta_bytes":171,
 "resposta_sha256":"…","duracao_ms":47,"anterior":"<hash da linha 3>","hash":"…"}
```

`situacao` é `ok`, `erro` ou `bloqueado`. O texto da resposta não é gravado, só o tamanho e o
SHA-256; para gravar também o texto, use `-Dpcba.auditoria.guardar-respostas=true`.

As linhas são encadeadas: `hash = sha256(anterior + linha sem o hash)`. Apagar, inserir ou alterar
uma linha quebra a cadeia. Para conferir:

```bash
python -m iped_pcba.auditoria "D:\Casos\caso-x\iped-pcba-auditoria\mcp-auditoria.jsonl"
```

(rode de dentro da pasta `instalador`, ou com o Python do IPED como no `instalar.ps1`).

Se o log não puder ser gravado, a resposta não é entregue à IA.

## Escrita no caso

Ferramentas que alteram o caso:

| Ferramenta | O que faz |
|---|---|
| `add_to_bookmark` | põe itens num marcador (cria o marcador se não existir) |
| `bookmark_search_results` | marca de uma vez os resultados de uma busca (até 5000 itens) |
| `set_bookmark_comment` | grava o comentário do marcador (o porquê e a busca usada) e se ele entra no relatório |
| `remove_from_bookmark` | tira itens de um marcador |
| `set_item_checked` | marca ou desmarca a seleção do item |
| `update_report_field` | escreve um campo de texto do rascunho do relatório técnico do caso |
| `update_report_analysis` | cria ou atualiza a análise de um provedor no rascunho do relatório |

`get_report_draft` (leitura) devolve o rascunho do RT, as lacunas `[ENTRE COLCHETES]` e os campos
que a IA pode escrever. O rascunho é o mesmo arquivo que o painel edita
(`<caso>/iped-pcba-relatorio/rt.json`); cada campo escrito pela IA fica em `ia_editou` e o painel
pede revisão. O `.docx` é gerado pelo analista no painel.

O MCP sozinho começa em somente leitura: a IA não vê essas ferramentas e, se chamar mesmo assim,
a chamada é recusada e registrada como `bloqueado`. O lançador gerado pelo instalador passa
`--permitir-escrita` quando existe o arquivo `escrita-ativa.txt` na pasta do MCP; o painel cria e
apaga esse arquivo (passo 4, "Permitir escrita no caso"). A instalação já vem com a escrita
liberada; para instalar sem, use `--somente-leitura` no `aplicar`.

Os marcadores ficam no próprio caso (`iped/bookmarks.iped`) e aparecem no IPED. Se o caso estiver
aberto no IPED enquanto a IA marca, feche e abra o caso de novo depois, para o IPED não gravar por
cima.

## Caso ativo

Sem `--case`, o MCP lê o caso indicado em `~/.iped-tools-mcp/active_case.txt` e troca de caso
sozinho quando o arquivo muda. O botão "Usar com a IA" do painel grava esse arquivo.

## Compilar

```bash
bash scripts/preparar-libs-iped.sh <pasta do IPED>        # ou scripts\preparar-libs-iped.ps1
mvn package
```

O primeiro comando instala no Maven local as bibliotecas do próprio IPED instalado. O GitHub
Actions faz o mesmo a partir do código-fonte oficial do IPED 4.3.1 e gera os pacotes.

Para rodar sem o instalador:

```bash
java --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED \
  -Dstdout.encoding=UTF-8 -cp "target/iped-tools-mcp-1.0.1-runner.jar:<IPED>/lib/*" \
  br.com.ipedtools.mcp.McpApplication --stdio --case <caso>
```

O lançador gerado pelo instalador traz a lista completa de `--add-opens`.
