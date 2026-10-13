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

$modoPainel = -not ($Texto -or $Aplicar -or $Simular -or $Reverter -or $Json)
if (-not $IpedRoot) {
  Write-Host "Procurando o IPED nesta máquina (pode levar até um minuto)..." -ForegroundColor Cyan
  $lista = @(Find-Iped)
  if ($lista.Count -eq 0) {
    Write-Host "Nenhuma instalação do IPED encontrada. Rode de novo com -IpedRoot <pasta do IPED>." -ForegroundColor Red
    exit 1
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
