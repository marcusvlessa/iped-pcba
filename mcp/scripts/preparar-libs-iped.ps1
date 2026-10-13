<#
.SYNOPSIS
  Instala no repositório Maven local as bibliotecas do IPED usadas na compilação do MCP.
.EXAMPLE
  .\scripts\preparar-libs-iped.ps1 -IpedRoot "C:\Tools\iped-4.3.1\iped-4.3.1"
#>
param([Parameter(Mandatory=$true)][string]$IpedRoot, [string]$Versao = "")
$ErrorActionPreference = "Stop"
$lib = Join-Path $IpedRoot "lib"
if (-not (Test-Path $lib)) { throw "Pasta $lib não existe." }
if (-not $Versao) {
  $jar = Get-ChildItem $lib -Filter "iped-engine-*.jar" | Select-Object -First 1
  if (-not $jar -or $jar.Name -notmatch "iped-engine-([\d.]+)\.jar") { throw "Não achei iped-engine-*.jar em $lib." }
  $Versao = $Matches[1]
}
foreach ($a in "iped-api","iped-engine","iped-utils","iped-parsers-impl","iped-viewers-api","iped-carvers-api") {
  $f = Join-Path $lib "$a-$Versao.jar"
  if (-not (Test-Path $f)) { throw "Falta $f" }
  & mvn -q install:install-file "-Dfile=$f" "-DgroupId=iped" "-DartifactId=$a" "-Dversion=$Versao" "-Dpackaging=jar" "-DgeneratePom=true"
  if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar $a" }
  Write-Host "instalado $a $Versao"
}
Write-Host "Pronto. Compile com: mvn package -Diped.version=$Versao"
