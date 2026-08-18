#!/usr/bin/env bash
# Shared helpers. Sourced by every other script; not executable on its own.
# shellcheck shell=bash

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT
cd "$REPO_ROOT"

if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=''; C_BOLD=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''
fi

step()  { printf '%s==>%s %s\n' "$C_BLUE$C_BOLD" "$C_RESET" "$*"; }
ok()    { printf '%s  ok%s  %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s warn%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail()  { printf '%s fail%s %s\n' "$C_RED" "$C_RESET" "$*"; }
die()   { fail "$*"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Portability: target bash 3.2, not whatever bash wrote this.
#
# macOS ships bash 3.2.57 unmodified on every release since 2007, because
# Apple stopped updating it over the GPLv3 license change. Any script tested
# only against a modern bash (this repo's dev sandbox runs 5.2) can break on
# the exact machine a session gets recorded from. Two traps, both real bugs
# hit while building this scaffold:
#
#   1. `declare -A` (associative arrays) does not exist before bash 4.0.
#      Use a plain indexed array of "key=value" strings instead, split with
#      `${entry%%=*}` / `${entry#*=}`.
#   2. `mapfile`/`readarray` do not exist before bash 4.0. Use a
#      `while IFS= read -r line; do arr+=("$line"); done < <(...)` loop.
#   3. Expanding a possibly-empty array as `"${arr[@]}"` throws "unbound
#      variable" under `set -u` on any bash before 4.4 — bash 3.2 included.
#      Use `"${arr[@]+"${arr[@]}"}"` instead, or guard with
#      `((${#arr[@]} > 0))` before the expansion.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Token reduction.
#
# shrink wraps a COMMAND so its output is compressed before it reaches an
# agent's context. It is never applied to file contents, and never to anything
# a human will read. Documentation is protected separately and structurally;
# see docs/04-operations.md and scripts/check_prose.sh.
#
# Compression is byte-exact recoverable, and CAVEMAN_DISABLE=1 removes it
# entirely with no other behavioural change.
# ---------------------------------------------------------------------------
shrink() {
  if [[ "${CAVEMAN_DISABLE:-0}" == "1" ]] || ! have caveman; then
    "$@"
  else
    caveman shrink -- "$@"
  fi
}

# Run a command, printing a heading first, and record how long it took.
timed() {
  local label="$1"; shift
  local start end
  start=$(date +%s%N)
  step "$label"
  "$@"
  end=$(date +%s%N)
  printf '      %sdone in %sms%s\n' "$C_BOLD" "$(((end - start) / 1000000))" "$C_RESET"
}

# Append a line to the machine-written verification evidence log.
# Evidence is only ever written by scripts, never by hand, so that the log
# reflects commands that actually ran.
record_evidence() {
  local status="$1" detail="$2"
  local log="$REPO_ROOT/docs/05-verification.md"
  mkdir -p "$(dirname "$log")"
  if [[ ! -f "$log" ]]; then
    {
      printf '# Verification evidence\n\n'
      printf 'This file is written by scripts, never by hand. Each row records a\n'
      printf 'command that actually ran, when it ran, and what it returned.\n\n'
      printf '| Timestamp (UTC) | Result | Detail |\n'
      printf '| --- | --- | --- |\n'
    } >"$log"
  fi
  printf '| %s | %s | %s |\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$status" "$detail" >>"$log"
}

# Interpreter used when uv is not available. The smoke test deliberately needs
# nothing but the standard library, so that it exercises the same path a
# reviewer takes rather than one that only works inside a development
# environment.
if have python3; then
  PYTHON_BIN="$(command -v python3)"
elif have python; then
  PYTHON_BIN="$(command -v python)"
else
  PYTHON_BIN=""
fi
export PYTHON_BIN

# Run a project command. With uv present this resolves inside the project
# environment; without it, the command is run directly, which is what makes the
# container-only path work with no development tooling installed.
py() {
  if have uv; then
    uv run "$@"
    return
  fi

  local command="$1"
  shift
  case "$command" in
  python | python3)
    [[ -n "$PYTHON_BIN" ]] || die "No Python interpreter found on PATH."
    "$PYTHON_BIN" "$@"
    ;;
  *)
    have "$command" || die "$command is not available, and uv is not installed."
    "$command" "$@"
    ;;
  esac
}
