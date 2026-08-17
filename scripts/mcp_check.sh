#!/usr/bin/env bash
# Prove the tool server speaks the protocol before any assistant is attached.
#
# Order of operations during the exercise: run this, read the output, fix what
# is broken, and only then connect a client. Debugging a transport through a
# language model is the slowest route to an answer that exists.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

if [[ ! -f .mcp.json ]]; then
  warn "no .mcp.json yet; the server is wired up during the exercise"
  exit 0
fi

if grep -q '"command": *"REPLACE_ME"' .mcp.json 2>/dev/null; then
  warn ".mcp.json still holds the placeholder command; nothing to probe yet"
  exit 0
fi

if py python -m tools.mcp_probe "$@"; then
  record_evidence "PASS" "tool server completed the protocol handshake and advertised its tools"
  ok "tool server responds correctly"
else
  record_evidence "FAIL" "tool server did not complete the protocol handshake"
  die "The tool server did not complete the handshake. Fix this before attaching a client."
fi
