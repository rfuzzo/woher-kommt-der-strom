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
        ├─ fetch AGPT / AL / CBPF
        ├─ validate newest complete 15-min interval
        ├─ normalize to one compact JSON payload
        └─ atomically replace a cached JSON file
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

The cache host does not need a database. A single static JSON file is enough.

## Cache payload

Keep the proxy output close to APG's normalized time-series representation rather than mirroring the whole website payload. Suggested shape:

```json
{
  "generatedAt": "2026-08-09T14:45:12+02:00",
  "source": "apg",
  "resolution": 900,
  "generation": {
    "t": [1786285800],
    "groups": {
      "hydro": [3100.0],
      "fossil": [700.0],
      "wind": [540.0],
      "solar": [1450.0],
      "pumped": [120.0],
      "biomass": [260.0],
      "other": [40.0]
    }
  },
  "load": {
    "t": [1786285800],
    "mw": [4920.0]
  },
  "physicalFlow": {
    "t": [1786285800],
    "netMw": [310.0],
    "borders": {
      "CZtoAT": [100.0],
      "DEtoAT": [220.0],
      "HUtoAT": [-80.0],
      "ITtoAT": [30.0],
      "SItoAT": [25.0],
      "CHtoAT": [15.0]
    }
  }
}
```

The numeric values above are illustrative only; the production fetcher should always use APG values.

## Fetch cadence

Run the EU-hosted APG fetch every 15 minutes, ideally a few minutes after each quarter-hour so APG has time to publish the interval. Keep several recent hours in the cached file so GitHub can bridge an Energy-Charts tail safely.

The GitHub Pages build can remain every 30 minutes. If APG later proves consistently fresher and stable, the site build cadence can be reconsidered separately.

## Failure behavior

The proxy should be deliberately boring:

1. Fetch `AGPT`, `AL`, and `CBPF`.
2. Parse and validate all three.
3. Find the newest complete common timestamp.
4. Reject malformed or implausible data.
5. Only after all checks pass, atomically replace `latest.json`.
6. If anything fails, keep serving the previous successful file.

This gives two independent fallbacks:

- the proxy serves its last known good APG cache if APG is temporarily unavailable;
- GitHub Actions keeps Energy-Charts if the proxy is unavailable or not newer.

## Hosting requirements

The workload is tiny. The host only needs:

- outbound HTTPS access to `transparency.apg.at`;
- a scheduler capable of running every 15 minutes;
- static HTTPS hosting for one JSON file;
- enough disk for a few kilobytes;
- no inbound admin API and no persistent database.

A small EU VPS, a serverless/edge platform with scheduled jobs, or an existing always-on machine are all sufficient. Before choosing a provider, first run the same Swagger probe from that environment. The key requirement is proven APG reachability, not compute capacity.

## Security and abuse controls

The cached endpoint can be public because it contains only public APG transparency data. Still:

- set a short CDN/browser cache lifetime, e.g. a few minutes;
- include `generatedAt` so consumers can reject stale data;
- cap APG request durations and retry counts;
- avoid exposing arbitrary upstream URL proxying;
- only serve the single normalized dataset.

## Integration back into this repository

Once a reachable cache URL exists:

1. Add an environment variable such as `APG_CACHE_URL` to the workflow.
2. Add a small fetch step that writes the cached JSON to a temporary file.
3. Update `overlay_apg.py` so it can read either live APG or the normalized cache file.
4. Keep Energy-Charts as the fallback path.
5. Log `APG cache age`, `Energy-Charts age`, and the selected source on every build.
6. After several days, compare median and p95 freshness before deciding whether the proxy is worth keeping permanently.

## Current repository state

The live APG overlay remains in `scripts/overlay_apg.py` and the connectivity diagnostic remains in `scripts/run_apg_overlay.py` for manual testing. The production Pages workflow does not call them while GitHub-hosted runners are known to time out reaching APG.
