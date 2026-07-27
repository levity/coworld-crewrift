# The improvement loop — moved

The runbook now lives **outside this repo**, at `~/projects/softmax/improvement-loop.md`.

`coworld-crewrift` is an inherited fork and `players/crewborg` is an inherited player.
The loop is a working practice that is expected to outlive both, so it sits alongside
them rather than inside them. It is split into a portable Part 1 (the loop itself) and a
Part 2 that carries the crewborg-specific commands this file used to hold.

The path is deliberately not a relative link: it resolves outside the repository, and
this file is also read from `.claude/worktrees/*`, where a relative hop would land
somewhere else.

This stub stays so the docs here do not dead-end.
