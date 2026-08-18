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

previous_sha="$(git rev-parse HEAD 2>/dev/null || echo none)"
git commit -m "$message"
new_sha="$(git rev-parse HEAD)"

# The verification sweep stamps the commit it verified, and then refreshes the
# generated status block and evidence log. Committing those regenerated files
# would otherwise invalidate the stamp and block the next push over changes that
# contain no source at all. Carry the stamp forward, but only when the commit
# really did touch nothing but generated files.
stamp_dir="$REPO_ROOT/.claude/state"
if [[ -f "$stamp_dir/verified-$previous_sha" ]]; then
  changed="$(git diff --name-only "$previous_sha" "$new_sha")"
  generated_only=1
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    case "$file" in
    README.md | docs/05-verification.md) ;;
    *)
      generated_only=0
      break
      ;;
    esac
  done <<<"$changed"

  if ((generated_only == 1)); then
    mkdir -p "$stamp_dir"
    touch "$stamp_dir/verified-$new_sha"
    ok "carried the verification stamp forward: this commit only regenerated status files"
  fi
fi

ok "committed: $message"
