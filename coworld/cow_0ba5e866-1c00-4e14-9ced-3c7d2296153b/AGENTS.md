# AGENTS.md

Guidance for coding agents working from this downloaded Coworld package.

## Facts

- Champion means your nominated policy version: the chosen participant you want to represent you in a league. It is not
  a claim that the policy has won the tournament.

## Start

- Read `coworld_manifest.json` before changing policy code.
- Treat `game.protocols.player`, `game.docs.pages`, `variants`, and `certification` as the local contract for this
  package.
- Run `uv run coworld run-episode ./coworld_manifest.json --timeout-seconds 120` with the bundled players before
  testing your own image.

## Policy Work

- Keep policy source in your policy project, not in this downloaded Coworld cache.
- Use the manifest path from this directory when building, running, and comparing policies.
