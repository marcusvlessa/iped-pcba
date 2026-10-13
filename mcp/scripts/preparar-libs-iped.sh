#!/usr/bin/env bash
# Instala no repositório Maven local as bibliotecas do IPED usadas na compilação do MCP.
# Uso: bash scripts/preparar-libs-iped.sh <pasta do IPED> [versão]
# As bibliotecas vêm da própria instalação do IPED (pasta lib/); nada é baixado.
set -euo pipefail
IPED="${1:?informe a pasta do IPED (a que tem iped.jar)}"
VER="${2:-}"
LIB="$IPED/lib"
[ -d "$LIB" ] || { echo "Pasta $LIB não existe." >&2; exit 1; }
if [ -z "$VER" ]; then
  VER=$(ls "$LIB" | sed -n 's/^iped-engine-\([0-9.]*\)\.jar$/\1/p' | head -1)
fi
[ -n "$VER" ] || { echo "Não achei iped-engine-*.jar em $LIB." >&2; exit 1; }
MVN="${MVN:-mvn}"
for a in iped-api iped-engine iped-utils iped-parsers-impl iped-viewers-api iped-carvers-api; do
  jar="$LIB/$a-$VER.jar"
  [ -f "$jar" ] || { echo "Falta $jar" >&2; exit 1; }
  "$MVN" -q install:install-file -Dfile="$jar" -DgroupId=iped -DartifactId="$a" \
    -Dversion="$VER" -Dpackaging=jar -DgeneratePom=true
  echo "instalado $a $VER"
done
echo "Pronto. Compile com: mvn package -Diped.version=$VER"
