"""Tudo que o IPED-PCBA precisa numa máquina nova, conferido e instalado sozinho.

  python -m iped_pcba.dependencias situacao [--iped PASTA]
  python -m iped_pcba.dependencias instalar ITEM... [--iped PASTA] [--destino PASTA]
  python -m iped_pcba.dependencias instalar tudo [--iped PASTA]

Itens: iped, plugins (Whisper e reconhecimento facial do IPED), vcredist, gpu (CUDA para o Whisper),
ollama, modelo (modelo de IA local), pdftotext, mcp.
Downloads só de fontes oficiais (GitHub do IPED, ollama.com, Microsoft, GitHub da Poppler e deste projeto).
Quando o GitHub informa o SHA-256 do arquivo, ele é conferido antes de extrair. Antes de sobrescrever
arquivos do IPED (plugins), guarda cópia da pasta conf. Só a biblioteca padrão.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

WIN = os.name == "nt"
IPED_VERSAO = "4.3.1"
IPED_REPO = "sepinf-inc/IPED"
IPED_ZIP_FIM = "_and_java_plugins.zip"
IPED_PLUGINS_FIM = "_plugins_Whisper_FaceRecognition_AgeClassifier_Win64_CPU.zip"
PCBA_REPO = "marcusvlessa/iped-pcba"
OLLAMA_WIN = "https://ollama.com/download/OllamaSetup.exe"
VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
POPPLER_REPO = "oschwartz10612/poppler-windows"
CASA = os.path.join(os.path.expanduser("~"), ".iped-pcba")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ITENS = ["iped", "plugins", "vcredist", "gpu", "ollama", "modelo", "pdftotext", "mcp", "skills"]


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ downloads

def _json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "iped-pcba"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


_MAIS_NOVA = []


def versao_iped_mais_nova():
    """Versão da última release do IPED no GitHub; sem internet, a versão que este pacote conhece."""
    if not _MAIS_NOVA:
        try:
            req = urllib.request.Request("https://api.github.com/repos/{}/releases/latest".format(IPED_REPO),
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "iped-pcba"})
            with urllib.request.urlopen(req, timeout=5) as r:
                tag = json.loads(r.read().decode("utf-8")).get("tag_name") or ""
            v = tag.lstrip("vV")
            _MAIS_NOVA.append(v if _chave(v) > _chave(IPED_VERSAO) else IPED_VERSAO)
        except Exception:
            _MAIS_NOVA.append(IPED_VERSAO)
    return _MAIS_NOVA[0]


def _chave(v):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def versao_instalada(raiz):
    from .localizar import versao_de
    return versao_de(raiz) if raiz else ""


def asset_github(repo, nome=None, tag=None, termina=None):
    """URL, tamanho e SHA-256 (quando o GitHub informa) de um arquivo de release."""
    rel = _json("https://api.github.com/repos/{}/releases/{}".format(repo, "tags/" + tag if tag else "latest"))
    for a in rel.get("assets") or []:
        if (nome and a["name"] == nome) or (termina and a["name"].endswith(termina)):
            dig = a.get("digest") or ""
            return {"url": a["browser_download_url"], "nome": a["name"], "tamanho": a.get("size"),
                    "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else None}
    raise RuntimeError("Arquivo {} não encontrado na release {} de {}".format(nome or termina, tag or "latest", repo))


def baixar(url, destino, tamanho=None, sha256=None):
    """Baixa com progresso no log; retoma se o arquivo parcial já existir; confere tamanho e SHA-256."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    parcial = destino + ".parcial"
    if os.path.isfile(destino) and (not tamanho or os.path.getsize(destino) == tamanho):
        log("Já baixado:", destino)
    else:
        ja = os.path.getsize(parcial) if os.path.isfile(parcial) else 0
        req = urllib.request.Request(url, headers={"User-Agent": "iped-pcba"})
        if ja:
            req.add_header("Range", "bytes={}-".format(ja))
        log("Baixando", url)
        with urllib.request.urlopen(req, timeout=120) as r:
            if ja and r.status != 206:
                ja = 0
            total = int(r.headers.get("Content-Length") or 0) + ja
            with open(parcial, "ab" if ja else "wb") as f:
                feito, marca, t0 = ja, -1, time.time()
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
                    feito += len(bloco)
                    pc = int(feito * 100 / total) if total else -1
                    if pc != marca and (pc % 5 == 0 or pc < 0):
                        marca = pc
                        vel = (feito - ja) / max(1, time.time() - t0) / 1048576
                        log("  {}% ({} de {} MB, {:.1f} MB/s)".format(pc, feito >> 20, total >> 20, vel))
        if tamanho and os.path.getsize(parcial) != tamanho:
            raise RuntimeError("Download incompleto: {} de {} bytes. Rode de novo para continuar.".format(
                os.path.getsize(parcial), tamanho))
        os.replace(parcial, destino)
    if sha256:
        log("Conferindo SHA-256…")
        h = hashlib.sha256()
        with open(destino, "rb") as f:
            for b in iter(lambda: f.read(1 << 22), b""):
                h.update(b)
        if h.hexdigest().lower() != sha256.lower():
            os.remove(destino)
            raise RuntimeError("SHA-256 não confere; o arquivo foi apagado. Tente de novo.")
        log("SHA-256 confere:", sha256)
    return destino


