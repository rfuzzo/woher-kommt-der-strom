# Woher kommt der Strom?

A small, dependency-free page showing where Austria's electricity is coming
from right now: the generation mix, the last 24 hours by source, and the
physical flows across the borders.

Built as a static site, refreshed by GitHub Actions, served from GitHub Pages.

## How it works

```
GitHub Actions (every 30 min)
  └─ scripts/fetch_data.py   fetch + reshape + precompute
       └─ site/data.json     one blob, everything the page needs
            └─ site/         uploaded as the Pages artifact
```

The browser makes exactly one request for data and does no arithmetic on it —
every series, share and total is computed in `fetch_data.py`. `data.json` is
never committed; each Actions run rebuilds it and deploys, so the repo history
stays clean.

There is no framework, no build step and no third-party JavaScript. The charts
are hand-rolled SVG in `site/app.js`.

## Data

Everything comes from the [Energy-Charts v2 API](https://api.energy-charts.info/)
(Fraunhofer ISE), which needs no API key. It aggregates
[ENTSO-E](https://transparency.entsoe.eu/) and
[APG](https://www.apg.at/) data.

| Panel | Endpoint |
|---|---|
| Generation mix, 24 h shape, load, renewable share | `/v2/public_power?country=at` |
| Cross-border flows | `/v2/cbpf?country=at` |
| Day-ahead price | `/v2/price?bzn=AT` |

Licence: CC BY 4.0, attribution `energy-charts.info`; prices additionally
Bundesnetzagentur | SMARD.de. Both attributions render in the page footer.

### This is not real-time

Measured lag between `available_until` and the wall clock, sampled once:

| Endpoint | Resolution | Lag |
|---|---|---|
| `frequency` | 1 s | **~2 min** |
| `public_power` | 15 min | ~2 h |
| `cbpf` | 15 min | ~3 h |
| `price` (day-ahead) | 15 min | **~28 h ahead** |
| `public_power_forecast` | 15 min | ~28 h ahead |

The lag is in the source, not in this repo: APG publishes metered generation
about an hour behind, and ENTSO-E aggregation adds more. Refreshing faster
than every 30 minutes would buy nothing. The page therefore shows the data
timestamp and the publication lag instead of implying it is live, and
`available_until` decides which sample is the newest usable one.

Two things could make the page feel closer to now, neither shipped yet:

- **Grid frequency** is effectively live at 1 s resolution (Austria is in the
  RG Continental Europe synchronous area, so it is the same frequency as
  Germany). It cannot be fetched from the browser — the API sends
  `access-control-allow-origin: https://www.api.energy-charts.info`, so a
  direct client-side call is blocked and it would need either the Actions
  rebuild (which reintroduces cron lag) or a small proxy.
- **Solar forecast** for Austria runs ~28 h ahead, which would cover the
  trailing gap between the last measured sample and now.

### Two gotchas worth knowing

- **`cbpf` is in GW, `public_power` is in MW.** The fetcher normalises via each
  response's declared `unit` instead of assuming a scale.
- **Generation + imports does not equal load.** The two come from different
  scopes and the residual covers pumping, network losses and industrial
  self-supply. Rather than force a reconciliation, the 24 h chart stacks
  generation and draws load as a separate line — where the line sits below the
  stack, Austria is a net exporter.

## Colours

The categorical palette is not hand-picked. The seven groups map to slots that
were checked with the data-viz validator — lightness band, chroma floor,
colourblind separation (protan/deutan), normal-vision floor and contrast — in
both light and dark mode:

```
worst adjacent CVD ΔE   9.1 light / 8.4 dark   (target ≥ 8)
worst adjacent normal   19.6 light / 19.3 dark (floor ≥ 15)
```

**The stack order in `ORDER` (app.js) and `GROUPS` (fetch_data.py) is the order
that was validated.** Reordering the groups changes which colours sit next to
each other and voids that result — re-run the validator if you do.

Three light-mode series fall below 3:1 against the surface, so the page ships
the required relief: every value is directly labelled in the legend and the
mix also has a table view.

## Running locally

```bash
python3 scripts/fetch_data.py && python3 -m http.server 8931 --directory site
```

Then open <http://localhost:8931>.

## Credit

The idea of a single, calm page that just answers "where is the power coming
from" is borrowed from [holadelej.hu](https://holadelej.hu/), which does this
for Hungary. This is an independent implementation for Austria — no design,
markup or copy was taken from it. If you like this, go look at theirs.

Built with the help of [Claude Code](https://claude.com/claude-code).

## Possible next steps

- Hydro reservoir levels and river flow from [ehyd.gv.at](https://ehyd.gv.at/)
  (CC BY 4.0), the Austrian analogue of the Hungarian site's Danube panel.
- Grid frequency from `/v2/frequency` — Austria shares the Continental Europe
  synchronous area, so it is the same frequency as Germany.
- Winter import dependence: the seasonal flip from net exporter to net
  importer is the story this page cannot tell from 24 hours alone.
