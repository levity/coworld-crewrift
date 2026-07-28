# Observatory episode-artifact endpoint map

The authoritative live route list is always `<base>/openapi.json`. Read it when a
route 4xxs — **the server moves faster than the published `coworld` client**, and
this skew is the single most common cause of artifact-download breakage here.

`<base>` defaults to the official gateway derived from your `softmax login`:
`<api-server>/observatory` (today `https://softmax.com/api/observatory`). The same
routes are also served directly at `https://api.observatory.softmax-research.net`
(root, no `/observatory` segment); pass `--server` to switch.

Auth: `X-Auth-Token: <token>` header. In Python use
`softmax.auth.load_current_token(server=softmax.auth.get_api_server())` — **not**
the removed `load_current_cogames_token(api_server=...)` (see "Drift" below).

## The two episode populations

| | League / tournament episodes | Experience-request episodes |
| --- | --- | --- |
| What | League round games (e.g. a Crewrift league) | Ad-hoc / commissioner-created hosted episodes |
| Listed by | `/stats/policy-versions` → `/episodes?policy_version_id=` | `/v2/episode-requests` (by container) or `/v2/experience-requests/{xreq}/episodes` |
| Id form | bare uuid (`/episodes/{uuid}`) | `ereq_...` |
| Metadata record | `/episodes/{id}` → `replay_url`, `policy_results`, `game_stats`, `tags` | the row itself → `participants`, `scores`, `status`, `replay_url`, `game_config` |
| `job_id` | in `tags.job_id` | top-level `job_id` field |

They are **disjoint populations**: a league episode's `pool_id` returns **0** rows
from `/v2/episode-requests?pool_id=`, and `coworld episodes --policy <league-player>`
is empty. Don't try to cross them — discover each in its own world.

## Artifact routes — one family, for both populations

**Both populations serve their artifacts from the ownership-aware
`/v2/episode-requests/...` routes** (verified live 2026-07-28). The two populations differ
only in how you get the `ereq_...` handle: an experience-request episode already is one, and
a league episode resolves to one through its job.

| Route | Returns |
| --- | --- |
| `GET /v2/episode-requests/by-job/{job_id}` | `{"episode_request_id": "ereq_..."}` — the league episode's handle, from `tags.job_id` |
| `GET /v2/episode-requests/{ereq}/artifacts/{results,replay}` | game result or replay artifact |
| `GET /v2/episode-requests/{ereq}/policy-artifacts` | owned slots with `policy_version_id`, `has_log`, and `has_artifact` |
| `GET /v2/episode-requests/{ereq}/{policy_version_id}/policy-logs/{agent_idx}` | one owned slot's stderr |
| `GET /v2/episode-requests/{ereq}/{policy_version_id}/policy-artifact/{agent_idx}` | one owned slot's telemetry ZIP |

So a **league episode yields results, per-agent logs and your own telemetry zips**, exactly
like one you requested yourself. `fetch_artifacts.py` does the `by-job` hop for you.

The replay decompresses (zlib) to the game's binary replay (e.g. magic `CREWRIFT...`) — the
directly-loadable form. Keep the raw `.z` too.

**Do not reach for `/jobs/{job_id}/...`.** Those routes are restricted to Softmax team
members and answer **403** to a normal player author; `/jobs/{job_id}/policy-artifact` is
gone (404). A 403 is easy to misread as an absent artifact — most clients here wrap GETs in
a best-effort helper that returns `None` on any 4xx — so **check the status code before
concluding an artifact does not exist.** Reading a 403 as "league play has no results" is
a mistake that has cost this project real money in unnecessary experience requests.

### Dead ends (do not use)
- `GET /v2/experience-request-episodes...` — **gone** (renamed away ~2026-06; an
  older `fetch_episodes.py` keyed logs off this and now fails here).
