# Deno APG cache

The Deno Deploy app at `woher-kommt-der-strom.rfuzzo.deno.net` is used as a small cache between APG and GitHub Actions. GitHub-hosted runners currently time out when connecting directly to `transparency.apg.at`, while the Deno Amsterdam deployment can reach it normally.

## What it does

`proxy/deno/main.ts`:

- fetches APG `AGPT`, `AL`, and `CBPF` at 15-minute resolution;
- requests calendar-day windows because the live APG API requires `fromlocal` and `tolocal` at local midnight;
- fetches yesterday and today so the cache remains useful around midnight and while Energy-Charts is several hours behind;
- allows each APG request 30 seconds and retries once before abandoning a refresh;
- refreshes every 15 minutes with `Deno.cron()`;
- stores only the latest successful combined payload in Deno KV;
- leaves the previous value intact when any APG request fails.

Public endpoints:

- `/probe` — APG connectivity check.
- `/apg/refresh` — perform a refresh immediately (useful after deployment/setup).
- `/apg/latest.json` — return the last successfully cached payload.

## One-time Deno setup

The app needs a Deno KV database attached to its production timeline.

In `console.deno.com`:

1. Open the `woher-kommt-der-strom` app.
2. Open **Databases**.
3. Create a **Deno KV** database.
4. Attach/link it to the production app/timeline.
5. Redeploy `main` if the console requests it.
6. Open `/apg/refresh` once and verify `ok: true`.
7. Open `/apg/latest.json` and verify `schemaVersion: 1` plus non-empty generation/load/border rows.

No secret or database URL is required in application code; Deno Deploy supplies the linked KV database to `Deno.openKv()`.

## Failure behavior

The refresh builds the entire new payload first and writes it to KV only after all six APG day requests succeed. A partial APG failure therefore cannot overwrite the last-known-good cache.

GitHub integration should independently reject an empty or excessively stale cache and keep the Energy-Charts result as fallback.
