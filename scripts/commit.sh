#!/usr/bin/env bash
# Stage, gate, and commit.
#
# The gate is deliberately tiered. Commit time runs the fast checks only, so
# that committing stays something you do often rather than something you avoid.
# The heavier checks run before a push, and the heaviest run in continuous
# integration.
#
# Skipping the gate is possible and is never the answer. A failing test means
# the code is wrong, not that the gate is inconvenient.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

message="${1:-}"
[[ -n "$message" ]] || die "Usage: scripts/commit.sh \"<conventional commit message>\""

if ! [[ "$message" =~ ^(feat|fix|docs|test|refactor|chore|build|ci|perf)(\(.+\))?!?:\ .+ ]]; then
  die "Message must follow conventional commits, for example: feat(orders): reject negative quantities"
fi

git add -A

if git diff --cached --quiet; then
  warn "nothing staged; no commit made"
  exit 0
fi

timed "fast unit suite" scripts/test.sh
timed "documentation prose" scripts/check_prose.sh

if have gitleaks; then
  timed "secret scan (staged changes)" shrink gitleaks protect --staged --no-banner --redact \
    --config .gitleaks.toml
else
  warn "gitleaks is not installed; the commit-time secret scan did not run"
fi

scripts/update_readme.sh >/dev/null
git add -A

git commit -m "$message"
ok "committed: $message"