def extrair(zipf, destino):
    log("Extraindo", os.path.basename(zipf), "em", destino)
    with zipfile.ZipFile(zipf) as z:
        nomes = z.infolist()
        base = os.path.realpath(destino)
        for i, info in enumerate(nomes):
            alvo = os.path.realpath(os.path.join(destino, info.filename))
            if not (alvo == base or alvo.startswith(base + os.sep)):
                raise RuntimeError("Arquivo fora da pasta dentro do zip: " + info.filename)
            z.extract(info, destino)
            if i % 2000 == 0:
                log("  {}/{} arquivos".format(i, len(nomes)))
    log("  {}/{} arquivos".format(len(nomes), len(nomes)))


def _downloads():
    d = os.path.join(CASA, "downloads")
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------------ verificações

def _python_iped(raiz):
    for p in (os.path.join(raiz or "", "python", "python.exe"), os.path.join(raiz or "", "python", "bin", "python3")):
        if os.path.isfile(p):
            return p
    return None


def _site_packages(raiz):
    for p in (os.path.join(raiz, "python", "Lib", "site-packages"),):
        if os.path.isdir(p):
            return p
    return None


def tem_plugins(raiz):
    sp = raiz and _site_packages(raiz)
    if not sp:
        return False
    return os.path.isdir(os.path.join(sp, "faster_whisper")) or os.path.isdir(os.path.join(sp, "whisperx"))


def tem_vcredist():
    if not WIN:
        return True
    try:
        import winreg
        for k in (r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                  r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, k) as h:
                    if winreg.QueryValueEx(h, "Installed")[0] == 1:
                        return True
            except OSError:
                pass
    except ImportError:
        pass
    return os.path.isfile(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vcruntime140_1.dll"))


def gpu_nvidia():
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if WIN else None)
    if not exe or not os.path.isfile(exe):
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True,
                             text=True, timeout=20).stdout.strip()
        return out.splitlines()[0] if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def tem_cuda_whisper(raiz):
    py = raiz and os.path.join(raiz, "python")
    return bool(py and os.path.isdir(py) and any(n.lower().startswith(("cublas64_", "cudnn")) for n in os.listdir(py)))


def ollama_exe():
    c = shutil.which("ollama")
    if c:
        return c
    if WIN:
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(p):
            return p
    return None


def ram_gb():
    try:
        if WIN:
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong)] + \
                           [("x%d" % i, ctypes.c_ulonglong) for i in range(6)]
            m = M()
            m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.t / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:
        return 0


