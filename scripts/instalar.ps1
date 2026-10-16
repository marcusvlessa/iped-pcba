<#
.SYNOPSIS
  Instalador IPED-PCBA para estações Windows.
.DESCRIPTION
  Acha o IPED na máquina e abre o Painel IPED-PCBA no navegador, que conduz o analista por
  todo o fluxo: configuração da máquina, processamento das evidências, casos e IA (MCP).
  Com -Texto, faz só a configuração aqui no console, perguntando antes de gravar.
  Usa o Python que já vem dentro do IPED (python\python.exe); não instala nada.
  Toda gravação faz backup em <IPED>\pcba\backup\<data-hora>\ e pode ser desfeita com -Reverter.
.EXAMPLE
  .\instalar.ps1                                   # acha o IPED e abre o painel
  .\instalar.ps1 -Texto                            # configuração pelo console (S/N)
  .\instalar.ps1 -IpedRoot "D:\IPED\iped-4.3.1"    # usa esta instalação
  .\instalar.ps1 -ServidorTranscricao 10.0.0.5:11111
  .\instalar.ps1 -Aplicar                          # sem perguntar (implantação em lote)
  .\instalar.ps1 -Simular                          # mostra o que mudaria, arquivo por arquivo
  .\instalar.ps1 -Reverter                         # desfaz a última aplicação
#>
param(
  [string]$IpedRoot = "",
  [string]$Temp = "",
  [string]$ServidorTranscricao = "",
  [switch]$SaidaSSD,
  [switch]$Aplicar,
  [switch]$Simular,
  [switch]$Reverter,
  [switch]$Texto,
  [switch]$Json
)
$ErrorActionPreference = "Stop"
$logArq = Join-Path $env:TEMP "iped-pcba-instalar.log"
try { Start-Transcript -Path $logArq -Force | Out-Null } catch { }
trap {
  Write-Host ""
  Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Registro completo em $logArq" -ForegroundColor Yellow
  try { Stop-Transcript | Out-Null } catch { }
  exit 1
}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$pacote = Join-Path (Split-Path -Parent $aqui) "instalador"

function Get-IpedVersao($pasta) {
  $jar = Get-ChildItem (Join-Path $pasta "lib") -Filter "iped-engine-*.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($jar -and $jar.Name -match "iped-engine-([\d.]+)\.jar") { return [version]$Matches[1] }
  return [version]"0.0"
}

function Find-Iped {
  # 1) o que o próprio IPED registra; 2) pastas comuns até 3 níveis
  $achados = @()
  $declarado = Join-Path $env:USERPROFILE ".iped\ipedRoot.txt"
  $candidatos = @()
  $emUso = @()
  if ($env:IPED_ROOT) { $emUso += $env:IPED_ROOT }
  if (Test-Path $declarado) { $emUso += (Get-Content $declarado -Raw).Trim() }
  $emUso = @($emUso | Where-Object { $_ -and (Test-Path $_) } | ForEach-Object { (Resolve-Path $_).Path })
  $candidatos += $emUso
  $bases = @($env:USERPROFILE, "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Downloads", "$env:USERPROFILE\Documents")
  foreach ($d in (Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -ne $null })) {
    $bases += @($d.Root, (Join-Path $d.Root "Tools"), (Join-Path $d.Root "Program Files"))
  }
  foreach ($b in $bases | Where-Object { $_ -and (Test-Path $_) }) {
    Get-ChildItem $b -Filter "iped.jar" -Recurse -Depth 3 -ErrorAction SilentlyContinue |
      ForEach-Object { $candidatos += $_.DirectoryName }
  }
  foreach ($c in $candidatos | Select-Object -Unique) {
    if ((Test-Path (Join-Path $c "IPEDConfig.txt")) -and (Test-Path (Join-Path $c "iped.jar")) -and
        (Test-Path (Join-Path $c "python\python.exe"))) {
      $r = (Resolve-Path $c).Path
      $achados += [pscustomobject]@{ Raiz = $r; Versao = (Get-IpedVersao $c); EmUso = ($emUso -contains $r) }
    }
  }
  # versão mais nova primeiro; entre iguais, a que o IPED registrou como em uso
  return $achados | Sort-Object Raiz -Unique | Sort-Object @{e={$_.Versao};Descending=$true}, @{e={$_.EmUso};Descending=$true}
}

