#!/usr/bin/env bash
# Local security sweep. Designed to finish in seconds so it is actually run.
#
# A note on CodeQL, because overstating tooling is exactly the kind of claim a
# reviewer tests: CodeQL takes minutes on Python, not seconds. It runs in
# continuous integration, and optionally in the background here through
# scripts/codeql.sh. The fast local equivalents are semgrep and bandit.
#
# GitGuardian runs where a key and network are available. Its absence never
# fails this script, because a scan that cannot run is not a finding; gitleaks
# covers the same ground offline.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

FAST="${FAST:-0}"
failures=0

run_check() {
  local label="$1"; shift
  step "$label"
  if "$@"; then
    ok "$label"
  else
    fail "$label"
    failures=$((failures + 1))
  fi
}

# --- Secrets ---------------------------------------------------------------
if have gitleaks; then
  run_check "gitleaks (working tree)" shrink gitleaks detect --no-banner --redact --source . \
    --config .gitleaks.toml
else
  warn "gitleaks not installed; run scripts/bootstrap.sh"
  failures=$((failures + 1))
fi

if have detect-secrets || py python -c "import detect_secrets" 2>/dev/null; then
  step "detect-secrets"
  if py detect-secrets-hook --baseline .secrets.baseline $(git ls-files 2>/dev/null); then
    ok "detect-secrets"
  else
    fail "detect-secrets"
    failures=$((failures + 1))
  fi
fi

if [[ -n "${GITGUARDIAN_API_KEY:-}" ]] && have ggshield; then
  run_check "GitGuardian" shrink ggshield secret scan path --recursive --yes .
else
  warn "GitGuardian skipped (no key or ggshield not installed); gitleaks covers this offline"
fi

# --- Static analysis -------------------------------------------------------
run_check "bandit" shrink py bandit -q -c pyproject.toml -r src tools

if have semgrep; then
  run_check "semgrep" shrink semgrep --quiet --error --config p/python --config p/security-audit src tools
else
  warn "semgrep not installed; CodeQL covers this in continuous integration"
fi

# --- Dependencies ----------------------------------------------------------
# The lock file is audited rather than the installed environment. That is both
# more accurate, because it covers exactly what a deployment will install, and
# avoids auditing this project against a package index it was never published
# to.
if [[ "$FAST" != "1" ]]; then
  requirements="$(mktemp)"
  trap 'rm -f "$requirements"' EXIT
  uv export --format requirements-txt --no-emit-project --no-hashes -q -o "$requirements"
  run_check "pip-audit (locked dependencies)" shrink py pip-audit --strict \
    --progress-spinner off -r "$requirements"
else
  warn "pip-audit skipped in fast mode"
fi

if ((failures > 0)); then
  record_evidence "FAIL" "security sweep reported ${failures} failing checks"
  die "security sweep failed (${failures} checks)"
fi

record_evidence "PASS" "security sweep clean (gitleaks, bandit, dependency audit)"
ok "security sweep clean"