def modelo_sugerido():
    """Modelo local com ferramentas, pelo tamanho da máquina."""
    ram, gpu = ram_gb(), gpu_nvidia()
    if gpu or ram >= 24:
        return "qwen2.5:7b"
    if ram >= 12:
        return "qwen2.5:3b"
    return "qwen2.5:1.5b"


def modelos_ollama():
    """Modelos do Ollama: pelo disco (Ollama fechado) e pelo ollama list."""
    from . import ialocal
    mods = ialocal.ollama_baixados()
    exe = ollama_exe()
    if exe:
        try:
            out = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30).stdout
            mods += [l.split()[0] for l in out.splitlines()[1:] if l.strip() and l.split()[0] not in mods]
        except (OSError, subprocess.SubprocessError):
            pass
    return mods


def _item_skills():
    from . import skills
    sit = skills.situacao()
    faltam = [d["nome"] for d in sit["destinos"] if d["detectado"]
              and any(i["estado"] not in ("instalada", "gerado") for i in d["itens"])]
    onde = ", ".join(d["nome"].split(" (")[0] for d in sit["destinos"] if d["detectado"])
    return {"id": "skills", "nome": "Skills de análise ({})".format(len(sit["skills"])), "ok": not faltam,
            "detalhe": ("instalar ou atualizar em: " + ", ".join(faltam)) if faltam else "instaladas em: " + onde,
            "auto": True}


def pdftotext():
    c = shutil.which("pdftotext")
    if c:
        return c
    base = os.path.join(CASA, "poppler")
    for raiz, _, arqs in os.walk(base) if os.path.isdir(base) else []:
        if ("pdftotext.exe" if WIN else "pdftotext") in arqs:
            return os.path.join(raiz, "pdftotext.exe" if WIN else "pdftotext")
    return None


def tem_mcp(raiz):
    return bool(raiz) and os.path.isfile(os.path.join(raiz, "pcba", "mcp", "iped-pcba-mcp.jar")) or \
        os.path.isfile(os.path.join(REPO, "mcp-dist", "iped-pcba-mcp.jar"))


def _item_iped(raiz):
    nova = versao_iped_mais_nova()
    tem = bool(raiz and os.path.isfile(os.path.join(raiz, "iped.jar")))
    atual = versao_instalada(raiz) if tem else ""
    velho = bool(tem and atual and _chave(atual) < _chave(nova))
    item = {"id": "iped", "nome": "IPED " + (atual or nova), "ok": tem and not velho,
            "detalhe": raiz or "não encontrado", "auto": True, "tamanho": "714 MB", "versao": atual, "mais_nova": nova}
    if velho:
        item.update(desatualizado=True, nome="IPED " + atual,
                    detalhe="{} · a versão atual é a {}; a nova é instalada ao lado e a antiga fica intacta".format(raiz, nova))
    return item


