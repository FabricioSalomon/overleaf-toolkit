# Empacota e carrega as imagens Docker deste snapshot.
# Esperado: REPO_ROOT, die()

IMAGES_DIR="$REPO_ROOT/vendor/images"
IMAGES_PREFIX="$IMAGES_DIR/stack.tar.gz.part-"
IMAGES_MANIFEST="$IMAGES_DIR/manifest"

docker_ok() {
  docker info >/dev/null 2>&1
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    die "Docker nao encontrado.

Instale o Docker Desktop, abra ele, espere o icone ficar verde e rode de novo:
  npm start"
  fi
  if docker_ok; then
    return 0
  fi
  if [ -e /var/run/docker.sock ] && [ ! -w /var/run/docker.sock ]; then
    die "sem permissao no Docker.

No Linux/WSL:
  sudo usermod -aG docker \"\$USER\"
  newgrp docker

Feche o terminal, abra de novo e rode: npm start"
  fi
  die "Docker nao esta rodando.

Abra o Docker Desktop, espere o icone ficar verde e rode de novo:
  npm start"
}

snapshot_images() {
  (
    # shellcheck source=/dev/null
    source "$REPO_ROOT/config/overleaf.rc"
    local version
    version="$(tr -d '[:space:]' < "$REPO_ROOT/config/version")"
    printf '%s\n' \
      "${OVERLEAF_IMAGE_NAME:-sharelatex/sharelatex}:${version}" \
      "${MONGO_IMAGE}:${MONGO_VERSION}" \
      "${REDIS_IMAGE}"
  )
}

image_present() {
  docker image inspect "$1" >/dev/null 2>&1
}

all_snapshot_images_present() {
  local img
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    image_present "$img" || return 1
  done < <(snapshot_images)
}

have_image_parts() {
  [ -f "$IMAGES_MANIFEST" ] || return 1
  ls "$IMAGES_PREFIX"* >/dev/null 2>&1
}

cmd_pack() {
  require_docker
  mkdir -p "$IMAGES_DIR"

  local img missing=0
  echo "==> Conferindo imagens locais"
  while IFS= read -r img; do
    if image_present "$img"; then
      echo "    ok  $img"
    else
      echo "    falta  $img"
      missing=1
    fi
  done < <(snapshot_images)
  [ "$missing" -eq 0 ] || die "alguma imagem do snapshot nao esta no Docker. Suba o Overleaf nesta maquina e rode de novo."

  local stage
  stage="$(mktemp -d)"

  snapshot_images > "$stage/manifest"

  echo "==> Empacotando (vai demorar, sao alguns GB)"
  # 90MB por parte: abaixo do limite de 100MB do GitHub.
  if ! docker save $(snapshot_images) | gzip -9 | split -b 90m - "$stage/stack.tar.gz.part-"; then
    rm -rf "$stage"
    die "empacotamento falhou. As partes antigas em vendor/images/ foram mantidas."
  fi
  if ! cat "$stage"/stack.tar.gz.part-* | gzip -t; then
    rm -rf "$stage"
    die "o pacote ficou cortado. As partes antigas em vendor/images/ foram mantidas."
  fi

  rm -f "$IMAGES_PREFIX"* "$IMAGES_MANIFEST"
  mv "$stage"/stack.tar.gz.part-* "$stage/manifest" "$IMAGES_DIR/"
  rm -rf "$stage"

  local parts size
  parts="$(find "$IMAGES_DIR" -name 'stack.tar.gz.part-*' | wc -l)"
  size="$(du -sh "$IMAGES_DIR" | awk '{print $1}')"
  echo "==> $parts partes, $size em vendor/images/"
  echo "Commite vendor/images/ neste repo. Sem isso o snapshot nao viaja com o git."
}

cmd_load_images() {
  echo "==> Carregando imagens do repo (primeira vez, demora)"
  cat "$IMAGES_PREFIX"* | gzip -dc | docker load
}

ensure_images() {
  require_docker
  if all_snapshot_images_present; then
    return 0
  fi
  if have_image_parts; then
    cmd_load_images
    all_snapshot_images_present || die "as partes em vendor/images/ nao bateram com config/version"
    return 0
  fi
  die "este clone nao tem as imagens em vendor/images/.

Na maquina onde o Overleaf JA roda:
  ./dev pack
  git add vendor/images
  git commit -m \"snapshot das imagens Docker\"

Depois o npm start funciona offline, sem Docker Hub."
}
