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
$pip = Join-Path $IpedRoot "python\Scripts\pip.exe"
$pyDir = Join-Path $IpedRoot "python"
$libsUrl = "https://github.com/Purfview/whisper-standalone-win/releases/download/libs/cuBLAS.and.cuDNN_CUDA12_win_v1.7z"
$libsName = "cuBLAS.and.cuDNN_CUDA12_win_v1.7z"

if(-not (Test-Path $py)){ Write-Error "Python embarcado nao encontrado em $py"; exit 1 }

function Step($n,$desc){ Write-Host ""; Write-Host "[$n] $desc" -ForegroundColor Cyan }
function Run($cmd){
  Write-Host "    > $cmd" -ForegroundColor DarkGray
  if($Execute){ Invoke-Expression $cmd }
}

Write-Host "==== Setup Whisper GPU para IPED ====" -ForegroundColor Cyan
Write-Host "IPED_ROOT : $IpedRoot"
$modo = if($Execute){ 'EXECUTAR' } else { 'SIMULACAO (use -Execute para aplicar)' }
Write-Host "Modo      : $modo" -ForegroundColor Yellow
Write-Host "Pre-req manuais: Visual C++ Redistributable x64 e driver CUDA 12.x instalados e reiniciado."

Step 1 "Garantir pip no Python embarcado"
$getpip = Join-Path $pyDir "get-pip.py"
if(Test-Path $getpip){ Run "& `"$py`" `"$getpip`"" }
else { Write-Host "    get-pip.py nao encontrado; se pip ja existe, ok. Senao baixe get-pip.py para $pyDir" -ForegroundColor Yellow }

Step 2 "Instalar gputil + faster-whisper"
Run "& `"$pip`" install gputil faster-whisper"

Step 3 "Pin estavel para CUDA12 + cuDNN8"
Run "& `"$pip`" install --force-reinstall `"numpy<2`" ctranslate2==4.4.0 `"setuptools<81`""

if($WhisperX){
  Step "3b" "Instalar whisperx (fork IPED) para batchSize>1 (requer FFmpeg no PATH)"
  Run "& `"$pip`" install `"git+https://github.com/sepinf-inc/whisperx.git@multi-audio`""
}

Step 4 "Baixar DLLs cuBLAS+cuDNN (CUDA12) do Purfview"
$dest = Join-Path $env:TEMP $libsName
Write-Host "    URL    : $libsUrl"
Write-Host "    Destino: $dest"
if($Execute){
  Invoke-WebRequest -Uri $libsUrl -OutFile $dest
  Write-Host "    Download concluido." -ForegroundColor Green
}

Step 5 "Extrair as 4 DLLs para $pyDir"
$seven = Get-Command 7z.exe -ErrorAction SilentlyContinue
if($Execute){
  if($seven){
    Run "& `"$($seven.Source)`" e `"$dest`" -o`"$pyDir`" -y"
  } else {
    Write-Host "    7-Zip (7z.exe) nao encontrado. Extraia manualmente $dest e copie as 4 DLLs (cublas*, cudnn*) para $pyDir" -ForegroundColor Yellow
  }
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
