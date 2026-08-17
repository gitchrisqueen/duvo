#!/usr/bin/env bash
# One-time setup. Run this well before the session, never during it.
#
# Everything here is idempotent and degrades gracefully: an optional tool that
# cannot be installed produces a warning, not a failure, because the exercise
# must not depend on any single piece of tooling being available on the day.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

CAVEMAN_VERSION="${CAVEMAN_VERSION:-2.1.0}"

# --- Python ----------------------------------------------------------------
have uv || die "uv is required. Install it from https://docs.astral.sh/uv/"
timed "installing Python dependencies" uv sync --all-extras

# --- Git hooks -------------------------------------------------------------
if py python -c "import pre_commit" 2>/dev/null || have pre-commit; then
  timed "installing git hooks" py pre-commit install --install-hooks
else
  step "installing pre-commit"
  uv tool install pre-commit >/dev/null 2>&1 || warn "could not install pre-commit"
  have pre-commit && pre-commit install --install-hooks || warn "git hooks not installed"
fi

# --- Local development secrets --------------------------------------------
step "local development secrets"
mkdir -p secrets
if [[ ! -f secrets/upstream_api_key ]]; then
  py python -c "import secrets as s, pathlib; pathlib.Path('secrets/upstream_api_key').write_text('dev-' + s.token_hex(16))"
  ok "wrote a local development key to secrets/upstream_api_key"
else
  ok "secrets/upstream_api_key already exists"
fi
chmod 600 secrets/upstream_api_key 2>/dev/null || true

# --- Secret scanning -------------------------------------------------------
if ! have gitleaks; then
  warn "gitleaks is not installed. Install it so the commit gate can scan offline:"
  warn "  https://github.com/gitleaks/gitleaks#installing"
fi
if [[ ! -f .secrets.baseline ]] && py python -c "import detect_secrets" 2>/dev/null; then
  timed "creating detect-secrets baseline" bash -c \
    'uv run detect-secrets scan --exclude-files "\.venv/|uv\.lock" > .secrets.baseline'
fi

# --- Token reduction -------------------------------------------------------
# Pinned deliberately. An upstream change on the morning of the session is an
# unacceptable variable, and this tool is a cushion rather than a dependency.
if have npm; then
  if ! have caveman; then
    step "installing caveman ${CAVEMAN_VERSION}"
    npm install -g "@caveman-ai/cli@${CAVEMAN_VERSION}" >/dev/null 2>&1 \
      && ok "caveman installed" \
      || warn "caveman could not be installed; scripts run unchanged without it"
  fi
  if have caveman; then
    caveman setup --install >/dev/null 2>&1 || warn "caveman setup did not complete"
    caveman telemetry off >/dev/null 2>&1 || true
    ok "caveman ready (telemetry off, proxy not used)"
  fi
else
  warn "npm not available; caveman skipped. Set CAVEMAN_DISABLE=1 to silence this."
fi

# --- Container images ------------------------------------------------------
if have docker && docker info >/dev/null 2>&1; then
  timed "pinning base image digests" scripts/pin_base_images.sh || warn "could not pin digests"
  step "warming the dependency layer cache"
  if scripts/docker_build.sh >/dev/null 2>&1; then
    ok "image layers cached; in-session rebuilds will only touch the source layer"
  else
    warn "image build failed during bootstrap. Resolve this before the session:"
    warn "  scripts/docker_build.sh"
  fi
else
  warn "Docker is not available here. The image build is verified in continuous"
  warn "integration, but preflight must confirm it on the machine you present from."
fi

echo
ok "bootstrap complete"
echo "Next: scripts/preflight.sh for the go/no-go check before recording."
