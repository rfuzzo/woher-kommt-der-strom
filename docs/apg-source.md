# APG as a fresher Austrian data source

## Goal

Reduce the avoidable 2–4 hour delay in the Austrian near-current panels without giving up Energy-Charts for European context.

APG exposes Austrian generation, actual load and physical cross-border flows through its public Transparency REST API. The API contract is published as OpenAPI/Swagger at `https://transparency.apg.at/api/swagger/v1/swagger.json`.

## Implemented split

APG is now preferred for the freshness-sensitive Austrian tail:

- generation per production type via `AGPT`;
- actual total load via `AL`;
- physical cross-border flows via `CBPF`.

Energy-Charts remains the source for:

- neighbour-country generation used for import composition;
- day-ahead prices;
- European flow tracing / Sankey inputs;
- seasonal context and longer historical context;
- fallback when APG is unavailable or has no newer complete sample.

The frontend still receives the same `site/data.json` shape.

## Integration shape

`scripts/fetch_data.py` first builds the complete Energy-Charts dataset exactly as before. `scripts/overlay_apg.py` then requests roughly 30 hours of 15-minute APG data and appends only samples that are newer than the Energy-Charts `dataAt` value and complete across generation, load and physical border flow.

If APG times out, rate-limits, returns malformed data or has no newer complete interval, the overlay exits successfully without changing `data.json`. The existing Energy-Charts result therefore remains the automatic fallback.

The overlay also adds a `sources` object to `data.json` containing the APG timestamps and the Energy-Charts timestamp used as the baseline. The build log prints how many minutes fresher the selected APG sample is.

## Generation mapping

The APG `AGPT` series map into the site's existing seven groups:

- hydro: `B11` + `B12`;
- fossil: `B04` + `B05` + `B06`;
- wind: `B19`;
- solar: `SolarTotal` when present, otherwise `B16`;
- pumped storage generation: `B10`;
- biomass & waste: `B01` + `B17`;
- other: `B09` + `B15` + `B20`.

`SolarFeedIn` is deliberately not added to `SolarTotal`, because the API documents those as separate views of solar rather than additive categories.

## Cross-border semantics

APG `CBPF` is physical flow and uses the same sign convention needed by the current physical-flow panels: imports into Austria are positive. The six border series are `CZtoAT`, `DEtoAT`, `HUtoAT`, `ITtoAT`, `SItoAT` and `CHtoAT`, plus the `Sum` series.

Physical APG data does not replace the Energy-Charts commercial-trading series used for the money calculation. The valuation panel therefore remains Energy-Charts based.

## Remaining mixed-source caveats

The newest current snapshot can be APG-backed while a few slower context calculations still come from Energy-Charts. In particular:

- pumped-storage consumption remains the latest Energy-Charts value because the first APG overlay only uses generation, actual load and CBPF;
- import composition still uses neighbour generation from Energy-Charts, so its technology shares can be older than the APG net-import headline;
- the Sankey remains on its existing three-hour Energy-Charts cadence;
- prices and trade valuation remain commercial-market data from Energy-Charts.

These are kept separate rather than silently treating differently scoped quantities as interchangeable.

## Validation

The deployment workflow runs Energy-Charts first and APG second, then applies the existing data-integrity checks. The APG overlay rejects incomplete common intervals and implausible generation jumps before extending the public series.

The `sources` diagnostics make it possible to measure the real freshness improvement over subsequent scheduled builds before removing any redundant Energy-Charts fetches.

## Architecture

```text
Energy-Charts ─── full dataset / Europe / prices / history / tracing
                        │
                        ▼
                scripts/fetch_data.py
                        │
                        ▼
                   site/data.json
                        │
APG ───── AGPT / AL / CBPF (newer complete 15-minute tail)
                        │
                        ▼
               scripts/overlay_apg.py
                        │
                        ▼
                   site/data.json
```
