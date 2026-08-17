#!/usr/bin/env bash
# CodeQL, run locally against a database prepared during bootstrap.
#
# This is honest about its cost: building a Python database takes minutes, not
# seconds, which is why it is not part of the fast local sweep. During the
# exercise it belongs in the background at around the forty minute mark, so its
# findings land before the final push. Continuous integration runs it on every
# push regardless.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

DB_DIR="${DB_DIR:-.codeql/db}"
RESULTS="${RESULTS:-.codeql/results.sarif}"

have codeql || die "CodeQL CLI is not installed. Continuous integration still runs it; see .github/workflows/codeql.yml"

mkdir -p "$(dirname "$RESULTS")"

if [[ ! -d "$DB_DIR" ]] || [[ "${REBUILD:-0}" == "1" ]]; then
  rm -rf "$DB_DIR"
  timed "building CodeQL database (this takes minutes)" \
    shrink codeql database create "$DB_DIR" --language=python --source-root=. --overwrite
fi

timed "running CodeQL security queries" \
  shrink codeql database analyze "$DB_DIR" \
  --format=sarif-latest --output="$RESULTS" \
  python-security-and-quality.qls

findings="$(py python -c "
import json, pathlib, sys
data = json.loads(pathlib.Path('$RESULTS').read_text())
print(sum(len(run.get('results', [])) for run in data.get('runs', [])))
")"

if [[ "$findings" != "0" ]]; then
  record_evidence "FAIL" "CodeQL reported ${findings} findings; see ${RESULTS}"
  die "CodeQL reported ${findings} findings. Inspect ${RESULTS}."
fi

record_evidence "PASS" "CodeQL clean (python-security-and-quality)"
ok "CodeQL clean"