# Baixa o IPED oficial do GitHub, confere o SHA-256 informado pelo GitHub e extrai. Devolve a raiz.
function Install-Iped {
  $versao = "4.3.1"
  $nome = "IPED-${versao}_and_java_plugins.zip"
  $destino = "C:\Tools\IPED"
  $livre = (Get-PSDrive C).Free
  if ($livre -lt 3GB) {
    $d = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 3GB } | Sort-Object Free -Descending | Select-Object -First 1
    if (-not $d) { throw "Nenhum disco com 3 GB livres para o IPED." }
    $destino = Join-Path $d.Root "Tools\IPED"
  }
  $rel = Invoke-RestMethod "https://api.github.com/repos/sepinf-inc/IPED/releases/tags/$versao" -Headers @{ "User-Agent" = "iped-pcba" }
  $a = $rel.assets | Where-Object { $_.name -eq $nome } | Select-Object -First 1
  if (-not $a) { throw "Arquivo $nome não encontrado na página do IPED." }
  $pasta = Join-Path $env:USERPROFILE ".iped-pcba\downloads"
  New-Item -ItemType Directory -Force -Path $pasta, $destino | Out-Null
  $zip = Join-Path $pasta $nome
  if (-not ((Test-Path $zip) -and (Get-Item $zip).Length -eq $a.size)) {
    Write-Host ("Baixando {0} ({1} MB)..." -f $nome, [int]($a.size / 1MB)) -ForegroundColor Cyan
    try { Start-BitsTransfer -Source $a.browser_download_url -Destination $zip -DisplayName "IPED $versao" }
    catch { Invoke-WebRequest $a.browser_download_url -OutFile $zip -UseBasicParsing }
  }
  if ($a.digest -like "sha256:*") {
    Write-Host "Conferindo SHA-256..." -ForegroundColor Cyan
    $h = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if ($h -ne $a.digest.Substring(7).ToLower()) { Remove-Item $zip; throw "SHA-256 não confere; o arquivo foi apagado. Rode de novo." }
    Write-Host "SHA-256 confere: $h" -ForegroundColor Green
  }
  Write-Host "Extraindo em $destino (alguns minutos)..." -ForegroundColor Cyan
  $tar = Join-Path $env:SystemRoot "System32\tar.exe"
  if (Test-Path $tar) { & $tar -xf $zip -C $destino } else { Expand-Archive $zip -DestinationPath $destino -Force }
  $raiz = Join-Path $destino "iped-$versao"
  if (-not (Test-Path (Join-Path $raiz "iped.jar"))) { throw "A extração não trouxe $raiz\iped.jar." }
  Write-Host "IPED $versao instalado em $raiz" -ForegroundColor Green
  return $raiz
}

$modoPainel = -not ($Texto -or $Aplicar -or $Simular -or $Reverter -or $Json)
if (-not $IpedRoot) {
  Write-Host "Procurando o IPED nesta máquina (pode levar até um minuto)..." -ForegroundColor Cyan
  $lista = @(Find-Iped)
  if ($lista.Count -eq 0) {
    Write-Host "Nenhuma instalação do IPED encontrada." -ForegroundColor Yellow
    $resp = Read-Host "Baixar e instalar o IPED 4.3.1 oficial agora (uns 700 MB)? (S/N)"
    if ($resp -notmatch '^[sS]') {
      Write-Host "Rode de novo com -IpedRoot <pasta do IPED> se ele estiver em outro lugar." -ForegroundColor Red
      exit 1
    }
    try { $novo = Install-Iped } catch { Write-Host ("Não consegui instalar o IPED: " + $_) -ForegroundColor Red; exit 1 }
    $lista = @([pscustomobject]@{ Raiz = $novo; Versao = "4.3.1"; EmUso = $true })
    Write-Host "No painel, em Configurar a máquina, use Instalar tudo que falta para a transcrição, a IA local e o resto." -ForegroundColor Cyan
  }
  $IpedRoot = $lista[0].Raiz
  Write-Host ("IPED {0} em {1}" -f $lista[0].Versao, $IpedRoot) -ForegroundColor Green
  foreach ($o in $lista | Select-Object -Skip 1) { Write-Host ("  outra instalação ignorada: {0} ({1})" -f $o.Raiz, $o.Versao) }
}

$py = Join-Path $IpedRoot "python\python.exe"
if (-not (Test-Path $py)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $cmd) { Write-Error "Python não encontrado em $py nem no PATH."; exit 1 }
  $py = $cmd.Source
}
$env:PYTHONIOENCODING = "utf-8"
# O Python embarcado do IPED tem um arquivo ._pth que ignora PYTHONPATH;
# por isso o pacote entra no sys.path pelo próprio comando.
$boot = "import sys; sys.path.insert(0, r'$pacote'); from iped_pcba.cli import main; sys.exit(main())"

if ($modoPainel) {
  Write-Host ""
  Write-Host "Abrindo o Painel IPED-PCBA no navegador..." -ForegroundColor Cyan
  Write-Host "Deixe esta janela aberta enquanto usa o painel." -ForegroundColor Cyan
  try { Stop-Transcript | Out-Null } catch { }
  & $py -c $boot painel --iped $IpedRoot
  exit $LASTEXITCODE
}

if ($Reverter) {
  & $py -c $boot reverter --iped $IpedRoot
  exit $LASTEXITCODE
}

function Invoke-Instalador([string]$comando, [string[]]$extra) {
  $a = @("-c", $boot, $comando, "--iped", $IpedRoot, "--papel", "cliente")
  if ($Temp) { $a += @("--temp", $Temp) }
  if ($ServidorTranscricao) { $a += @("--servidor-transcricao", $ServidorTranscricao) }
  if ($SaidaSSD) { $a += "--saida-ssd" }
  if ($Json) { $a += "--json" }
  $a += $extra
  & $py @a | Out-Host
  return $LASTEXITCODE
}

if ($Simular) { exit (Invoke-Instalador "aplicar" @("--simular")) }
if ($Aplicar) { exit (Invoke-Instalador "aplicar" @()) }

$rc = Invoke-Instalador "diagnosticar" @()
if ($rc -ne 0) { exit $rc }
Write-Host ""
$resp = Read-Host "Aplicar estas configurações? Um backup é feito antes. (S/N)"
if ($resp -match '^[sS]') { exit (Invoke-Instalador "aplicar" @()) }
Write-Host "Nada foi alterado."
exit 0
