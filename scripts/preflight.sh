#!/usr/bin/env bash
# Go or no-go, immediately before recording starts.
#
# This is the last moment at which a problem is cheap. Everything checked here
# has, at some point, gone wrong for somebody in the middle of a timed exercise.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

blockers=0
warnings=0

require() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    ok "$label"
  else
    fail "$label"
    blockers=$((blockers + 1))
  fi
}

prefer() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    ok "$label"
  else
    warn "$label"
    warnings=$((warnings + 1))
  fi
}

step "tooling"
require "git is available" have git
require "uv is available" have uv
require "Python dependencies are installed" py python -c "import duvo_fde"
prefer "Docker daemon is reachable" bash -c 'docker info >/dev/null 2>&1'
prefer "gitleaks is installed" have gitleaks
prefer "GitHub CLI is installed" have gh

step "resources"
free_gb="$(df -Pk . | awk 'NR==2 {printf "%.0f", $4/1048576}')"
if ((free_gb >= 15)); then
  ok "disk headroom: ${free_gb}GB free"
else
  fail "only ${free_gb}GB free. Screen recording plus image builds needs more."
  blockers=$((blockers + 1))
fi

if have free; then
  free_mb="$(free -m | awk '/^Mem:/ {print $7}')"
  if ((free_mb >= 3000)); then
    ok "memory headroom: ${free_mb}MB available"
  else
    warn "only ${free_mb}MB available. Close everything not needed for the session."
    warnings=$((warnings + 1))
  fi
fi

step "repository"
if [[ -z "$(git status --porcelain)" ]]; then
  ok "working tree is clean"
else
  warn "working tree has uncommitted changes"
  warnings=$((warnings + 1))
fi
require "on the scaffold branch or main" bash -c 'git rev-parse --abbrev-ref HEAD >/dev/null'
prefer "the pre-brief tag exists" bash -c 'git rev-parse pre-brief >/dev/null 2>&1'

step "quality gates"
require "fast test suite is green" scripts/test.sh
require "documentation prose guard is green" scripts/check_prose.sh
require "the prose guard rejects compressed prose" bash -c \
  'py python -m tools.prose_guard tests/fixtures/terse_example.md >/dev/null 2>&1; [[ $? -eq 1 ]]'
require "documented commands still work" scripts/verify_docs.sh

step "token reduction"
if have caveman && [[ "${CAVEMAN_DISABLE:-0}" != "1" ]]; then
  prefer "caveman round-trips a command" bash -c 'caveman shrink -- echo roundtrip >/dev/null'
  if pgrep -f "caveman.*proxy" >/dev/null 2>&1; then
    fail "a caveman proxy is running. Do not route provider traffic through a proxy today."
    blockers=$((blockers + 1))
  else
    ok "no proxy in the request path"
  fi
else
  ok "caveman is not active; scripts run unchanged"
fi

step "local secrets"
require "a development key exists" test -f secrets/upstream_api_key
if git ls-files --error-unmatch secrets/upstream_api_key >/dev/null 2>&1; then
  fail "secrets/upstream_api_key is tracked by git. Remove it before doing anything else."
  blockers=$((blockers + 1))
else
  ok "no secret files are tracked by git"
fi

echo
printf '%s\n' "-------------------------------------------------------------"
cat <<'MANUAL'
Checked by hand, because no script can see them:

  [ ] Recording software is running and captures SCREEN, CAMERA, and AUDIO.
  [ ] You have played back ten seconds and confirmed the camera and the sound.
  [ ] Notifications are silenced on the machine and on your phone.
  [ ] The interview clock is running in a visible pane: make clock
  [ ] docs/INTERVIEW-RUNBOOK.md is open, and you have read it today.
  [ ] You have said the opening line on camera BEFORE opening the brief.
MANUAL
printf '%s\n' "-------------------------------------------------------------"
echo

if ((blockers > 0)); then
  fail "NO-GO: ${blockers} blocker(s), ${warnings} warning(s)"
  exit 1
fi

if ((warnings > 0)); then
  warn "GO, with ${warnings} warning(s). Know what you are giving up."
else
  ok "GO"
fi
