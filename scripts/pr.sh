#!/usr/bin/env bash
# Verify, push, and open a draft pull request.
#
# The pull request is opened early and deliberately: continuous integration and
# automated review then run for the whole session rather than becoming a
# bottleneck in the last five minutes.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

branch="$(git rev-parse --abbrev-ref HEAD)"
base="${BASE_BRANCH:-main}"
title="${1:-Forward Deployed Engineer exercise}"

[[ "$branch" != "$base" ]] || die "Refusing to open a pull request from ${base}. Work on a branch."

if [[ "${SKIP_VERIFY:-0}" != "1" ]]; then
  timed "verification sweep" scripts/verify_all.sh
else
  warn "verification skipped by request; the pull request will say so"
fi

scripts/push_retry.sh "$branch" || warn "continuing without a successful push"

if ! have gh; then
  warn "The GitHub CLI is not installed, so the pull request was not opened here."
  warn "Open a draft pull request from ${branch} into ${base} in the browser."
  exit 0
fi

if gh pr view "$branch" >/dev/null 2>&1; then
  ok "a pull request already exists for ${branch}"
  gh pr view "$branch" --json url --jq .url
  exit 0
fi

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
{
  echo "Draft opened early so that continuous integration and automated review run"
  echo "throughout the session rather than at the end."
  echo
  echo "Verification evidence is written by scripts into \`docs/05-verification.md\`."
  echo "Nothing in the documentation is claimed unless a command produced it."
} >"$body_file"

gh pr create --draft --base "$base" --head "$branch" --title "$title" --body-file "$body_file"
ok "draft pull request opened"
