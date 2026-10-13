#!/usr/bin/env bash
# Instalador IPED-PCBA para o servidor Linux central (ou estação Linux).
# Por padrão só diagnostica. Exemplos:
#   ./instalar.sh /opt/iped-4.3.1 diagnosticar --papel servidor --temp /srv/ipedtemp
#   ./instalar.sh /opt/iped-4.3.1 aplicar      --papel servidor --temp /srv/ipedtemp
#   ./instalar.sh /opt/iped-4.3.1 reverter
set -euo pipefail
if [ $# -lt 1 ]; then sed -n 2,7p "$0"; exit 1; fi
RAIZ="$1"; shift
CMD="${1:-diagnosticar}"; if [ $# -gt 0 ]; then shift; fi
AQUI="$(cd "$(dirname "$0")" && pwd)"
PY="$RAIZ/python/bin/python3"; [ -x "$PY" ] || PY="$(command -v python3)"
PYTHONPATH="$AQUI/../instalador" exec "$PY" -m iped_pcba "$CMD" --iped "$RAIZ" "$@"
