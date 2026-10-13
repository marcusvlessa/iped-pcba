"""Instala componentes opcionais no Python que vem com o IPED.

  python -m iped_pcba.componentes whisper    # faster-whisper (transcrição Whisper em CPU)

Precisa de internet (pypi.org). Se o Python do IPED não tiver pip, baixa o get-pip.py
oficial (bootstrap.pypa.io) antes.
"""

import os
import subprocess
import sys
import tempfile
import urllib.request

GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
PACOTES = {"whisper": ["faster-whisper", "numpy<2"]}


def tem_pip():
    try:
        import pip  # noqa: F401
        return True
    except ImportError:
        return False


def garantir_pip():
    if tem_pip():
        print("pip já está instalado.", flush=True)
        return
    destino = os.path.join(tempfile.gettempdir(), "get-pip.py")
    print("Baixando " + GET_PIP, flush=True)
    urllib.request.urlretrieve(GET_PIP, destino)
    subprocess.check_call([sys.executable, destino, "--no-warn-script-location"])


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in PACOTES:
        print("Uso: componentes {}".format("|".join(PACOTES)), file=sys.stderr)
        return 2
    print("Python: " + sys.executable, flush=True)
    garantir_pip()
    cmd = [sys.executable, "-m", "pip", "install", "--no-warn-script-location"] + PACOTES[argv[0]]
    print("$ " + " ".join(cmd), flush=True)
    rc = subprocess.call(cmd)
    print("Concluído." if rc == 0 else "Falhou (código {}).".format(rc), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
