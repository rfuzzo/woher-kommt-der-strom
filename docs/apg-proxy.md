# APG cache/proxy deployment plan

## Why this exists

GitHub-hosted Actions runners currently cannot establish a usable HTTPS connection to `transparency.apg.at`. DNS resolution succeeds and the public Swagger JSON resolves to IPv4 `91.232.233.107`, but the connection times out before any HTTP response is received.

That means the APG integration code is valid to keep, but the fetch has to run somewhere with normal reachability to APG.

## Minimal architecture

```text
APG Transparency API
        │
        │ every 15 min
        ▼
small EU-hosted fetch job
        │
        ├─ fetch AGPT / AL / CBPF / DAFTG / ALF-DALF
        ├─ atomically replace the validated cache
        ├─ build and score supply nowcasts in SQLite
        └─ export current/history JSON
        │
        ▼
https://<host>/apg/latest.json
        │
        │ every 30 min
        ▼
GitHub Actions
        │
        ├─ scripts/fetch_data.py        Energy-Charts base/fallback
        ├─ fetch cached APG JSON
        └─ scripts/overlay_apg.py       apply fresher tail
        │
        ▼
GitHub Pages
```

The cache itself is a static JSON file. The same host also keeps the nowcast
history in SQLite so collection is independent of GitHub Actions.

## Netcup VPS deployment

The production VPS files live in `proxy/vps/`:

- `apg_cache.py` fetches yesterday and today for `AGPT`, `AL`, `CBPF`, `DAFTG`
  and `ALF/DALF`, validates matching columns, and atomically replaces
  `latest.json`;
- `nowcast_store.py` records every prediction in SQLite, scores it when APG
  publishes the target interval, and atomically exports current/history JSON;
- `apg-cache.timer` starts the fetch shortly after every quarter-hour;
- `Caddyfile` serves the cache at
  `https://strom-api.rfuzzo.de/apg/latest.json` with automatic HTTPS.

APG or network failures leave the previous successful JSON file untouched.
Consumers try the VPS endpoint first and automatically use the Deno endpoint
when the VPS result is unavailable, invalid, or more than one hour old.
The VPS prediction exports are available at `/apg/nowcast.json` and
`/apg/nowcast-history.json`; GitHub Pages mirrors them but no longer owns the
mutable backtest history.

## Cache payload

The proxy stays close to APG's normalized time-series representation. Schema 4
contains `generation`, `load`, `borders`, `generationForecast` and
`loadForecast`, each with APG's `ValueColumns` and `ValueRows`, plus fetch-time
metadata. This lets the overlay and nowcast share the same parser.

## Fetch cadence

Run the EU-hosted APG fetch every 15 minutes, ideally a few minutes after each quarter-hour so APG has time to publish the interval. Keep several recent hours in the cached file so GitHub can bridge an Energy-Charts tail safely.

The GitHub Pages build can remain every 30 minutes. If APG later proves consistently fresher and stable, the site build cadence can be reconsidered separately.

## Failure behavior

The proxy should be deliberately boring:

1. Fetch `AGPT`, `AL`, `CBPF`, `DAFTG` and `ALF/DALF`.
2. Parse and validate all five, rejecting malformed data.
3. Only after every fetch succeeds, atomically replace `latest.json`.
4. Build the current supply estimate from that cache.
5. Store it, score newly available actual intervals, and atomically export JSON.
6. If a stage fails, keep serving that stage's previous successful file.

This gives two independent fallbacks:

- the proxy serves its last known good APG cache if APG is temporarily unavailable;
- GitHub Actions keeps Energy-Charts if the proxy is unavailable or not newer.

## Hosting requirements

The workload is tiny. The host only needs:

- outbound HTTPS access to `transparency.apg.at`;
- a scheduler capable of running every 15 minutes;
- static HTTPS hosting for the JSON exports;
- enough disk for the cache and the small SQLite history;
- no inbound admin API.

A small EU VPS, a serverless/edge platform with scheduled jobs, or an existing always-on machine are all sufficient. Before choosing a provider, first run the same Swagger probe from that environment. The key requirement is proven APG reachability, not compute capacity.

## Security and abuse controls

The cached endpoint can be public because it contains only public APG transparency data. Still:

- set a short CDN/browser cache lifetime, e.g. a few minutes;
- include `generatedAt` so consumers can reject stale data;
- cap APG request durations and retry counts;
- avoid exposing arbitrary upstream URL proxying;
- only serve the single normalized dataset.

## Integration into this repository

GitHub Actions reads the VPS cache first and retains Deno as an overlay-only
fallback. It logs source, schema, age and row counts, overlays the fresh actual
tail, then mirrors the VPS nowcast exports into Pages. Energy-Charts remains the
fallback whenever the cache is unavailable or incomplete.

## Current repository state

The production workflow uses `scripts/run_apg_cache_overlay.py`. Direct APG
access remains available for local diagnostics, since GitHub-hosted runners
still cannot reliably reach APG.
