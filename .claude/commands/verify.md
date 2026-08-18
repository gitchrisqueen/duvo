---
description: Run the full verification sweep and strip every unsupported claim
---

This is the freeze. Nothing new is built from here.

1. Run `scripts/verify_all.sh` and read the output rather than skimming it.
2. Invoke `qa-verifier`. Accept the evidence table exactly as reported. A stage
   that did not run is recorded as not verified, never as passing.
3. Invoke `doc-truth-auditor` over `README.md`, `DEPLOYMENT.md`, and `docs/`.
   Every capability claim needs code behind it and an evidence row supporting
   it. Anything else is downgraded or deleted.
4. Check that every documented command carries a `<!-- verify -->` marker, so it
   is executed rather than trusted.
5. Run `scripts/walkthrough.sh` to rehearse the demonstration headlessly. A
   command that fails here is cut from the walkthrough rather than attempted
   live.

A smaller verified result beats a larger unverified one, every time.

Time check: the freeze runs from minute forty five to minute fifty.

$ARGUMENTS