def situacao(raiz=None):
    """Lista o que existe e o que falta. 'auto' diz se o painel instala sozinho nesta máquina."""
    from . import ialocal
    gpu = gpu_nvidia()
    mods = modelos_ollama()
    lms = ialocal.lmstudio_baixados() if ialocal.lmstudio_instalado() else []
    bons = [m for m in mods + lms if ialocal.com_ferramentas(m)]
    det = "; ".join(x for x in ("Ollama: " + ", ".join(mods) if mods else "",
                                 "LM Studio: " + ", ".join(lms) if lms else "") if x)
    itens = [
        _item_iped(raiz),
        {"id": "plugins", "nome": "Transcrição (Whisper) e reconhecimento facial do IPED", "ok": tem_plugins(raiz),
         "detalhe": "bibliotecas Python do IPED", "auto": bool(raiz), "tamanho": "528 MB" if WIN else "pip"},
        {"id": "vcredist", "nome": "Microsoft Visual C++ 2015-2022", "ok": tem_vcredist(),
         "detalhe": "pedido pelos plugins do IPED", "auto": WIN, "admin": True, "aplica": WIN},
        {"id": "gpu", "nome": "CUDA para o Whisper na placa de vídeo", "ok": (not gpu) or tem_cuda_whisper(raiz),
         "detalhe": gpu or "sem placa NVIDIA: o Whisper roda no processador", "auto": bool(gpu) and WIN and bool(raiz),
         "aplica": bool(gpu)},
        {"id": "ollama", "nome": "Ollama (IA local)", "ok": bool(ollama_exe()),
         "detalhe": ollama_exe() or ("não é preciso: o LM Studio já tem modelo" if lms else "não instalado"),
         "auto": WIN, "aplica": not lms, "manual": None if WIN else "curl -fsSL https://ollama.com/install.sh | sh"},
        {"id": "modelo", "nome": "Modelo de IA local" + ("" if bons else " ({})".format(modelo_sugerido())),
         "ok": bool(bons), "detalhe": det or "nenhum modelo", "auto": bool(ollama_exe()) or WIN,
         "requer": "instale o Ollama primeiro"},
        {"id": "pdftotext", "nome": "Leitor de PDF (Poppler)", "ok": bool(pdftotext()), "detalhe": pdftotext() or
         "PDFs dos arquivos de contexto não são lidos", "auto": WIN,
         "manual": None if WIN else "sudo apt install poppler-utils"},
        {"id": "mcp", "nome": "MCP do IPED (IA consulta o caso)", "ok": tem_mcp(raiz),
         "detalhe": "vem no pacote da página de Releases", "auto": True},
        _item_skills(),
    ]
    return {"itens": itens, "faltam": [i["id"] for i in itens if not i["ok"] and i.get("aplica", True)],
            "sistema": platform.system(), "ram_gb": round(ram_gb())}


# ------------------------------------------------------------------ instalações

def pasta_padrao_iped():
    """Onde instalar o IPED: C:\\Tools\\IPED no Windows (ou o disco com mais espaço), /opt/iped no Linux."""
    if not WIN:
        return "/opt/iped" if os.access("/opt", os.W_OK) else os.path.join(os.path.expanduser("~"), "iped")
    melhor, livre = "C:\\", -1
    for letra in "CDEFGH":
        r = letra + ":\\"
        if os.path.isdir(r):
            try:
                f = shutil.disk_usage(r).free
            except OSError:
                continue
            if r == "C:\\":
                f *= 1.5  # prefere o C: se tiver espaço parecido
            if f > livre:
                melhor, livre = r, f
    return os.path.join(melhor, "Tools", "IPED")


def instalar_iped(destino=None, atual=None):
    """Instala a última versão do IPED. Atualizando, a nova vai ao lado da antiga, que fica intacta."""
    versao = versao_iped_mais_nova()
    if atual:
        destino = destino or os.path.dirname(os.path.normpath(atual))
        log("IPED instalado:", versao_instalada(atual) or "versão desconhecida", "em", atual)
        log("Instalando o IPED", versao, "ao lado; a pasta antiga não é alterada.")
    destino = destino or pasta_padrao_iped()
    a = asset_github(IPED_REPO, termina=IPED_ZIP_FIM, tag=versao)
    livre = shutil.disk_usage(os.path.splitdrive(os.path.abspath(destino))[0] + os.sep if WIN else "/").free
    if livre < 3 * 1024 ** 3:
        raise RuntimeError("Pouco espaço livre para o IPED (precisa de uns 3 GB).")
    z = baixar(a["url"], os.path.join(_downloads(), a["nome"]), a["tamanho"], a["sha256"])
    os.makedirs(destino, exist_ok=True)
    extrair(z, destino)
    raiz = os.path.join(destino, "iped-" + versao)
    if not os.path.isfile(os.path.join(raiz, "iped.jar")):
        raise RuntimeError("O zip não trouxe iped-{}/iped.jar".format(versao))
    if not WIN:
        for sub in ("jre/bin", "tools"):
            for r, _, fs in os.walk(os.path.join(raiz, sub)):
                for f in fs:
                    p = os.path.join(r, f)
                    os.chmod(p, os.stat(p).st_mode | 0o111)
    log("IPED instalado em", raiz)
    if atual:
        log("Abra \"1. Configurar a máquina\" e aplique a configuração para levar os ajustes da PCBA ao IPED novo.")
    log("IPED_RAIZ=" + raiz)
    return raiz


