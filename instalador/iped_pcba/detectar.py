"""Detecção de hardware e da instalação do IPED (Windows e Linux).

Somente leitura: nada aqui altera a máquina. As funções parse_* são puras
para poderem ser testadas sem o hardware real.
"""

import datetime
import glob
import json
import os
import platform
import re
import shutil
import socket
import subprocess

TIMEOUT = 30


def _rodar(cmd):
    """Executa um comando e devolve stdout, ou '' se falhar."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _powershell(script):
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return ""
    return _rodar([exe, "-NoProfile", "-NonInteractive", "-Command", script])


# ---------------------------------------------------------------- parsers


def parse_nvidia_smi(csv_texto, cabecalho_texto=""):
    """Lê a saída de
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
    e, opcionalmente, o cabeçalho do nvidia-smi (para a versão de CUDA)."""
    cuda = ""
    m = re.search(r"CUDA Version:\s*([\d.]+)", cabecalho_texto or "")
    if m:
        cuda = m.group(1)
    gpus = []
    for linha in (csv_texto or "").splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) < 3 or not partes[0]:
            continue
        try:
            vram = round(float(partes[1]) / 1024, 1)
        except ValueError:
            vram = 0.0
        gpus.append({"nome": partes[0], "vram_gb": vram, "driver": partes[2], "cuda": cuda})
    return gpus


def parse_meminfo(texto):
    m = re.search(r"^MemTotal:\s+(\d+)\s+kB", texto or "", re.M)
    return round(int(m.group(1)) / 1024 / 1024, 1) if m else 0.0


def parse_cpuinfo(texto):
    nome = ""
    m = re.search(r"^model name\s*:\s*(.+)$", texto or "", re.M)
    if m:
        nome = m.group(1).strip()
    # núcleos físicos = pares únicos (physical id, core id)
    pares = set()
    pid = cid = None
    for linha in (texto or "").splitlines():
        if linha.startswith("physical id"):
            pid = linha.split(":")[1].strip()
        elif linha.startswith("core id"):
            cid = linha.split(":")[1].strip()
        elif not linha.strip():
            if pid is not None and cid is not None:
                pares.add((pid, cid))
            pid = cid = None
    if pid is not None and cid is not None:
        pares.add((pid, cid))
    return nome, len(pares)


def parse_lsblk(json_texto):
    """lsblk -J -b -d -o NAME,ROTA,SIZE,MODEL,TYPE"""
    try:
        dados = json.loads(json_texto or "{}")
    except ValueError:
        return []
    discos = []
    for d in dados.get("blockdevices", []):
        if d.get("type") not in (None, "disk"):
            continue
        if re.match(r"(zram|ram|loop)\d", d.get("name") or ""):
            continue
        rota = d.get("rota")
        if isinstance(rota, str):
            rota = rota in ("1", "true")
        tipo = "hdd" if rota else "ssd"
        discos.append({
            "nome": (d.get("model") or d.get("name") or "").strip(),
            "dispositivo": d.get("name"),
            "tipo": tipo,
            "tamanho_gb": round(int(d.get("size") or 0) / 1024 ** 3),
        })
    return discos


def parse_windows_json(texto):
    """Saída JSON do bloco PowerShell de _coletar_windows."""
    try:
        d = json.loads(texto or "{}")
    except ValueError:
        return {}
    discos = d.get("discos") or []
    if isinstance(discos, dict):
        discos = [discos]
    mapa = {"3": "hdd", "4": "ssd", "HDD": "hdd", "SSD": "ssd"}
    return {
        "cpu": {
            "nome": (d.get("cpuNome") or "").strip(),
            "fisicos": int(d.get("cpuFisicos") or 0),
            "logicos": int(d.get("cpuLogicos") or 0),
        },
        "ram_gb": round(float(d.get("ramBytes") or 0) / 1024 ** 3, 1),
        "discos": [
            {
                "nome": (x.get("FriendlyName") or "").strip(),
                "tipo": mapa.get(str(x.get("MediaType")), "desconhecido"),
                "tamanho_gb": round(float(x.get("Size") or 0) / 1024 ** 3),
                "letras": x.get("Letras") or "",
            }
            for x in discos
        ],
    }


# ---------------------------------------------------------------- coleta

_PS_HARDWARE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cpus = Get-CimInstance Win32_Processor
$discos = foreach($d in Get-PhysicalDisk){
  $letras = (Get-Disk | Where-Object { $_.SerialNumber -eq $d.SerialNumber } |
    Get-Partition | Where-Object DriveLetter | ForEach-Object { $_.DriveLetter }) -join ''
  [pscustomobject]@{ FriendlyName=$d.FriendlyName; MediaType="$($d.MediaType)"; Size=$d.Size; Letras=$letras }
}
[pscustomobject]@{
  cpuNome   = ($cpus | Select-Object -First 1).Name
  cpuFisicos= ($cpus | Measure-Object NumberOfCores -Sum).Sum
  cpuLogicos= ($cpus | Measure-Object NumberOfLogicalProcessors -Sum).Sum
  ramBytes  = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
  discos    = @($discos)
} | ConvertTo-Json -Depth 4 -Compress
"""


