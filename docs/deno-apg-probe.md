# Deno Deploy APG connectivity probe

This is the first deployment test for moving APG fetching off GitHub-hosted Actions runners.

GitHub Actions can resolve `transparency.apg.at` but times out before receiving an HTTPS response. A normal Austrian mobile connection can reach both the Swagger document and the live `AGPT` Data endpoint. The live API also enforces a stricter rule than the OpenAPI description: `fromlocal` and `tolocal` must be local-midnight boundaries.

## Deploy from a phone

1. Open `https://console.deno.com` and sign in.
2. Create an organization on the Free plan.
3. Choose **New App** and connect GitHub.
4. Select `rfuzzo/woher-kommt-der-strom`.
5. Deploy branch `deno-apg-probe` for this connectivity test.
6. Set the application entrypoint to `proxy/deno/main.ts` if the UI does not detect it automatically.
7. Prefer a European deployment region if the app settings offer one.
8. Create/deploy the app.

No secrets or database are needed for this probe.

## Test

Open the app's public URL first. It should return JSON listing two endpoints.

Then open:

- `/probe` — fetches APG's Swagger JSON with an 8-second timeout.
- `/apg/today` — fetches today's Austrian `AGPT` generation data at 15-minute resolution using `00:00` to next-day `00:00` path boundaries.

A successful `/probe` response should contain `"ok": true` and HTTP status 200.

A successful `/apg/today` response should contain `"ok": true`, a nonzero `rowCount`, APG column names, and the first/last returned row. It intentionally returns only diagnostics rather than proxying the complete APG response.

## After reachability is proven

Replace this probe with the actual cache service:

1. Fetch `AGPT`, `AL`, and `CBPF` every 15 minutes.
2. Parse and validate the newest timestamp common to all three datasets.
3. Store only the last-known-good normalized result in Deno KV.
4. Serve it from `/apg/latest.json`.
5. Have GitHub Actions consume that small cached endpoint and keep Energy-Charts as fallback.

The existing `scripts/overlay_apg.py` remains the reference for normalization and dashboard merge semantics.
