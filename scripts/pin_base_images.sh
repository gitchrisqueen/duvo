#!/usr/bin/env bash
# Resolve base image tags to digests and record them in .env.images.
#
# Digests are written by this script rather than typed by hand so the values are
# always real. Pinning matters mid-session: an upstream retag of a floating tag
# invalidates every cached layer at the worst possible moment.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

OUTPUT="${OUTPUT:-.env.images}"

have docker || die "Docker is required to resolve digests."
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable."

declare -A images=(
  [PYTHON_IMAGE]="python:3.12-slim"
  [UV_IMAGE]="ghcr.io/astral-sh/uv:0.5.11"
)

: >"$OUTPUT"
{
  echo "# Written by scripts/pin_base_images.sh. Do not edit by hand."
  echo "# Pass to the build with: docker build \$(scripts/docker_build.sh --print-args)"
} >>"$OUTPUT"

for name in "${!images[@]}"; do
  reference="${images[$name]}"
  step "resolving ${reference}"
  docker pull --quiet "$reference" >/dev/null
  digest="$(docker inspect --format='{{index .RepoDigests 0}}' "$reference")"
  [[ -n "$digest" ]] || die "could not resolve a digest for ${reference}"
  echo "${name}=${digest}" >>"$OUTPUT"
  ok "${name}=${digest}"
done

record_evidence "PASS" "base image digests pinned in ${OUTPUT}"
