#!/usr/bin/env bash
# Instalador IPED-PCBA para o servidor Linux central (ou estação Linux).
# Por padrão só diagnostica. Exemplos:
#   ./instalar.sh /opt/iped-4.3.1 diagnosticar --papel servidor --temp /srv/ipedtemp
#   ./instalar.sh /opt/iped-4.3.1 aplicar      --papel servidor --temp /srv/ipedtemp
#   ./instalar.sh /opt/iped-4.3.1 reverter
#   ./instalar.sh baixar /opt/iped         (baixa e instala o IPED oficial, conferindo o SHA-256)
set -euo pipefail
if [ $# -lt 1 ]; then sed -n 2,8p "$0"; exit 1; fi
if [ "$1" = "baixar" ]; then
  AQUI="$(cd "$(dirname "$0")" && pwd)"
  PYTHONPATH="$AQUI/../instalador" exec python3 -m iped_pcba.dependencias instalar iped --destino "${2:-/opt/iped}"
fi
RAIZ="$1"; shift
CMD="${1:-diagnosticar}"; if [ $# -gt 0 ]; then shift; fi
AQUI="$(cd "$(dirname "$0")" && pwd)"
PY="$RAIZ/python/bin/python3"; [ -x "$PY" ] || PY="$(command -v python3)"
PYTHONPATH="$AQUI/../instalador" exec "$PY" -m iped_pcba "$CMD" --iped "$RAIZ" "$@"
