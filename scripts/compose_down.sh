#!/usr/bin/env bash
# Stop the stack and remove its volumes so the next run starts clean.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

have docker || die "Docker is not installed."

shrink docker compose down --volumes --remove-orphans
ok "stack stopped"
