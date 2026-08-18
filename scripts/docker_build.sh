#!/usr/bin/env bash
# Build the images, reusing every layer that can be reused.
#
# Reports how long the build took, because the number is the point: after the
# first build, editing application code should rebuild in seconds. If it does
# not, the layer ordering in the Dockerfile has drifted and should be fixed
# before the session rather than discovered during it.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

have docker || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable."

build_args=()
if [[ -f .env.images ]]; then
  while IFS='=' read -r key value; do
    [[ "$key" == \#* || -z "$key" ]] && continue
    build_args+=(--build-arg "${key}=${value}")
  done <.env.images
fi

if [[ "${1:-}" == "--print-args" ]]; then
  printf '%s ' "${build_args[@]+"${build_args[@]}"}"
  exit 0
fi

export DOCKER_BUILDKIT=1

start=$(date +%s%N)
step "building runtime image"
# The `[@]+"${...[@]}"` form, not a plain `"${build_args[@]}"`, because
# build_args is often empty and bash before 4.4 (which is to say, stock macOS
# bash) throws "unbound variable" expanding an empty array under `set -u`.
# See scripts/_lib.sh for the general note on this.
shrink docker build "${build_args[@]+"${build_args[@]}"}" \
  --target runtime \
  --cache-from duvo-fde:local \
  --tag duvo-fde:local \
  .

step "building mock upstream image"
shrink docker build "${build_args[@]+"${build_args[@]}"}" \
  --target mock \
  --cache-from duvo-fde-mock:local \
  --tag duvo-fde-mock:local \
  .
elapsed_ms=$((($(date +%s%N) - start) / 1000000))

printf 'build completed in %sms\n' "$elapsed_ms"
record_evidence "PASS" "images built in ${elapsed_ms}ms"
ok "images built in ${elapsed_ms}ms"
