# APG as a fresher Austrian data source

## Goal

Reduce the avoidable 2–4 hour delay in the Austrian near-current panels without giving up Energy-Charts for European context.

APG publishes Austrian generation and load with roughly a one-hour delay, and physical cross-border flows more quickly than the current Energy-Charts tail in practice. That makes APG a good candidate for the Austrian data where freshness matters most.

## Proposed split

Prefer APG for:

- generation per production type;
- actual total load;
- physical cross-border flows.

Keep Energy-Charts for:

- neighbour-country generation used for import composition;
- day-ahead prices;
- European flow tracing / Sankey inputs;
- seasonal context and other historical series;
- fallback when APG is unavailable or incomplete.

The frontend should continue receiving the same `site/data.json` shape. Source selection belongs in `scripts/fetch_data.py`.

## Integration shape

Add a small APG adapter that normalizes APG data into the same timestamp + series representation already used by the Energy-Charts path.

For an initial observation period, fetch both sources and compare their newest complete intervals. Prefer APG only when it is both newer and complete; otherwise keep Energy-Charts.

Expose lightweight diagnostics in `data.json`, for example the selected source and latest timestamp seen from each provider for generation, load and trade. This lets us measure the freshness gain before removing any redundant fetches.

## Important semantic checks

Before replacing individual series, verify that the scopes match:

- APG generation describes feed-in to the public grid in the APG control area; behind-the-meter PV is a separate concept.
- APG load uses the APG control-area definition and includes grid losses.
- Physical cross-border flows must not silently replace commercial trading data used for the existing money calculations.
- Pumped-storage generation and consumption must remain separated consistently with the current balance calculation.

If two sources describe materially different quantities, keep them separate instead of merging them.

## API access

APG advertises a public REST API for transparency data from 1 January 2023 onward, but the REST specification is not published directly on the public page. APG provides the specification after requesting API access through its transparency page.

The adapter should therefore be implemented only against the documented APG contract once that specification is available, rather than guessing endpoint paths or field names.

## Validation

During the initial dual-source period, record for each build:

- build time;
- newest complete APG timestamp;
- newest complete Energy-Charts timestamp;
- selected source;
- value differences at timestamps present in both sources.

Useful summary metrics are median and p95 source age, the APG-vs-Energy-Charts freshness difference, and the value deltas for overlapping intervals.

A switch is successful if APG is materially fresher without introducing more gaps or unexplained discontinuities.

## Expected architecture

```text
APG ───────────── Austrian current generation / load / physical flows
                        │
Energy-Charts ─── Europe / prices / neighbours / history / tracing / fallback
                        │
                        ▼
                scripts/fetch_data.py
                        │
                        ▼
                   site/data.json
```

This keeps the existing frontend and European calculations while reducing avoidable latency in the parts of the page that are specifically about Austria now.
