<#
.SYNOPSIS
  Instalador IPED-PCBA para estações Windows.
.DESCRIPTION
  Acha o IPED na máquina e abre o Painel IPED-PCBA no navegador, que conduz o analista por
  todo o fluxo: configuração da máquina, processamento das evidências, casos e IA (MCP).
  Com -Texto, faz só a configuração aqui no console, perguntando antes de gravar.
  Usa o Python que já vem dentro do IPED (python\python.exe) ou o da máquina; quem acha o IPED e
  instala o que falta é o pacote iped_pcba, o mesmo que o painel usa.
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

# Este script só acha um Python e passa a palavra ao pacote iped_pcba, que localiza o IPED (versão mais
# nova primeiro), instala o que falta e conduz o resto. A lógica fica num lugar só, testada, em Python.

function Test-Python($exe) {
  if (-not $exe -or -not (Test-Path $exe)) { return $false }
  try { & $exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) }
  catch { return $false }
}

function Find-Python {
  # 1) o Python do IPED indicado ou registrado pelo próprio IPED; 2) Python da máquina (rápido);
  # 3) o Python de qualquer IPED nas pastas comuns (o IPED traz um em python\python.exe)
  $pastas = @()
  if ($IpedRoot) { $pastas += $IpedRoot }
  if ($env:IPED_ROOT) { $pastas += $env:IPED_ROOT }
  $declarado = Join-Path $env:USERPROFILE ".iped\ipedRoot.txt"
  if (Test-Path $declarado) { $pastas += (Get-Content $declarado -Raw).Trim().TrimStart([char]0xFEFF) }
  foreach ($p in $pastas) { $py = Join-Path $p "python\python.exe"; if (Test-Python $py) { return $py } }
  foreach ($nome in @("py", "python", "python3")) {
    $c = Get-Command $nome -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "*\WindowsApps\*") {  # o atalho da Microsoft Store não é Python
      if ($nome -eq "py") {
        try { $real = (& $c.Source -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1) } catch { $real = $null }
        if ($real -and (Test-Python $real.Trim())) { return $real.Trim() }
      } elseif (Test-Python $c.Source) { return $c.Source }
    }
  }
  Write-Host "Procurando o IPED nesta máquina (pode levar até um minuto)..." -ForegroundColor Cyan
  $bases = @($env:USERPROFILE, "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Downloads", "$env:USERPROFILE\Documents")
  foreach ($d in (Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -ne $null })) {
    $bases += @($d.Root, (Join-Path $d.Root "Tools"), (Join-Path $d.Root "Program Files"))
  }
  foreach ($b in $bases | Where-Object { $_ -and (Test-Path $_) }) {
    foreach ($jar in Get-ChildItem $b -Filter "iped.jar" -Recurse -Depth 3 -ErrorAction SilentlyContinue) {
      $py = Join-Path $jar.DirectoryName "python\python.exe"
      if (Test-Python $py) { return $py }
    }
  }
  return $null
}

# Máquina sem IPED e sem Python: baixa a última versão oficial do IPED (que traz o Python), conferindo o
# SHA-256 do GitHub. Com o IPED instalado, o resto (plugins, IA local, transcrição) é feito pelo painel.
function Install-Iped {
  $rel = Invoke-RestMethod "https://api.github.com/repos/sepinf-inc/IPED/releases/latest" -Headers @{ "User-Agent" = "iped-pcba" }
  $a = $rel.assets | Where-Object { $_.name -like "*_and_java_plugins.zip" } | Select-Object -First 1
  if (-not $a) { throw "Pacote do IPED não encontrado na última versão publicada ($($rel.tag_name))." }
  $versao = $rel.tag_name.TrimStart("vV")
  $d = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 3GB } |
    Sort-Object @{e={ if ($_.Name -eq "C") { $_.Free * 1.5 } else { $_.Free } }} -Descending | Select-Object -First 1
  if (-not $d) { throw "Nenhum disco com 3 GB livres para o IPED." }
  $destino = Join-Path $d.Root "Tools\IPED"
  $pasta = Join-Path $env:USERPROFILE ".iped-pcba\downloads"
  New-Item -ItemType Directory -Force -Path $pasta, $destino | Out-Null
  $zip = Join-Path $pasta $a.name
  if (-not ((Test-Path $zip) -and (Get-Item $zip).Length -eq $a.size)) {
    Write-Host ("Baixando {0} ({1} MB)..." -f $a.name, [int]($a.size / 1MB)) -ForegroundColor Cyan
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
$py = Find-Python
if (-not $py) {
  Write-Host "Nenhuma instalação do IPED (nem Python) encontrada nesta máquina." -ForegroundColor Yellow
  $resp = Read-Host "Baixar e instalar a última versão oficial do IPED agora (uns 700 MB)? (S/N)"
  if ($resp -notmatch '^[sS]') {
    Write-Host "Rode de novo com -IpedRoot <pasta do IPED> se ele estiver em outro lugar." -ForegroundColor Red
    exit 1
  }
  try { $IpedRoot = Install-Iped } catch { Write-Host ("Não consegui instalar o IPED: " + $_) -ForegroundColor Red; exit 1 }
  $py = Join-Path $IpedRoot "python\python.exe"
  Write-Host "No painel, em Configurar a máquina, use Instalar tudo que falta para a transcrição, a IA local e o resto." -ForegroundColor Cyan
}
# Sem -IpedRoot, o pacote acha o IPED sozinho (versão mais nova primeiro) e diz qual escolheu.
$iped = @()
if ($IpedRoot) { $iped = @("--iped", $IpedRoot) }
$env:PYTHONIOENCODING = "utf-8"
# O Python embarcado do IPED tem um arquivo ._pth que ignora PYTHONPATH;
# por isso o pacote entra no sys.path pelo próprio comando.
$boot = "import sys; sys.path.insert(0, r'$pacote'); from iped_pcba.cli import main; sys.exit(main())"

if ($modoPainel) {
  Write-Host ""
  Write-Host "Abrindo o Painel IPED-PCBA no navegador..." -ForegroundColor Cyan
  Write-Host "Deixe esta janela aberta enquanto usa o painel." -ForegroundColor Cyan
  try { Stop-Transcript | Out-Null } catch { }
  & $py -c $boot painel @iped
  exit $LASTEXITCODE
}

if ($Reverter) {
  & $py -c $boot reverter @iped
  exit $LASTEXITCODE
}

function Invoke-Instalador([string]$comando, [string[]]$extra) {
  $a = @("-c", $boot, $comando) + $iped + @("--papel", "cliente")
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