- `coworld_id` / `job_id` / `episode_id` as query params on `/v2/episode-requests`
  are **silently ignored** (not real filters). Only `pool_id`, `round_id`,
  `division_id`, `player_id` filter server-side. A **bare** pool uuid 422s — the
  value must carry the `pool_` prefix.

## Discovery routes

```
GET /stats/policy-versions?name_exact=<name>&limit=100      -> [{id, version, policy_id, ...}]
GET /episodes?policy_version_id=<pv>&limit&offset           -> [episode record, ...]
GET /episodes/{episode_id}                                  -> single league episode record
GET /v2/episode-requests?pool_id=pool_<uuid>|round_id|division_id|player_id&limit&offset
                                                           -> {entries, total_count, limit, offset}
GET /v2/episode-requests/{ereq_id}                          -> single experience-request episode row
GET /v2/experience-requests/{xreq_id}/episodes             -> [experience-request episode row, ...]
GET /v2/experience-requests?mine&limit&offset              -> {entries, ...} (the xreq batteries, not episodes)
```

`/episodes` and `/stats/policy-versions` return bare lists (the latter may also be
`{entries:[...]}`). `/v2/episode-requests` is paginated as
`{entries, total_count, limit, offset}` — `total_count` is the whole table
(hundreds of thousands), so always filter by a container; never page it blindly.

## Official `coworld` CLI equivalents (for interactive use)

These work today against the live server (they hit `/v2/episode-requests/...`)
but only cover the experience-request world:

```bash
uv run coworld episodes --pool pool_... --json       # list ereq episodes
uv run coworld replays  --round round_... --download-dir replays/
uv run coworld episode-results ereq_... --output results.json
uv run coworld episode-logs ereq_... --download-dir logs/
uv run coworld replay <coworld_id> <replay_file>     # open a replay in the viewer
```

For league episodes by policy, and for bundling everything per episode in one
pass, use this skill's `fetch_artifacts.py` instead.

## Drift log (why this file exists)

- **2026-07-22**: XP consumption moved to ownership-scoped
  `/v2/episode-requests/...` routes. Verified a current XP player-artifact ZIP
  and policy log live; the former job-based downloader had silently treated
  403/404 responses as missing optional telemetry.
- **2026-07-28**: league episodes resolve to an `ereq_...` through
  `/v2/episode-requests/by-job/{job_id}` and serve results, per-agent logs and owned
  telemetry zips from the same `/v2/episode-requests/...` family as experience requests.
  Verified live on a league game: per-seat results and a 133,769-line `telemetry.jsonl`.
  `fetch_artifacts.py` now does the hop; the `/jobs/...` fallback stays only for the
  team-member case.
- **2026-06-27**: re-verified the discovery split live — `coworld episodes --policy crewborg`
  returns `[]` (champion league player), while `/stats/policy-versions` → `/episodes` lists its
  league games (the `fetch_artifacts.py --policy` path downloaded a current league episode). The
  two-population **discovery** model still holds.
- **2026-06-10**: added the per-player artifact routes
  (`/jobs/{job_id}/policy-artifact[/{agent_idx}]`) — players may upload one
  telemetry/debug zip per slot to a runner-provided
  `COWORLD_PLAYER_ARTIFACT_UPLOAD_URL` (metta #15290; player-side support in the
  players SDK's `TraceOutputs`). **Verified live 2026-06-10** against crewborg v18
  hosted episodes (after metta #15409 fixed the runner-image build so the upload
  actually ships). Note the listing returns **filenames**, not slot ints.

- **2026-06**: `/v2/episode-requests*` ↔ `/v2/experience-request*` churn; the
  `/v2/experience-request-episodes` route was removed.
- **~2026-06 (auth)**: `softmax.auth.load_current_cogames_token(api_server=...)` →
  `softmax.auth.load_current_token(server=...)`. The old name is gone; tools that
  still call it (e.g. an older `crewrift/crewborg/scripts/fetch_episodes.py`) fail at auth
  until updated.

When you hit drift: diff `<base>/openapi.json` against the routes above, fix the
path, and add a dated line here.
