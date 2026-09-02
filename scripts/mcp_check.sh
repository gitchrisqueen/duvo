#!/usr/bin/env bash
# Prove the tool server speaks the protocol before any assistant is attached.
#
# Order of operations during the exercise: run this, read the output, fix what
# is broken, and only then connect a client. Debugging a transport through a
# language model is the slowest route to an answer that exists.
#
# A handshake on its own is a weak check. It completes against a server whose
# every tool call would fail, because initialize and tools/list touch neither
# the credential store nor the upstream. So when an upstream is serving, this
# also makes real tool calls and reads the results off the wire. That is the
# only place the message an assistant actually receives can be observed: an
# in-process test sees an exception, and the protocol library is entitled to
# replace the message before the client ever sees it.
#
# Usage:
#   scripts/mcp_check.sh                 handshake, plus calls if an upstream is up
#   scripts/mcp_check.sh --no-call       handshake only
#   DUVO_UPSTREAM_BASE_URL=... scripts/mcp_check.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

UPSTREAM="${DUVO_UPSTREAM_BASE_URL:-http://localhost:8080}"

want_calls=1
probe_args=()
for argument in "$@"; do
  case "$argument" in
  --no-call) want_calls=0 ;;
  *) probe_args+=("$argument") ;;
  esac
done

if [[ ! -f .mcp.json ]]; then
  warn "no .mcp.json yet; the server is wired up during the exercise"
  exit 0
fi

if grep -q '"command": *"REPLACE_ME"' .mcp.json 2>/dev/null; then
  warn ".mcp.json still holds the placeholder command; nothing to probe yet"
  exit 0
fi

# A check that could not run is not a finding. If nothing is serving the
# upstream, say so and why, and check the handshake alone rather than reporting
# a failure that is about the environment rather than about the server.
if [[ "$want_calls" == "1" ]]; then
  if curl -fsS "${UPSTREAM}/__health" >/dev/null 2>&1; then
    probe_args+=("--call")
    ok "upstream serving at ${UPSTREAM}; real tool calls will be made and asserted"
  else
    want_calls=0
    warn "nothing serving at ${UPSTREAM}, so the tool calls are SKIPPED, not passed."
    warn "Start one with scripts/demo_client.sh or 'make up', then run this again."
  fi
fi

if py python -m tools.mcp_probe "${probe_args[@]+"${probe_args[@]}"}"; then
  if [[ "$want_calls" == "1" ]]; then
    record_evidence "PASS" "tool server completed the handshake and answered real tool calls correctly over the wire"
    ok "tool server responds correctly, including on the failure path"
  else
    record_evidence "PASS" "tool server completed the protocol handshake and advertised its tools (tool calls not exercised)"
    ok "tool server completed the handshake"
  fi
else
  if [[ "$want_calls" == "1" ]]; then
    record_evidence "FAIL" "tool server did not answer a real tool call as required"
  else
    record_evidence "FAIL" "tool server did not complete the protocol handshake"
  fi
  die "The tool server did not behave as required. Fix this before attaching a client."
fi
