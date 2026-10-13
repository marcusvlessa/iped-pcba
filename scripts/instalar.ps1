<#
.SYNOPSIS
  Instalador IPED-PCBA para estações Windows.
.DESCRIPTION
  Usa o Python que já vem dentro do IPED (python\python.exe), então não é preciso
  instalar nada. Por padrão só DIAGNOSTICA. Para gravar, use -Aplicar.
  Toda gravação faz backup em <IPED>\pcba\backup\<data-hora>\ e pode ser desfeita com -Reverter.
.EXAMPLE
  .\instalar.ps1 -IpedRoot "C:\IPED\iped-4.3.1"
  .\instalar.ps1 -IpedRoot "C:\IPED\iped-4.3.1" -Temp "D:\IPEDTemp" -Aplicar -Simular
  .\instalar.ps1 -IpedRoot "C:\IPED\iped-4.3.1" -Temp "D:\IPEDTemp" -ServidorTranscricao 10.0.0.5:11111 -Aplicar
  .\instalar.ps1 -IpedRoot "C:\IPED\iped-4.3.1" -Reverter
#>
param(
  [Parameter(Mandatory=$true)][string]$IpedRoot,
  [string]$Temp = "",
  [string]$ServidorTranscricao = "",
  [switch]$SaidaSSD,
  [switch]$Aplicar,
  [switch]$Simular,
  [switch]$Reverter,
  [switch]$Json
)
$ErrorActionPreference = "Stop"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$pacote = Join-Path (Split-Path -Parent $aqui) "instalador"

$py = Join-Path $IpedRoot "python\python.exe"
if (-not (Test-Path $py)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $cmd) { Write-Error "Python nao encontrado em $py nem no PATH."; exit 1 }
  $py = $cmd.Source
}
$env:PYTHONIOENCODING = "utf-8"
# O Python embarcado do IPED tem python39._pth, que ignora PYTHONPATH;
# por isso o pacote entra no sys.path pelo próprio comando.
$boot = "import sys; sys.path.insert(0, r'$pacote'); from iped_pcba.cli import main; sys.exit(main())"

if ($Reverter) {
  & $py -c $boot reverter --iped $IpedRoot
  exit $LASTEXITCODE
}
$argsPy = @("-c", $boot, $(if ($Aplicar) { "aplicar" } else { "diagnosticar" }), "--iped", $IpedRoot, "--papel", "cliente")
if ($Temp) { $argsPy += @("--temp", $Temp) }
if ($ServidorTranscricao) { $argsPy += @("--servidor-transcricao", $ServidorTranscricao) }
if ($SaidaSSD) { $argsPy += "--saida-ssd" }
if ($Aplicar -and $Simular) { $argsPy += "--simular" }
if ($Json) { $argsPy += "--json" }
& $py @argsPy
exit $LASTEXITCODE