def _coletar_windows():
    return parse_windows_json(_powershell(_PS_HARDWARE))


def _coletar_linux():
    try:
        with open("/proc/cpuinfo") as f:
            nome, fisicos = parse_cpuinfo(f.read())
    except OSError:
        nome, fisicos = platform.processor(), 0
    try:
        with open("/proc/meminfo") as f:
            ram = parse_meminfo(f.read())
    except OSError:
        ram = 0.0
    discos = parse_lsblk(_rodar(["lsblk", "-J", "-b", "-d", "-o", "NAME,ROTA,SIZE,MODEL,TYPE"]))
    logicos = os.cpu_count() or 0
    return {
        "cpu": {"nome": nome, "fisicos": fisicos or logicos, "logicos": logicos},
        "ram_gb": ram,
        "discos": discos,
    }


def _coletar_gpus():
    if not shutil.which("nvidia-smi"):
        return []
    csv = _rodar(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                  "--format=csv,noheader,nounits"])
    return parse_nvidia_smi(csv, _rodar(["nvidia-smi"]))


def tipo_disco_do_caminho(caminho, maquina=None):
    """Retorna 'ssd', 'hdd' ou 'desconhecido' para o disco onde está o caminho."""
    if not caminho:
        return "desconhecido"
    if os.name == "nt":
        letra = os.path.splitdrive(os.path.abspath(caminho))[0][:1].upper()
        for d in (maquina or {}).get("discos", []):
            if letra and letra in (d.get("letras") or "").upper():
                return d.get("tipo", "desconhecido")
        return "desconhecido"
    alvo = caminho
    while alvo and not os.path.exists(alvo):
        alvo = os.path.dirname(alvo)
    dev = _rodar(["findmnt", "-n", "-o", "SOURCE", "--target", alvo or "/"]).strip()
    if not dev.startswith("/dev/"):
        return "desconhecido"
    pai = _rodar(["lsblk", "-n", "-o", "PKNAME", dev]).strip().splitlines()
    nome = (pai[0].strip() if pai and pai[0].strip() else os.path.basename(dev))
    rota = _rodar(["lsblk", "-n", "-d", "-o", "ROTA", "/dev/" + nome]).strip()
    if rota == "0":
        return "ssd"
    if rota == "1":
        return "hdd"
    return "desconhecido"


def detectar_iped(raiz):
    """Inspeciona uma pasta de instalação do IPED."""
    info = {"raiz": raiz, "encontrado": False}
    if not raiz or not os.path.isdir(raiz):
        return info
    info["encontrado"] = os.path.isfile(os.path.join(raiz, "IPEDConfig.txt"))
    versao = ""
    for jar in glob.glob(os.path.join(raiz, "lib", "iped-engine-*.jar")):
        m = re.search(r"iped-engine-([\d.]+(?:-SNAPSHOT)?)\.jar$", jar)
        if m:
            versao = m.group(1)
    if not versao:
        m = re.search(r"iped-([\d.]+)", os.path.basename(os.path.normpath(raiz)))
        versao = m.group(1) if m else ""
    info["versao"] = versao
    py = "python.exe" if os.name == "nt" else "bin/python3"
    info["python_embarcado"] = os.path.isfile(os.path.join(raiz, "python", py))
    java = "java.exe" if os.name == "nt" else "java"
    info["java_embarcado"] = os.path.isfile(os.path.join(raiz, "jre", "bin", java))
    info["pacotes_python"] = pacotes_python(raiz)
    info["perfis"] = sorted(
        p for p in os.listdir(os.path.join(raiz, "profiles"))
        if os.path.isdir(os.path.join(raiz, "profiles", p))
    ) if os.path.isdir(os.path.join(raiz, "profiles")) else []
    return info


PACOTES_DE_INTERESSE = ("faster_whisper", "ctranslate2", "whisperx", "torch", "tensorflow",
                        "face_recognition", "huggingsound")


def pacotes_python(raiz):
    """Pacotes relevantes instalados no Python embarcado do IPED."""
    pastas = [os.path.join(raiz, "python", "Lib", "site-packages")]
    pastas += glob.glob(os.path.join(raiz, "python", "lib", "python3*", "site-packages"))
    achados = set()
    for pasta in pastas:
        if not os.path.isdir(pasta):
            continue
        nomes = os.listdir(pasta)
        for p in PACOTES_DE_INTERESSE:
            if p in nomes:
                achados.add(p)
    return sorted(achados)


def detectar(raiz_iped=None):
    """Coleta tudo e devolve o dicionário que vai para maquina.json."""
    so = "windows" if os.name == "nt" else "linux"
    base = _coletar_windows() if so == "windows" else _coletar_linux()
    base = base or {"cpu": {"nome": "", "fisicos": 0, "logicos": os.cpu_count() or 0},
                    "ram_gb": 0.0, "discos": []}
    base.update({
        "so": so,
        "so_versao": platform.platform(),
        "hostname": socket.gethostname(),
        "gpus": _coletar_gpus(),
        "iped": detectar_iped(raiz_iped),
        "coletado_em": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    return base
