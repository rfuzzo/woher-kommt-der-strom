# Woher kommt der Strom?

A small, dependency-free page showing where Austria's electricity is coming
from: the current mix as a two-ring donut, seven-day history and comparisons,
a year of seasonal context, import and export with cross-border detail,
pumped-storage operation and the energy balance.

**→ [rfuzzo.github.io/woher-kommt-der-strom](https://rfuzzo.github.io/woher-kommt-der-strom/)**

German and English, light and dark, no cookies, no trackers, no JavaScript
from anyone else's server.

Sister project: [Wie viel Wasser hat Österreich?](https://rfuzzo.github.io/woher-kommt-das-wasser/)
([source](https://github.com/rfuzzo/woher-kommt-das-wasser)) — precipitation
and snow depth from GeoSphere Austria.

## How it works

```
GitHub Actions (every 30 min)
  ├─ scripts/fetch_data.py    fetch + reshape + precompute
  │    └─ site/data.json      one blob, everything the page needs
  ├─ scripts/trace_origin.py  every 3 h, cache-gated: 32 calls
  │    └─ site/trace.json     traced origin for the Sankey
  └─ site/                    uploaded as the Pages artifact
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
| Generation mix, 24 h / 7 d shape, comparisons, load, renewable share | `/v2/public_power?country=at` |
| Cross-border flows, import/export balance | `/v2/cbpf?country=at` |
| Day-ahead price, trade valuation | `/v2/price?bzn=AT` |
| Import composition | `/v2/public_power?country={cz,de,hu,it,si,ch}` |
| Traced origin (Sankey) | `/v2/public_power` + `/v2/cbpf` for 16 zones |
| Seasonal context, 365 days | `/ren_share_daily_avg?country=at&year=-1` |

The API rate-limits (HTTP 429) when the neighbour countries are requested
back to back, so `get()` retries with backoff. Do not remove that.

`ren_share_daily_avg` is the one endpoint requested without the `/v2` prefix.
`add_season()` asks for the v2 path first and falls back to the root one, and
`daily_pairs()` reads either body shape — v2's rows of `{timestamp, values}`
or the older flat `{days, data}`. If the v2 path turns out to serve it, the
fallback and the second branch of `daily_pairs()` can both go.

Licence: CC BY 4.0, attribution `energy-charts.info`; prices additionally
Bundesnetzagentur | SMARD.de. Both render in the page footer.

### This is not live

Energy-Charts usually publishes Austrian data 2–3 hours behind the wall clock,
and that source delay cannot be removed here. The newest rows can still be
revised, so the fetcher uses the freshest complete sample unless the recent
run-of-river series contains an implausible jump; only then does it fall back
to the interval before the discontinuity. The page shows the data timestamp
and its current age instead of implying it is live.

### The import mix is attribution, not tracing — and that was checked

Each border flow is attributed to the exporting country's own generation mix
at that moment. This is the cheap approximation: it ignores transit, so power
reaching Austria from Czechia may in fact have originated in Poland.

Rather than leave that as an unquantified hand-wave, `scripts/check_import_mix.py`
implements proper flow-tracing (average participation — Bialek / Tranberg) over
a 16-country network and compares the two. Solving

```
T_i · c_i = P_i + Σ_j F_ji · c_j
```

for every zone propagates origin across the network, so Austria's imports are
weighted by its neighbours' *traced* mixes instead of their raw production.

Result on a sample day:

| group | attributed | traced | delta |
|---|---:|---:|---:|
| fossil | 32.8 % | 34.5 % | +1.6 |
| nuclear | 21.4 % | 18.8 % | −2.6 |
| wind | 8.2 % | 9.6 % | +1.5 |
| solar | 21.3 % | 21.1 % | −0.1 |
| hydro | 8.1 % | 7.9 % | −0.2 |
| **fossil + nuclear** | **54.2 %** | **53.3 %** | **−1.0** |

About one percentage point on the headline. Austria's imports come
overwhelmingly from Czechia and Germany, both large producers whose own import
share is small next to their production, so the dilution is second-order.

That is why the *import mix* panel keeps the simple method: tracing costs 32
API calls per build against a rate-limited endpoint, to move that headline by
a point. Re-run the check if the import pattern shifts:

```bash
python3 scripts/check_import_mix.py
```

The panel shows **gross** imports (the sum of all inflows), which is larger
than the net balance shown elsewhere.

`renewableShareSupply` is our own calculation — domestic plus attributed
imported renewables over total supply — and is not a figure the API provides.

### The Sankey does run the tracing

The one-point gap above is small for a technology breakdown, but tracing
answers a question attribution cannot answer *at all*: **which country** the
power started in. Attribution can only ever name Austria's six neighbours.
Tracing names the country the electricity was generated in, however many
borders it crossed to get here — Polish coal arriving via Czechia, French
nuclear via Germany. Neither shows up in the import-mix panel; both show up in
the Sankey.

`scripts/trace_origin.py` runs the same solve as the checker with origin kept
as a second dimension. The only change is the right-hand side: instead of six
columns (one per technology), the system carries one column per
`(zone, technology)` pair, each zone seeding only its own columns.

```
B[i][(z, k)] = P_i[k]  if z == i  else  0
```

Solving propagates those labelled columns through the network exactly as
before, so the algorithm is unchanged — there is just more bookkeeping riding
along. Austria's row of the solution is the mix of everything entering the
country, broken down by where it started; multiplied by Austrian load, that is
the Sankey.

Because it is expensive, it runs on a **three-hour cadence** rather than every
30 minutes. The workflow keys an `actions/cache` entry to a three-hour bucket:
within the same window the previous `trace.json` is restored and the tracer is
skipped. `restore-keys: trace-` means a miss still restores the newest earlier
result, so the panel shows slightly stale data with its own timestamp instead
of disappearing. A failed trace is never fatal — the step is
`continue-on-error`, the previous file is published, and if there is no file at
all the panel simply stays hidden.

Limits worth knowing: average participation assumes power mixes completely
within each zone, so it cannot point at individual plants; and the 16-country
network is truncated, so flows entering it from outside are treated as if they
originated at the boundary.


### The donut mixes two figures on purpose

The outer ring is the source, the inner ring says whether that source stood in
Austria. Both rings are shares of one total: domestic generation plus positive
net imports.

That total forces a choice, because the import mix is measured on **gross**
inflows while the headline import figure is the **net** commercial balance.
`add_supply_mix()` therefore applies the import mix's *shares* to the net
figure rather than its megawatts, so the ring closes on the same supply total
the tiles and the table use. Using the mix's own megawatts would overshoot the
circle whenever Austria is importing and exporting at the same time, which is
most of the day.

Imported segments are hatched rather than given their own hues. They reuse the
source colours — so hydro is blue whichever side of the border it came from —
and the texture carries both "imported" and "estimated" without spending six
more slots out of a palette that was validated at its current size.

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
- **`clean()` zero-fills, `scaled()` does not. Pick deliberately.** Zero is
  right for generation — a production type the API does not report really is
  contributing nothing. It is wrong for cross-border flows, where it turns an
  unpublished interval into a border that briefly carried no power.
- **A missing border does not make `sum` null, it makes it wrong.** The API
  adds `sum` up over the borders it has, so one unpublished border leaves a
  number that is low by exactly that flow. Zero-filling the components on top
  of that produced a ~1.5 GW cliff and recovery in a single interval, which
  looked like a grid event and was not one. An interval is only used when
  *every* border has published; otherwise the total is unknown, not smaller,
  and the charts draw a gap. `trade.gaps` and `importMix.gaps` count them.
  The give-away that it was never real: all six import-mix groups collapsed
  together and recovered one step later, while storage and load stayed
  smooth — no domestic response, no load change, so energy could not balance.
- **Use `available_until`, not the last row.** The API pads the tail with
  intervals it has not published yet. The rows immediately before that
  watermark can still be provisional, so a run-of-river continuity guard
  rejects the kind of ~900 MW false step observed on 7 August 2026 without
  delaying every normal build by a fixed hour.
- **Generation + imports does not equal load.** The balance panel explicitly
  subtracts pumping demand, which explains most of the midday difference. The
  remaining gap is left visible because generation, trading and load have
  different scopes and publication schedules, with grid losses on top; it is
  not forced to reconcile.
- **The stack order is a validated order.** The seven groups in `ORDER`
  (`app.js`) and `GROUPS` (`fetch_data.py`) map to palette slots that were
  checked for colourblind separation and contrast in both light and dark mode.
  Reordering the groups changes which colours sit next to each other and voids
  that result. Three light-mode series fall below 3:1 contrast, which is why
  every value is directly labelled and each chart has a table view.
- **Time-axis labels are width-aware.** `tickIndices()` picks the label count
  from the plot width rather than always asking for eight; the last sample is
  always labelled, so the regular tick before it is dropped when the two would
  collide. Eight `HH:MM` labels do not fit on a phone.
- **The seasonal panel leads with the trailing mean.** Daily renewable share
  swings by tens of points with the weather, so the raw series is drawn pale
  behind a 30-day mean. The most recent day may still be partial, which is why
  it is labelled with its own date rather than called "today".
- **Import and export is one panel.** The 24 h balance, the per-neighbour
  cards and the seven-day import dependency all come from `cbpf` and share one
  timestamp; they were three blocks saying the same thing in three ways. Each
  neighbour card takes its headline number from `flows`, which walks back to
  that border's newest published reading, and its shape from the padded
  series — the last point of the series is not always live.

## Running locally

```bash
python3 scripts/fetch_data.py
python3 scripts/trace_origin.py      # optional; powers the origin Sankey
python3 -m http.server 8931 --directory site
```

Then open <http://localhost:8931>.

## Credit

The idea of a single, calm page that answers "where is the power coming from"
is borrowed from [holadelej.hu](https://holadelej.hu/), which does this for
Hungary. This is an independent implementation for Austria — no design, markup
or copy was taken from it. If you like this, go look at theirs.

Built with the help of [Claude Code](https://claude.com/claude-code).

## Ideas

- Installed capacity against current output, from `/v2/installed_power`. Would
  give the megawatts a ceiling to sit under. Needs checking first that
  `public_power` covers the same fleet — if it under-reports self-consumed
  rooftop PV, the capacity factor is an artefact rather than a fact.
- Hours below €0 over a longer window, as a structural read on surplus.

Deliberately not doing: grid frequency. It is measured in Freiburg and is the
same across all of Continental Europe, so it is not an Austrian number, and
one-second data would advertise a liveness the rest of the page is careful to
disclaim.
