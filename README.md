# Woher kommt der Strom?

A small, dependency-free page showing where Austria's electricity is coming
from: the generation mix, the last 24 hours by source, and the flows across
the borders.

**→ [rfuzzo.github.io/woher-kommt-der-strom](https://rfuzzo.github.io/woher-kommt-der-strom/)**

German and English, light and dark, no cookies, no trackers, no JavaScript
from anyone else's server.

## How it works

```
GitHub Actions (every 30 min)
  └─ scripts/fetch_data.py   fetch + reshape + precompute
       └─ site/data.json     one blob, everything the page needs
            └─ site/         uploaded as the Pages artifact
```

The browser makes one request for data and does no arithmetic on it — every
series, share and total is computed in `fetch_data.py`. `data.json` is not
committed; each run rebuilds and deploys it, so the repo history stays clean.

No framework, no build step, no third-party JavaScript. The charts are
hand-rolled SVG in `site/app.js`.

## Data

Everything comes from the [Energy-Charts v2 API](https://api.energy-charts.info/)
(Fraunhofer ISE), which needs no API key. It aggregates
[ENTSO-E](https://transparency.entsoe.eu/) and [APG](https://www.apg.at/) data.

| Panel | Endpoint |
|---|---|
| Generation mix, 24 h shape, load, renewable share | `/v2/public_power?country=at` |
| Cross-border flows, import/export balance | `/v2/cbpf?country=at` |
| Day-ahead price, trade valuation | `/v2/price?bzn=AT` |
| Import composition | `/v2/public_power?country={cz,de,hu,it,si,ch}` |

The API rate-limits (HTTP 429) when the neighbour countries are requested
back to back, so `get()` retries with backoff. Do not remove that.

Licence: CC BY 4.0, attribution `energy-charts.info`; prices additionally
Bundesnetzagentur | SMARD.de. Both render in the page footer.

River discharge comes from [eHYD](https://ehyd.gv.at/) (Hydrographie
Österreich, CC BY 4.0), via `/services/Diagram/pegelBgis?hzbnr=<id>` — one
gauge per river, requested **from the browser**. eHYD sends
`access-control-allow-origin: *` and refreshes every ~15 minutes, so that
panel is roughly two hours fresher than everything else and needs no rebuild.
If eHYD is unreachable the panel stays hidden and the rest of the page is
unaffected.

### This is not live

Energy-Charts publishes settled data 2–3 hours behind the wall clock, and the
lag is in the source rather than here. The page shows the data timestamp and
the publication lag instead of implying it is current. The river panel is the
exception and carries its own, much fresher timestamp.

### The import mix is attribution, not tracing

Each border flow is attributed to the exporting country's own generation mix
at that moment. This is the standard cheap approximation, and it has a real
limitation: it ignores transit. Power that reaches Austria from Czechia may
have originated in Poland; German power may be French nuclear. Getting true
origin requires flow-tracing across the whole European network, which this
does not attempt. The page states this in plain language rather than burying
it.

The panel shows **gross** imports (the sum of all inflows), which is larger
than the net balance in the panel above it.

`renewableShareSupply` is our own calculation — domestic plus attributed
imported renewables over total supply — and is not a figure the API provides.

### The money figures are a valuation, not a settlement

Import cost and export revenue are commercial trade volumes priced at the
day-ahead spot price. Real contracts do not all clear on the exchange, so
treat the euro numbers as an order of magnitude. They use
`cross_border_electricity_trading` rather than physical flows, because money
follows trades rather than what the wires carry — the two series track closely
but are not identical.

## Notes for anyone changing this

- **`cbpf` is in GW, `public_power` is in MW.** The fetcher scales via each
  response's declared `unit` rather than assuming.
- **Use `available_until`, not the last row.** The API pads the tail with
  intervals it has not settled yet.
- **Generation + imports does not equal load.** Different scopes, plus
  pumping and network losses. The 24 h chart stacks generation and draws load
  as a separate line instead of forcing a reconciliation that the source data
  does not support.
- **The stack order is a validated order.** The seven groups in `ORDER`
  (`app.js`) and `GROUPS` (`fetch_data.py`) map to palette slots that were
  checked for colourblind separation and contrast in both light and dark mode.
  Reordering the groups changes which colours sit next to each other and voids
  that result. Three light-mode series fall below 3:1 contrast, which is why
  every value is directly labelled and each chart has a table view.

## Running locally

```bash
python3 scripts/fetch_data.py && python3 -m http.server 8931 --directory site
```

Then open <http://localhost:8931>.

## Credit

The idea of a single, calm page that answers "where is the power coming from"
is borrowed from [holadelej.hu](https://holadelej.hu/), which does this for
Hungary. This is an independent implementation for Austria — no design, markup
or copy was taken from it. If you like this, go look at theirs.

Built with the help of [Claude Code](https://claude.com/claude-code).

## Ideas

- River discharge against hydro generation — does the run-of-river fleet
  visibly track the water? Care needed not to imply more causation than the
  data carries.
- Grid frequency from `/v2/frequency` — Austria shares the Continental Europe
  synchronous area, so it is the same frequency as Germany. Effectively live,
  but the API is CORS-locked, so it needs a proxy or the Actions rebuild.
- The seasonal flip from net exporter to net importer, which 24 hours of data
  cannot show.
