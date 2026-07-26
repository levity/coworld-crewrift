#!/usr/bin/env python3
"""Offline sweep: does per-speaker trust beat a blanket evidence-class gate?

WHY. The deduction posterior treats every crewmate's claim and vote with one global
likelihood pair (`crew_accuse_hit=0.58` vs `crew_accuse_miss=0.15`). That says any
crewmate accuses a real impostor ~4x more often than an innocent. In the A/B rosters
that was literally true -- all six crew seats ran this policy. In LEAGUE play five of
six crewmates are foreign policies, some of which target on 100% of their ballots, so
their true ratio is 1.0 and we are reading pure noise as 4:1 evidence. Measured over
60 league episodes: non-structural ejects were 5/19 (26%) correct, against ~29% for
voting at random, and the posterior inside that class was *anti*-informative (mean
0.786 when right, 0.798 when wrong).

WHAT THIS DOES. Re-scores the recorded posteriors under a per-speaker trust factor
`tau`, without replaying any games. `MeetingDecision.as_trace` serialises the complete
evidence list (source, channel, stance, targets, status, weight) plus `pins`,
`excluded` and the resulting `marginals`, which is everything needed to rebuild the
log-weight over all C(8,2)=28 role assignments.

Trust is applied as TEMPERING -- `weight *= tau` -- not as per-speaker likelihood
parameters. Tempering shrinks evidence toward neutral, `tau=0` exactly reproduces
"ignore this speaker", it is monotone, and unlike mis-set likelihood parameters it
cannot manufacture a confidently wrong posterior.

    uv run python tools/sweep_speaker_trust.py <episodes-with-artifacts> ...

FIRST it self-checks: the reconstruction must reproduce the recorded marginals. A
sweep over a model that is not the shipped policy would be worse than no sweep, so
the check is not optional and the tool refuses to report if it fails.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crewborg.deduction.inference import InferenceConfig  # noqa: E402

SLOT_COLORS = ("red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan")
IMPOSTER_COUNT = 2
CFG = InferenceConfig()


# ---------------------------------------------------------------- likelihoods
# Mirrors _actor_claim_probability / _vote_probability. Imported config so the
# constants cannot drift from the policy; the SHAPE is duplicated here and that is
# exactly what the self-check below is guarding.
def claim_likelihood(hyp: frozenset[str], source: str, targets: tuple[str, ...],
                     stance: str) -> float:
    actor_imp = source in hyp
    target_imp = any(t in hyp for t in targets)
    if stance in {"accuse", "at_least_one"}:
        if actor_imp:
            return CFG.imp_accuse_partner if target_imp else CFG.imp_accuse_crew
        return CFG.crew_accuse_hit if target_imp else CFG.crew_accuse_miss
    if actor_imp:
        return CFG.imp_defend_partner if target_imp else CFG.imp_defend_crew
    return CFG.crew_defend_imp if target_imp else CFG.crew_defend_crew


def vote_likelihood(hyp: frozenset[str], voter: str, target: str) -> float:
    voter_imp = voter in hyp
    target_imp = target in hyp
    if voter_imp:
        return CFG.imp_vote_partner if target_imp else CFG.imp_vote_crew
    return CFG.crew_vote_imp if target_imp else CFG.crew_vote_crew


def rescore(players: list[str], evidence: list[dict], excluded: set[frozenset[str]],
            tau: dict[str, float] | None) -> dict[str, float]:
    """Marginal P(color is impostor) over all surviving role assignments."""
    log_w: dict[frozenset[str], float] = {}
    for pair in itertools.combinations(sorted(players), IMPOSTER_COUNT):
        hyp = frozenset(pair)
        if hyp in excluded:
            continue
        total = 0.0
        for ev in evidence:
            if ev.get("status") != "active":
                continue
            src, tgts = ev.get("source"), tuple(ev.get("targets") or ())
            if not src or not tgts:
                continue
            w = float(ev.get("weight") or 0.0)
            if tau is not None:
                w *= tau.get(src, 1.0)
            if w <= 0.0:
                continue
            ch = ev.get("channel")
            if ch == "vote":
                like = vote_likelihood(hyp, src, tgts[0])
            elif ch == "claim":
                like = claim_likelihood(hyp, src, tgts, ev.get("stance") or "accuse")
            else:
                continue  # direct / alibi act through pins + `excluded`, not weights
            total += w * math.log(max(like, 1e-9))
        log_w[hyp] = total
    if not log_w:
        return {}
    hi = max(log_w.values())
    wts = {h: math.exp(v - hi) for h, v in log_w.items()}
    z = sum(wts.values())
    out = collections.defaultdict(float)
    for h, w in wts.items():
        for c in h:
            out[c] += w / z
    return dict(out)


# ---------------------------------------------------------------- loading
def load(roots: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for root in roots:
        for ep in sorted(p for p in root.iterdir() if p.is_dir()):
            res = ep / "results.json"
            if not res.is_file():
                continue
            truth = {SLOT_COLORS[i] for i, v in
                     enumerate(json.loads(res.read_text()).get("imposter") or []) if v}
            if not truth:
                continue
            deaths: dict[str, int] = {}
            seats: list[list[dict]] = []
            for z in sorted((ep / "artifacts").glob("*.zip")):
                try:
                    raw = zipfile.ZipFile(z).read("telemetry.jsonl")
                except (OSError, KeyError, zipfile.BadZipFile):
                    continue
                lines = []
                for ln in raw.decode("utf8", "ignore").splitlines():
                    if ln.strip():
                        try:
                            lines.append(json.loads(ln))
                        except json.JSONDecodeError:
                            pass
                for r in lines:
                    if r.get("event") == "domain.player_died":
                        d = r.get("data") or {}
                        if d.get("color") and d.get("death_tick") is not None:
                            deaths[d["color"]] = min(deaths.get(d["color"], 1 << 30),
                                                     d["death_tick"])
                seats.append(lines)
            for lines in seats:
                for r in lines:
                    if r.get("event") != "domain.deduction_history_decision":
                        continue
                    dec = (r.get("data") or {}).get("decision") or {}
                    inf = dec.get("inference") or {}
                    marg = inf.get("marginals")
                    if not isinstance(marg, dict) or not marg:
                        continue
                    missing = [c for c in SLOT_COLORS if c not in marg]
                    self_color = missing[0] if len(missing) == 1 else None
                    tick = r.get("tick") or 0
                    # A ghost's decision never reaches the ballot box.
                    if self_color and deaths.get(self_color, 1 << 30) < tick:
                        continue
                    rows.append({
                        "episode": ep.name,
                        "tick": tick,
                        "self": self_color,
                        "truth": truth,
                        "recorded_marginals": {k: float(v) for k, v in marg.items()},
                        "evidence": inf.get("evidence") or [],
                        "pins": set(inf.get("pins") or ()),
                        "excluded": {frozenset(x.get("imposters") or ())
                                     for x in (inf.get("excluded") or [])},
                        "structural": bool(dec.get("structural")),
                        "action": dec.get("action"),
                        "target": dec.get("target"),
                        "alive": {c for c in SLOT_COLORS
                                  if deaths.get(c, 1 << 30) >= tick},
                    })
    return rows


def players_of(row: dict) -> list[str]:
    """Candidate impostors = every player EXCEPT self.

    The seat knows its own role, so no surviving assignment contains it -- which is
    exactly why `marginals` carries 7 entries, not 8. Putting self back into the
    hypothesis space was the first reconstruction bug: it handed self a 0.77 marginal
    and diluted everyone else.
    """
    return sorted(row["recorded_marginals"])


# ---------------------------------------------------------------- self-check
def self_check(rows: list[dict], tol: float) -> tuple[int, int, float]:
    ok = worst_n = 0
    worst = 0.0
    for row in rows:
        got = rescore(players_of(row), row["evidence"], row["excluded"], None)
        if not got:
            continue
        err = max(abs(got.get(c, 0.0) - p)
                  for c, p in row["recorded_marginals"].items())
        worst = max(worst, err)
        if err <= tol:
            ok += 1
        else:
            worst_n += 1
    return ok, worst_n, worst


# ---------------------------------------------------------------- trust models
def selectivity_tau(rows: list[dict], prior: float, k: float
                    ) -> dict[tuple[str, str], float]:
    """tau per (episode, speaker) from how SELECTIVELY they vote.

    The best-powered signal available, and it needs no ground truth: every player's
    ballot is visible at every meeting, and the trace keeps skipped ballots too (as
    ignored evidence, "skip vote has no target likelihood"). So the targeting RATE is
    directly observable per speaker.

    Why rate is the right statistic: a speaker who targets on a fraction f of ballots
    cannot support a likelihood ratio far from 1 as f -> 1, because P(accuse | X is
    impostor) and P(accuse | X is crew) converge. Eva-00 targets on 100% of its
    ballots and shrike on 95%; the field's most accurate crew policy targets on 19%.
    tau = 1 - rate captures exactly that, with no fitted parameter.

    Shrunk toward `prior` with pseudo-count `k` because a speaker is only seen a few
    times per episode. `prior` is the load-bearing knob: the shipped model is
    effectively tau=1 for every stranger, and simply lowering that is most of the fix.
    When policy identity becomes visible per player, `prior` is what becomes
    per-policy and carries across games; nothing else here changes.
    """
    ballots: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter)
    for row in rows:
        for ev in row["evidence"]:
            src = ev.get("source")
            if not src or ev.get("channel") != "vote":
                continue
            c = ballots[(row["episode"], src)]
            c["n"] += 1
            if ev.get("targets"):
                c["targeted"] += 1
    out = {}
    for key, c in ballots.items():
        n = c["n"]
        raw = 1.0 - (c["targeted"] / n if n else 0.0)
        out[key] = (n * raw + k * prior) / (n + k)
    return out


# ---------------------------------------------------------------- evaluation
def _auc(pairs: list[tuple[float, int]]) -> float | None:
    pos = [s for s, y in pairs if y]
    neg = [s for s, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = ties = 0
    for p in pos:
        for q in neg:
            wins += p > q
            ties += p == q
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def causal_tau(row: dict, prior: float, k: float) -> dict[str, float]:
    """tau from ONLY the evidence this decision actually had in hand.

    The episode-level estimator is lookahead: it aggregates every ballot in the
    episode, including ones cast after the decision being scored, which the policy
    obviously cannot see. Each decision's own trace is cumulative up to that decision,
    so estimating from it is exactly what `inference._speaker_trust` does at runtime.
    """
    seen: dict[str, list[int]] = {}
    for ev in row["evidence"]:
        src = ev.get("source")
        if not src or ev.get("channel") != "vote":
            continue
        c = seen.setdefault(src, [0, 0])
        c[0] += 1
        if ev.get("targets"):
            c[1] += 1
    return {s: ((n * (1.0 - t / n)) + k * prior) / (n + k)
            for s, (n, t) in seen.items() if n}


def evaluate(rows: list[dict], tau: dict[tuple[str, str], float] | None,
             base_probability: float, base_margin: float,
             causal: tuple[float, float] | None = None) -> dict[str, Any]:
    """Re-score every decision, re-apply the `loose` gate, and score the result."""
    pairs: list[tuple[float, int]] = []
    stats = collections.Counter()
    for row in rows:
        per_speaker = None
        if causal is not None:
            per_speaker = causal_tau(row, *causal)
        elif tau is not None:
            per_speaker = {s: t for (e, s), t in tau.items() if e == row["episode"]}
        marg = rescore(players_of(row), row["evidence"], row["excluded"], per_speaker)
        live = {c: p for c, p in marg.items() if c in row["alive"]}
        if not live:
            continue
        for c, p in live.items():
            pairs.append((p, 1 if c in row["truth"] else 0))
        ranked = sorted(live.items(), key=lambda kv: (-kv[1], kv[0]))
        target, prob = ranked[0]
        outside = ranked[IMPOSTER_COUNT][1] if len(ranked) > IMPOSTER_COUNT else 0.0
        if prob < base_probability or (prob - outside) < base_margin:
            continue
        cls = "structural" if row["structural"] else "nonstructural"
        stats[cls] += 1
        stats[cls + "_hit"] += target in row["truth"]
    return {
        "auc": _auc(pairs),
        "structural": stats["structural"], "structural_hit": stats["structural_hit"],
        "nonstructural": stats["nonstructural"],
        "nonstructural_hit": stats["nonstructural_hit"],
    }


def _line(label: str, r: dict[str, Any]) -> str:
    ns, nsh = r["nonstructural"], r["nonstructural_hit"]
    st, sth = r["structural"], r["structural_hit"]
    tot, toth = ns + st, nsh + sth
    f = lambda h, n: f"{100*h/n:5.0f}%" if n else "   --"
    auc = f"{r['auc']:.3f}" if r["auc"] is not None else "  --"
    return (f"{label:26s} {auc:>6s} {st:6d} {f(sth,st):>7s} {ns:7d} {f(nsh,ns):>7s} "
            f"{tot:7d} {f(toth,tot):>7s}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", type=Path, nargs="+")
    ap.add_argument("--tol", type=float, default=0.02,
                    help="max marginal error for the reconstruction self-check")
    ap.add_argument("--min-ok", type=float, default=0.90,
                    help="fraction of decisions that must reconstruct within --tol")
    ap.add_argument("--p", type=float, default=0.65, help="base_probability")
    ap.add_argument("--margin", type=float, default=1e-3, help="base_margin")
    args = ap.parse_args()

    rows = load(args.episodes)
    print(f"living-seat decisions with a posterior: {len(rows)}\n")
    if not rows:
        raise SystemExit("nothing to sweep")

    ok, bad, worst = self_check(rows, args.tol)
    frac = ok / max(ok + bad, 1)
    print(f"RECONSTRUCTION SELF-CHECK  (must pass before any sweep is meaningful)")
    print(f"  within {args.tol}: {ok}/{ok+bad} = {100*frac:.1f}%   worst error {worst:.4f}")
    if frac < args.min_ok:
        print(f"\n  ✗ FAILED. The offline re-scorer does not reproduce the shipped "
              f"policy's posterior,\n    so any tau sweep would be measuring a "
              f"different model. Fix the reconstruction\n    (likely: relayed-claim "
              f"provenance, or an evidence channel not modelled here)\n    before "
              f"trusting these numbers.")
        raise SystemExit(1)
    print("  ✓ reconstruction matches the recorded posterior\n")

    print(f"Gate held at the shipped `loose` values (p>={args.p}, margin>={args.margin}).")
    print("Structural ejects are shown for completeness; trust does not gate them.\n")
    print(f"{'trust model':26s} {'AUC':>6s} {'struct':>6s} {'prec':>7s} "
          f"{'nonstr':>7s} {'prec':>7s} {'total':>7s} {'prec':>7s}")
    print("-" * 84)
    print(_line("none (shipped)", evaluate(rows, None, args.p, args.margin)))

    # Flat tau: no estimation at all, just distrust every stranger equally. This is
    # the honest baseline -- any adaptive model has to beat it to justify itself.
    for t in (0.75, 0.5, 0.25, 0.0):
        flat = {(r["episode"], s): t for r in rows for s in
                {e.get("source") for e in r["evidence"] if e.get("source")}}
        print(_line(f"flat tau={t}", evaluate(rows, flat, args.p, args.margin)))

    # Selectivity-derived, shrunk toward a prior.
    for prior in (0.5, 0.25):
        for k in (2.0, 5.0):
            tau = selectivity_tau(rows, prior=prior, k=k)
            print(_line(f"selectivity p={prior} k={k:g}",
                        evaluate(rows, tau, args.p, args.margin)))

    print("\nAUC is over every living candidate in every decision (the posterior's")
    print("ranking quality). Precision columns are ejects the gate would have cast.")
    print("NOTE: ~4% of decisions do not reconstruct exactly (relayed-claim provenance")
    print("is not serialised), so treat small differences as noise.")


if __name__ == "__main__":
    main()
