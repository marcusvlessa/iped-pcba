<#
.SYNOPSIS
  Prepara o Python embarcado do IPED para transcricao Whisper em GPU (CUDA 12 + cuDNN 8).
.DESCRIPTION
  Modo HIBRIDO COM CONFIRMACAO: por padrao roda em -DryRun (so mostra o que faria).
  Com -Execute, realiza: get-pip, instalacao de gputil/faster-whisper, pin estavel
  (numpy<2, ctranslate2==4.4.0, setuptools<81) e download/extracao das 4 DLLs cuBLAS+cuDNN
  do Purfview para a pasta python do IPED.
  Pre-requisitos NAO automatizados (faca antes): Visual C++ Redistributable x64 e driver CUDA 12.x.
  NAO edita AudioTranscriptConfig.txt (use editar_config.ps1 para device=gpu etc.).
.PARAMETER IpedRoot
  Caminho do IPED (ex.: C:\IPED\iped-4.3.0).
.PARAMETER WhisperX
  Tambem instala o whisperx (fork do IPED) para batchSize>1. Requer FFmpeg no PATH.
.PARAMETER Execute
  Executa de fato. Sem este switch, roda em modo simulacao (DryRun).
.EXAMPLE
  .\setup_whisper_gpu.ps1 -IpedRoot "C:\IPED\iped-4.3.0"            # simulacao
  .\setup_whisper_gpu.ps1 -IpedRoot "C:\IPED\iped-4.3.0" -Execute  # executa
#>
param(
  [Parameter(Mandatory=$true)][string]$IpedRoot,
  [switch]$WhisperX,
  [switch]$Execute
)

$ErrorActionPreference = "Stop"
$py  = Join-Path $IpedRoot "python\python.exe"
$pyDir = Join-Path $IpedRoot "python"
$libsUrl = "https://github.com/Purfview/whisper-standalone-win/releases/download/libs/cuBLAS.and.cuDNN_CUDA12_win_v1.7z"
$libsName = "cuBLAS.and.cuDNN_CUDA12_win_v1.7z"

if(-not (Test-Path $py)){ Write-Error "Python embarcado nao encontrado em $py"; exit 1 }

function Step($n,$desc){ Write-Host ""; Write-Host "[$n] $desc" -ForegroundColor Cyan }
# Roda um programa pelo operador & (sem Invoke-Expression) e para com erro se ele falhar.
function Run([string]$exe, [string[]]$argumentos){
  Write-Host ("    > {0} {1}" -f $exe, ($argumentos -join " ")) -ForegroundColor DarkGray
  if($Execute){
    & $exe @argumentos
    if($LASTEXITCODE -ne 0){ Write-Error "Falhou (codigo $LASTEXITCODE): $exe"; exit 1 }
  }
}

Write-Host "==== Setup Whisper GPU para IPED ====" -ForegroundColor Cyan
Write-Host "IPED_ROOT : $IpedRoot"
$modo = if($Execute){ 'EXECUTAR' } else { 'SIMULACAO (use -Execute para aplicar)' }
Write-Host "Modo      : $modo" -ForegroundColor Yellow
Write-Host "Pre-req manuais: Visual C++ Redistributable x64 e driver CUDA 12.x instalados e reiniciado."

Step 1 "Garantir pip no Python embarcado"
$getpip = Join-Path $pyDir "get-pip.py"
if(Test-Path $getpip){ Run $py @($getpip) }
else { Write-Host "    get-pip.py nao encontrado; se pip ja existe, ok. Senao baixe get-pip.py para $pyDir" -ForegroundColor Yellow }

Step 2 "Instalar gputil + faster-whisper"
Run $py @("-m", "pip", "install", "gputil", "faster-whisper")

Step 3 "Pin estavel para CUDA12 + cuDNN8"
Run $py @("-m", "pip", "install", "--force-reinstall", "numpy<2", "ctranslate2==4.4.0", "setuptools<81")

if($WhisperX){
  Step "3b" "Instalar whisperx (fork IPED) para batchSize>1 (requer FFmpeg no PATH)"
  Run $py @("-m", "pip", "install", "git+https://github.com/sepinf-inc/whisperx.git@multi-audio")
}