def instalar_plugins(raiz):
    if not raiz:
        raise RuntimeError("Instale o IPED primeiro.")
    if not WIN:
        py = _python_iped(raiz) or shutil.which("python3")
        log("Linux: instalando faster-whisper no Python", py)
        return subprocess.check_call([py, "-m", "pip", "install", "--user", "faster-whisper", "numpy<2"])
    a = asset_github(IPED_REPO, termina=IPED_PLUGINS_FIM, tag=versao_instalada(raiz) or IPED_VERSAO)
    z = baixar(a["url"], os.path.join(_downloads(), a["nome"]), a["tamanho"], a["sha256"])
    copia = os.path.join(raiz, "conf.antes-plugins-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copytree(os.path.join(raiz, "conf"), copia)
    log("Cópia da configuração antes dos plugins:", copia)
    extrair(z, raiz)
    # os plugins trazem um AudioTranscriptConfig.txt padrão: devolve o que estava configurado
    shutil.copy2(os.path.join(copia, "AudioTranscriptConfig.txt"), os.path.join(raiz, "conf", "AudioTranscriptConfig.txt"))
    log("Plugins instalados; a configuração de transcrição anterior foi mantida.")


def _executar_instalador(url, nome, args):
    exe = baixar(url, os.path.join(_downloads(), nome))
    log("Executando", nome, " ".join(args), "(pode pedir confirmação do Windows)")
    rc = subprocess.call([exe] + args)
    if rc not in (0, 3010):
        raise RuntimeError("{} terminou com código {}".format(nome, rc))
    if rc == 3010:
        log("Instalado; o Windows pede reinicialização para concluir.")


def instalar_vcredist():
    if tem_vcredist():
        return log("Visual C++ já instalado.")
    _executar_instalador(VCREDIST, "vc_redist.x64.exe", ["/install", "/quiet", "/norestart"])


def instalar_gpu(raiz):
    if not gpu_nvidia():
        return log("Sem placa NVIDIA: nada a fazer; o Whisper usa o processador.")
    script = os.path.join(REPO, "scripts", "whisper_gpu.ps1")
    log("Placa:", gpu_nvidia())
    rc = subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                          "-IpedRoot", raiz, "-Execute"])
    if rc:
        raise RuntimeError("Preparação do CUDA terminou com código {}".format(rc))


