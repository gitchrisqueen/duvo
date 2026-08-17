---
description: Post-recording checks before the repository and video are submitted
---

The recording has stopped. Run `scripts/finalize.sh` and work through what it
prints.

It checks the things that are expensive to miss:

- No secret ever entered the git history, across all branches.
- No personal reference material was committed.
- Nothing under `secrets/` is tracked except the placeholder.
- The documentation still passes the prose guard and every documented command
  still runs.

Then, in order, and none of it skipped:

1. Play the recording back and confirm it captured both camera and audio.
2. Make the repository public.
3. Open the repository link in a private browser window and click through
   `README.md` and `DEPLOYMENT.md` as a stranger would.
4. Follow `DEPLOYMENT.md` from a clean clone in a scratch directory. This is the
   step that catches anything that only works because of your machine.
5. Upload the recording, then send the recording and the link.

Send nothing until steps three and four have actually been done.

$ARGUMENTS
