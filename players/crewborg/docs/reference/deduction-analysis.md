# Deduction analysis workflow

This workflow evaluates the append-only deduction path without manually reading
every replay. Run commands from the repository root with a Python environment
that contains crewborg's production dependencies plus `duckdb`. Put the policy
package first on `PYTHONPATH`; do not prepend an old vendored player SDK:

```sh
export PYTHONPATH=players/crewborg:.
```

Synthetic and public-history results are regression instruments, not game-win
estimates. Public warehouses cannot reconstruct private screen observations,
and synthetic histories only test the behaviors represented by their generator.

## Synthetic evaluation

The fast production-policy summary is deterministic:

```sh
python players/crewborg/tools/evaluate_deduction.py --games 1000 --seed 7
```

For diagnosis, run the audit over the same generated histories. It reports the
default policy, vote-weight and repeat-decay counterfactuals, decision reasons,
wrong-vote profiles, and a bounded set of compact timelines:

```sh
python players/crewborg/tools/analyze_deduction_synthetic.py \
  --games 1000 --seed 7 --samples 5 > /tmp/deduction-synthetic-audit.json

jq '.variants | map_values(del(.wrong_samples, .decision_reasons))' \
  /tmp/deduction-synthetic-audit.json
jq '.variants.default.wrong_samples' /tmp/deduction-synthetic-audit.json
```

Change one generator or inference parameter at a time. Compare variants on the
same generated games, and require both precision and retained correct coverage;
an apparent gain from abstaining is not sufficient.

`evaluate_deduction.py` also accepts typed `InferenceConfig` overrides for one
offline counterfactual without editing production defaults:

```sh
python players/crewborg/tools/evaluate_deduction.py \
  --warehouse /tmp/<arm>-warehouse \
  --inference-config '{"repeat_decay":0.4,"same_target_decay":0.55}'
```

## Hosted replay warehouse

Build `expand_replay` at the exact Crewrift version recorded by the hosted
episode. The companion `.source` directory is a required runtime resource and
must remain beside the binary:

```sh
players/crewborg/tools/build_expand_replay.sh \
  --ref <crewrift-version> --out /tmp/expand-<crewrift-version>
```

Stream each request into its own warehouse. On a small VM, overlap downloads
but serialize full-tick expansion; two workers is the established 2-vCPU
starting point:

```sh
S=players/crewborg/skills/crewrift-event-warehouse/scripts/stream_eval.py

python "$S" --xreq <xreq-id> --out /tmp/<arm>-warehouse \
  --expand-replay /tmp/expand-<crewrift-version> --workers 2
```

Before behavioral analysis, inspect `manifest.json`, failed episode counts,
`trace_complete`, and `trace_warning`. Authoritative XP outcomes may retain a
warning episode, but event-derived behavior must exclude its partial timeline.
`evaluate_deduction.py` performs that exclusion automatically.

## Same-history comparison

Run both implementations at the same standard tick-1152 cutoff. `--details`
can be large, so redirect it to JSON:

```sh
python players/crewborg/tools/analyze_solver_history.py \
  /tmp/<arm>-warehouse --details --early-chat \
  --out /tmp/<arm>-legacy.json

python players/crewborg/tools/evaluate_deduction.py \
  --warehouse /tmp/<arm>-warehouse --details \
  > /tmp/<arm>-deduction.json

python players/crewborg/tools/compare_deduction_decisions.py \
  /tmp/<arm>-legacy.json /tmp/<arm>-deduction.json \
  > /tmp/<arm>-comparison.json

jq 'del(.disagreements)' /tmp/<arm>-comparison.json
jq '.disagreements' /tmp/<arm>-comparison.json
```

Analyze each hosted arm separately before pooling because treatment and control
produce different game trajectories. The join key is `(episode_id,
meeting_id)`. Compare selection precision, coverage, dropped correct decisions,
added errors, parity thresholds, source composition, and the underlying active
evidence. The new detailed output includes marginals and active claim/vote
factors specifically so disagreement inspection does not require rerunning the
warehouse query.

## Interpretation limits

- XP outcomes and event-derived behavior use different denominators when a
  replay is incomplete; state both.
- Public-history comparison excludes private witness pins, watched actions, and
  any unavailable policy telemetry.
- A same-history solver improvement is evidence about decision logic, not proof
  of a crew-win improvement.
- Threshold sweeps reuse the evaluation set. Treat them as diagnostics and
  confirm proposed behavior on held-out history before another hosted run.
