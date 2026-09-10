#!/usr/bin/env bash
#
# Prepara o deploy: clona o Overleaf Toolkit oficial em ./toolkit,
# gera a config inicial e aponta o toolkit para a config DESTE repo.
#
# Ideia: o codigo do Toolkit fica upstream (atualizavel com git pull),
# e apenas a SUA configuracao vive versionada aqui.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_DIR="$REPO_ROOT/toolkit"
UPSTREAM="https://github.com/overleaf/toolkit.git"

if [ ! -d "$TOOLKIT_DIR/.git" ]; then
  echo "==> Clonando o Overleaf Toolkit em ./toolkit"
  git clone --depth 1 "$UPSTREAM" "$TOOLKIT_DIR"
else
  echo "==> ./toolkit ja existe, atualizando"
  git -C "$TOOLKIT_DIR" pull --ff-only
fi

# bin/init gera config/overleaf.rc, config/variables.env e config/version
# com os defaults canonicos do upstream. Nao inventamos essas chaves aqui.
if [ ! -f "$REPO_ROOT/config/overleaf.rc" ]; then
  echo "==> Gerando config inicial via bin/init"
  ( cd "$TOOLKIT_DIR" && ./bin/init )
  cp -n "$TOOLKIT_DIR"/config/* "$REPO_ROOT/config/" 2>/dev/null || true
fi

# Faz o Toolkit usar a config deste repo em vez da propria
echo "==> Ligando toolkit/config -> ./config"
rm -rf "$TOOLKIT_DIR/config"
ln -s "$REPO_ROOT/config" "$TOOLKIT_DIR/config"

cat <<'MSG'

Pronto. Proximos passos:

  cd toolkit
  ./bin/up            # sobe os containers (Ctrl-C para sair do modo attach)
  ./bin/doctor        # diagnostico se algo nao subir

Depois abra http://localhost/launchpad para criar o admin.
Edite a config em ./config/ e commite as mudancas neste repo.
MSG