Step 4 "Baixar DLLs cuBLAS+cuDNN (CUDA12) do Purfview"
$dest = Join-Path $env:TEMP $libsName
Write-Host "    URL    : $libsUrl"
Write-Host "    Destino: $dest"
if($Execute){
  Invoke-WebRequest -Uri $libsUrl -OutFile $dest
  Write-Host "    Download concluido." -ForegroundColor Green
  # SHA-256: quando o GitHub informa o resumo do arquivo da release, o download e conferido.
  $esperado = $null
  try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/Purfview/whisper-standalone-win/releases/tags/libs" -Headers @{ "User-Agent" = "iped-pcba" }
    $asset = $rel.assets | Where-Object { $_.name -eq $libsName } | Select-Object -First 1
    if($asset -and $asset.digest -like "sha256:*"){ $esperado = $asset.digest.Substring(7).ToLower() }
  } catch { Write-Host "    Nao consegui consultar o SHA-256 no GitHub: $($_.Exception.Message)" -ForegroundColor Yellow }
  if($esperado){
    $obtido = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
    if($obtido -ne $esperado){ Remove-Item $dest -Force; Write-Error "SHA-256 nao confere ($obtido <> $esperado). Arquivo apagado."; exit 1 }
    Write-Host "    SHA-256 conferido: $obtido" -ForegroundColor Green
  } else {
    Write-Host "    O GitHub nao informou o SHA-256 deste arquivo; seguindo sem conferir." -ForegroundColor Yellow
  }
}

Step 5 "Extrair as DLLs para $pyDir"
if($Execute){
  $seven = Get-Command 7z.exe -ErrorAction SilentlyContinue
  if(-not $seven){ $seven = Get-Command (Join-Path $env:ProgramFiles "7-Zip\7z.exe") -ErrorAction SilentlyContinue }
  if($seven){
    Run $seven.Source @("e", $dest, "-o$pyDir", "-y", "*.dll", "-r")
  } else {
    # Windows 10/11 trazem o tar.exe (bsdtar), que le .7z
    $tmpDir = Join-Path $env:TEMP "iped-pcba-cuda"
    if(Test-Path $tmpDir){ Remove-Item $tmpDir -Recurse -Force }
    New-Item -ItemType Directory $tmpDir | Out-Null
    $tar = Join-Path $env:SystemRoot "System32\tar.exe"
    if(-not (Test-Path $tar)){ Write-Error "Nem 7-Zip nem tar.exe nesta maquina. Instale o 7-Zip e rode de novo."; exit 1 }
    & $tar -xf $dest -C $tmpDir
    if($LASTEXITCODE -ne 0){ Write-Error "O tar.exe nao conseguiu abrir $dest. Instale o 7-Zip e rode de novo."; exit 1 }
    Get-ChildItem $tmpDir -Recurse -Filter *.dll | Copy-Item -Destination $pyDir -Force
    Remove-Item $tmpDir -Recurse -Force
  }
  $cublas = Get-ChildItem $pyDir -Filter "cublas64_*.dll" -ErrorAction SilentlyContinue
  $cudnn = Get-ChildItem $pyDir -Filter "cudnn*.dll" -ErrorAction SilentlyContinue
  if(-not $cublas -or -not $cudnn){
    Write-Error "As DLLs do CUDA (cublas64_*.dll e cudnn*.dll) nao apareceram em $pyDir. A GPU NAO foi configurada."
    exit 1
  }
  Write-Host ("    DLLs prontas: {0}" -f ((@($cublas) + @($cudnn) | ForEach-Object Name) -join ", ")) -ForegroundColor Green
} else {
  Write-Host "    (simulacao) extrairia $libsName para $pyDir" -ForegroundColor DarkGray
}

Step 6 "Configuracao (o instalador IPED-PCBA ja faz isto ao detectar a GPU)"
Write-Host "    Em conf/AudioTranscriptConfig.txt:"
Write-Host "      - ativar implementationClass = iped.engine.task.transcript.WhisperTranscriptTask"
Write-Host "      - whisperModel = medium   (ou large-v3 se VRAM>=10GB)"
Write-Host "      - device = gpu"
Write-Host "      - precision = float16"
if($WhisperX){ Write-Host "      - batchSize = 16 (whisperx)" }
Write-Host "    Validar: rode o IPED com o perfil pcba-celular num audio de teste"

Write-Host ""
if(-not $Execute){ Write-Host "Simulacao concluida. Reexecute com -Execute para aplicar." -ForegroundColor Yellow }
else { Write-Host "Setup concluido. Faca a validacao e configure o AudioTranscriptConfig.txt." -ForegroundColor Green }
