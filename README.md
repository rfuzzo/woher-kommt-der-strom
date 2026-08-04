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
| Day-ahead price | `/v2/price?bzn=AT` |

Licence: CC BY 4.0, attribution `energy-charts.info`; prices additionally
Bundesnetzagentur | SMARD.de. Both render in the page footer.

### This is not live

Energy-Charts publishes settled data 2–3 hours behind the wall clock, and the
lag is in the source rather than here. The page shows the data timestamp and
the publication lag instead of implying it is current.

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

- Hydro: reservoir levels and river discharge from
  [ehyd.gv.at](https://ehyd.gv.at/) (CC BY 4.0).
- Grid frequency from `/v2/frequency` — Austria shares the Continental Europe
  synchronous area, so it is the same frequency as Germany.
- The seasonal flip from net exporter to net importer, which 24 hours of data
  cannot show.
