#!/usr/bin/env bash
#
# Gera a config inicial (se faltar) e aponta toolkit/config para ./config.
# O Toolkit ja vem versionado em ./toolkit — nao clona nada.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_DIR="$REPO_ROOT/toolkit"

[ -x "$TOOLKIT_DIR/bin/up" ] || {
  echo "erro: ./toolkit nao encontrado. Esse diretorio faz parte deste repo." >&2
  exit 1
}

mkdir -p "$REPO_ROOT/config"

if [ ! -f "$REPO_ROOT/config/overleaf.rc" ]; then
  echo "==> Gerando config inicial via bin/init"
  if [ ! -d "$TOOLKIT_DIR/config" ]; then
    mkdir -p "$TOOLKIT_DIR/config"
  fi
  ( cd "$TOOLKIT_DIR" && ./bin/init )
  if [ ! -L "$TOOLKIT_DIR/config" ]; then
    cp -n "$TOOLKIT_DIR"/config/* "$REPO_ROOT/config/" 2>/dev/null || true
  fi
fi

echo "==> Ligando toolkit/config -> ../config"
rm -rf "$TOOLKIT_DIR/config"
ln -sfn ../config "$TOOLKIT_DIR/config"
