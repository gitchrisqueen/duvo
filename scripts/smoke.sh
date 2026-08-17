#!/usr/bin/env bash
# End-to-end exercise of the running stack, with no assistant involved.
#
# This is the deterministic proof that the thing actually works. It runs in
# continuous integration against the built image, so the path a reviewer takes
# is the path that is tested, and it writes its results into the verification
# evidence log rather than into a claim in a document.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

BASE_URL="${BASE_URL:-http://localhost:8080}"
KEY_FILE="${KEY_FILE:-$REPO_ROOT/secrets/upstream_api_key}"
checks=0
failures=0

# Returns the HTTP status code and body for a request, without needing curl.
http() {
  local method="$1" url="$2" key="${3:-}" body="${4:-}"
  py python - "$method" "$url" "$key" "$body" <<'PYTHON'
import json, sys, urllib.error, urllib.request

method, url, key, body = sys.argv[1:5]
data = body.encode() if body else None
request = urllib.request.Request(url, data=data, method=method)
if key:
    request.add_header("X-API-Key", key)
if data:
    request.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.status)
        print(response.read().decode())
except urllib.error.HTTPError as exc:
    print(exc.code)
    print(exc.read().decode())
except Exception as exc:  # noqa: BLE001
    print(0)
    print(json.dumps({"error": str(exc)}))
PYTHON
}

# Returns just the status code. Piping http() into `head -1` closes the pipe
# after the first line, so the Python process dies with BrokenPipeError while
# writing the body. Capturing the whole output and slicing it in the shell
# avoids the pipe entirely.
http_status() {
  local output
  output="$(http "$@")"
  printf '%s' "${output%%$'\n'*}"
}

check() {
  local label="$1" expected="$2" actual="$3"
  checks=$((checks + 1))
  if [[ "$actual" == "$expected" ]]; then
    ok "$label"
  else
    fail "$label (expected ${expected}, got ${actual})"
    failures=$((failures + 1))
  fi
}

step "upstream is reachable"
status="$(http_status GET "$BASE_URL/__health")"
check "mock upstream answers its health endpoint" "200" "$status"

if [[ "$status" != "200" ]]; then
  record_evidence "FAIL" "smoke test could not reach the stack at ${BASE_URL}"
  die "The stack is not running. Start it with: make up"
fi

key="$(cat "$KEY_FILE")"

step "authentication is enforced"
status="$(http_status GET "$BASE_URL/examples" "wrong-key")"
check "a wrong key is rejected" "401" "$status"

status="$(http_status GET "$BASE_URL/examples" "$key")"
check "the correct key is accepted" "200" "$status"

step "unknown identifiers are rejected rather than invented"
status="$(http_status GET "$BASE_URL/examples/does-not-exist" "$key")"
check "an unknown record returns not found" "404" "$status"

status="$(http_status GET "$BASE_URL/no-such-collection" "$key")"
check "an unknown collection returns not found" "404" "$status"

step "the upstream is not idempotent, which is why the server must be"
first="$(http_status POST "$BASE_URL/examples" "$key" '{"name":"smoke"}')"
second="$(http_status POST "$BASE_URL/examples" "$key" '{"name":"smoke"}')"
check "the first write is created" "201" "$first"
check "an identical second write is also created upstream" "201" "$second"

# --- Key rotation, against the running stack -------------------------------
# This is the check that found a real defect in a previous submission: the
# rotation appeared to work but the new key was never observed inside the
# container. Rotating by rename is what a secret manager actually does.
step "key rotation is observed without a restart"
rotated="rotated-$(py python -c 'import secrets; print(secrets.token_hex(8))')"
cp "$KEY_FILE" "${KEY_FILE}.smoke-backup"
printf '%s' "$rotated" >"${KEY_FILE}.new"
mv "${KEY_FILE}.new" "$KEY_FILE"

status="$(http_status GET "$BASE_URL/examples" "$rotated")"
check "the rotated key is accepted with no restart" "200" "$status"

status="$(http_status GET "$BASE_URL/examples" "$key")"
check "the previous key stops working" "401" "$status"

mv "${KEY_FILE}.smoke-backup" "$KEY_FILE"
status="$(http_status GET "$BASE_URL/examples" "$key")"
check "the original key works again after restoring it" "200" "$status"

# --- The service container -------------------------------------------------
if have docker && docker compose ps --services 2>/dev/null | grep -q '^server$'; then
  step "the service container reports its health"
  if docker compose exec -T server python -m duvo_fde health >/dev/null 2>&1; then
    ok "the server container reports ready"
    checks=$((checks + 1))
  else
    fail "the server container did not report ready"
    checks=$((checks + 1))
    failures=$((failures + 1))
  fi
fi

echo
if ((failures > 0)); then
  record_evidence "FAIL" "smoke test: ${failures} of ${checks} checks failed"
  die "smoke test failed (${failures} of ${checks} checks)"
fi

record_evidence "PASS" "smoke test: ${checks} of ${checks} checks passed against the running stack"
ok "smoke test passed (${checks} checks)"