def instalar_ollama():
    if ollama_exe():
        return log("Ollama já instalado:", ollama_exe())
    if not WIN:
        raise RuntimeError("No Linux rode: curl -fsSL https://ollama.com/install.sh | sh  (pede senha de administrador)")
    _executar_instalador(OLLAMA_WIN, "OllamaSetup.exe", ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    for _ in range(30):
        if ollama_exe():
            break
        time.sleep(2)
    log("Ollama:", ollama_exe() or "instalado; abra o Ollama uma vez se ele não aparecer")


def instalar_modelo(nome=None):
    exe = ollama_exe()
    if not exe:
        raise RuntimeError("Instale o Ollama primeiro.")
    nome = nome or modelo_sugerido()
    log("Baixando o modelo", nome, "(alguns GB; a primeira vez demora)")
    if subprocess.call([exe, "pull", nome]):
        raise RuntimeError("ollama pull {} falhou. O Ollama está aberto?".format(nome))
    log("Modelo pronto:", nome)


def instalar_pdftotext():
    if pdftotext():
        return log("pdftotext já disponível:", pdftotext())
    if not WIN:
        raise RuntimeError("No Linux rode: sudo apt install poppler-utils")
    a = asset_github(POPPLER_REPO, termina=".zip")
    z = baixar(a["url"], os.path.join(_downloads(), a["nome"]), a["tamanho"], a["sha256"])
    extrair(z, os.path.join(CASA, "poppler"))
    log("pdftotext:", pdftotext())


def instalar_mcp(raiz):
    if os.path.isfile(os.path.join(REPO, "mcp-dist", "iped-pcba-mcp.jar")):
        log("O MCP já está no pacote. Use Configurar a máquina para copiá-lo para o IPED.")
        return
    nome = "iped-pcba-windows.zip" if WIN else "iped-pcba-linux.tar.gz"
    a = asset_github(PCBA_REPO, nome=nome)
    arq = baixar(a["url"], os.path.join(_downloads(), a["nome"]), a["tamanho"], a["sha256"])
    tmp = tempfile.mkdtemp(prefix="iped-pcba-")
    if arq.endswith(".zip"):
        extrair(arq, tmp)
    else:
        import tarfile
        with tarfile.open(arq) as t:
            t.extractall(tmp, filter="data") if sys.version_info >= (3, 12) else t.extractall(tmp)
    origem = os.path.join(tmp, "iped-pcba", "mcp-dist")
    if not os.path.isdir(origem):
        raise RuntimeError("O pacote baixado não tem mcp-dist.")
    shutil.copytree(origem, os.path.join(REPO, "mcp-dist"))
    log("MCP copiado para", os.path.join(REPO, "mcp-dist"), "- agora use Configurar a máquina.")


def instalar_skills():
    from . import skills
    for f in skills.instalar():
        log("{}: {} ({})".format(f["destino"], f["skill"], f["acao"]))


def instalar(itens, raiz=None, destino=None):
    sit = {i["id"]: i for i in situacao(raiz)["itens"]}
    if itens == ["tudo"]:
        itens = [i for i in ITENS if not sit[i]["ok"] and sit[i].get("aplica", True) and sit[i]["auto"]]
    falhas = []
    for item in itens:
        log("")
        log("== " + sit[item]["nome"])
        try:
            if item == "iped":
                raiz = instalar_iped(destino, atual=raiz if sit["iped"].get("desatualizado") else None)
            elif item == "plugins":
                instalar_plugins(raiz)
            elif item == "vcredist":
                instalar_vcredist()
            elif item == "gpu":
                instalar_gpu(raiz)
            elif item == "ollama":
                instalar_ollama()
            elif item == "modelo":
                instalar_modelo()
            elif item == "pdftotext":
                instalar_pdftotext()
            elif item == "mcp":
                instalar_mcp(raiz)
            elif item == "skills":
                instalar_skills()
        except Exception as e:
            falhas.append(item)
            log("FALHOU:", e)
    log("")
    log("Concluído." if not falhas else "Terminou com falhas em: " + ", ".join(falhas))
    return 1 if falhas else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="iped_pcba.dependencias")
    ap.add_argument("acao", choices=["situacao", "instalar"])
    ap.add_argument("itens", nargs="*")
    ap.add_argument("--iped")
    ap.add_argument("--destino", help="pasta onde instalar o IPED")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if a.acao == "situacao":
        print(json.dumps(situacao(a.iped), indent=2, ensure_ascii=False))
        return 0
    ruins = [i for i in a.itens if i not in ITENS + ["tudo"]]
    if not a.itens or ruins:
        print("Itens: " + ", ".join(ITENS + ["tudo"]), file=sys.stderr)
        return 2
    return instalar(a.itens, a.iped, a.destino)


if __name__ == "__main__":
    sys.exit(main())
