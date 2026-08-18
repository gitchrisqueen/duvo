# 2. Agents do not use worktree isolation during the session

Status: accepted

## Context

An assistant agent can be given its own git worktree, so that several agents
editing files in parallel cannot collide. For a large refactor across many
files, that is genuinely useful.

## Decision

No agent sets worktree isolation during the recorded exercise.

Three reasons, in order of weight:

1. **The container stack breaks.** `docker-compose.yml` mounts `./secrets` and
   `./fixtures` by relative path. An agent working in a separate checkout either
   mounts a different copy or fails outright, and finding that out at minute
   forty is expensive.
2. **The scripts assume one repository root.** `scripts/_lib.sh` resolves the
   root from its own location and every other script inherits it. Two roots means
   verification evidence written in one place and read from another.
3. **Only one agent writes at a time.** The agent budget allows three
   invocations while building, and only `implementer` and `unit-tester` can
   write at all. The collision that isolation prevents cannot occur.

## Consequences

Agents share the working tree, which is what the scripts, the stack, and the
demonstration all expect. Worktree isolation stays available for experimentation
outside the session, where the container stack is not running.

The cost is real but small: if two writing agents were ever run concurrently
they could conflict. The mitigation is the agent budget itself, which exists for
other reasons anyway.
