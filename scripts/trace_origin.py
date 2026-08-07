#!/usr/bin/env python3
"""Trace where Austria's electricity was actually generated, and write
site/trace.json for the Sankey.

`check_import_mix.py` already implements average participation (Bialek /
Tranberg) across a 16-country network, but only resolves *technology*: it
answers "how much of this was coal" and throws the country away. This script
runs the same solve with the origin country kept as a second dimension, so
each unit of Austrian consumption can be traced to a (country, technology)
pair — the input a Sankey needs.

Mechanically the only change is the right-hand side. Instead of six columns
(one per technology), the system carries one column per (zone, technology)
pair, with zone i seeding only its own columns:

    B[i][(z, k)] = P_i[k]  if z == i  else  0

Solving propagates those labelled columns through the network exactly as
before, so nothing about the algorithm's correctness changes — there is just
more bookkeeping riding along. Austria's row of the solution is then the mix
of everything entering Austria, broken down by where it started.

This costs 32 API calls against a rate-limited endpoint, so it runs on its
own slower cadence (see .github/workflows/deploy.yml) rather than on every
build.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_import_mix import (  # noqa: E402
    GROUPS, KEYS, NOT_GEN, ZONES, fetch_all, inflows, load as load_cached,
    nearest, production, solve, ts_of,
)

OUT = Path(__file__).resolve().parent.parent / "site" / "trace.json"

# How many origin countries the Sankey names before the tail is folded into
# "Other". Six plus a tail keeps the diagram readable and stays inside the
# palette's limits.
TOP_COUNTRIES = 6
# Origins below this share of consumption are dropped rather than drawn as
# a band too thin to see.
MIN_SHARE = 0.0015
HOURS_BACK = 24


def loads() -> dict[str, dict[int, float]]:
    """zone -> ts -> load in MW. Held separately because production() drops
    the load series as not-generation."""
    out = {}
    for z in ZONES:
        d = load_cached(z)
        if not d:
            continue
        scale = 1000.0 if (d.get("unit") or "MW").upper() == "GW" else 1.0
        byts = {}
        for row in d["data"]:
            v = row["values"].get("load")
            if v is not None and v > 0:
                byts[ts_of(row)] = v * scale
        out[z] = byts
    return out


def trace_origin_at(ts, prod, flow):
    """Austria's inflow mix at `ts`, as {(origin zone, tech): share}."""
    zones = [z for z in ZONES if prod.get(z) and nearest(prod[z], ts)]
    idx = {z: i for i, z in enumerate(zones)}
    n = len(zones)
    if "at" not in idx:
        return None, zones

    P, F, T = {}, {}, {}
    for z in zones:
        P[z] = nearest(prod[z], ts)
        F[z] = {s: mw for s, mw in (nearest(flow.get(z, {}), ts) or {}).items()
                if s in idx}
        T[z] = sum(P[z].values()) + sum(F[z].values())

    # One column per (origin zone, technology). Each zone seeds only the
    # columns carrying its own name, so the solve keeps origin attached.
    cols = [(z, k) for z in zones for k in KEYS]
    col_idx = {c: j for j, c in enumerate(cols)}

    A = [[0.0] * n for _ in range(n)]
    B = [[0.0] * len(cols) for _ in range(n)]
    for z in zones:
        i = idx[z]
        A[i][i] = T[z] if T[z] > 0 else 1.0
        for s, mw in F[z].items():
            A[i][idx[s]] -= mw
        for k in KEYS:
            B[i][col_idx[(z, k)]] = P[z][k]

    C = solve(A, B)
    row = C[idx["at"]]
    return {c: row[col_idx[c]] for c in cols if row[col_idx[c]] > 1e-9}, zones


def shape(mix_mw: dict, total: float) -> dict:
    """Fold the raw (zone, tech) map into the Sankey's nodes and links."""
    by_country: dict[str, float] = {}
    for (z, _k), mw in mix_mw.items():
        by_country[z] = by_country.get(z, 0.0) + mw

    ranked = sorted(by_country, key=lambda z: -by_country[z])
    # Austria always keeps its own row: it is the comparison the reader wants,
    # even on a day when imports outweigh it.
    named = [z for z in ranked if z == "at"][:1]
    named += [z for z in ranked if z != "at"][:TOP_COUNTRIES - 1]
    keep = set(named)

    links: dict[tuple[str, str], float] = {}
    for (z, k), mw in mix_mw.items():
        key = (z if z in keep else "other", k)
        links[key] = links.get(key, 0.0) + mw

    order = named + (["other"] if any(c == "other" for c, _ in links) else [])
    countries = [{
        "c": c,
        "mw": round(sum(mw for (cc, _), mw in links.items() if cc == c), 1),
    } for c in order]
    # A country contributing a fraction of a percent draws as a hairline with
    # a label attached to nothing, so the tail is dropped rather than shown.
    floor = total * MIN_SHARE
    countries = [c for c in countries if c["mw"] >= floor]
    order = [c["c"] for c in countries]
    links = {(c, k): mw for (c, k), mw in links.items() if c in set(order)}
    techs = [{
        "k": k,
        "mw": round(sum(mw for (_, kk), mw in links.items() if kk == k), 1),
    } for k in KEYS]
    techs = [t for t in techs if t["mw"] > 0.05]

    shown = sum(c["mw"] for c in countries) or 1.0
    for c in countries:
        c["pct"] = round(100 * c["mw"] / shown, 1)
    for t in techs:
        t["pct"] = round(100 * t["mw"] / shown, 1)

    return {
        "consumptionMw": round(total, 1),
        "countries": countries,
        "techs": techs,
        "links": sorted(
            ({"c": c, "k": k, "mw": round(mw, 1)}
             for (c, k), mw in links.items() if mw > 0.05),
            key=lambda l: (order.index(l["c"]), KEYS.index(l["k"])),
        ),
        "domesticPct": round(
            100 * sum(mw for (c, _), mw in links.items() if c == "at") / total, 1
        ) if total else 0.0,
        "renewablePct": round(
            100 * sum(mw for (_, k), mw in links.items()
                      if k in ("hydro", "wind", "solar")) / total, 1
        ) if total else 0.0,
    }


def main() -> None:
    fetch_all()
    prod, flow, ld = production(), inflows(), loads()

    stamps = sorted(t for t in flow.get("at", {}) if flow["at"][t])
    if not stamps:
        raise SystemExit("no Austrian cross-border data")
    stamps = stamps[-int(HOURS_BACK * 4):]

    latest = None
    agg: dict[tuple[str, str], float] = {}
    agg_load = 0.0
    used = 0
    zones_seen: list[str] = []

    for ts in stamps:
        try:
            shares, zones = trace_origin_at(ts, prod, flow)
        except Exception as e:                       # noqa: BLE001
            print(f"  skip {ts}: {e}", file=sys.stderr)
            continue
        if not shares:
            continue
        at_load = nearest(ld.get("at", {}), ts)
        if not at_load:
            continue

        zones_seen = zones
        used += 1
        agg_load += at_load
        for key, share in shares.items():
            agg[key] = agg.get(key, 0.0) + share * at_load
        latest = (ts, {k: v * at_load for k, v in shares.items()}, at_load)

    if not used or latest is None:
        raise SystemExit("nothing traceable in the window")

    ts, now_mw, now_load = latest
    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "at": ts,
        "zoneCount": len(zones_seen),
        "zones": zones_seen,
        "steps": used,
        "method": "average participation (Bialek/Tranberg)",
        "now": shape(now_mw, now_load),
        # Averaged rather than summed, so the day view reads in MW like every
        # other panel instead of as a 24-hour running total.
        "day": shape({k: v / used for k, v in agg.items()}, agg_load / used),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    when = datetime.fromtimestamp(ts, timezone.utc)
    print(f"wrote {OUT} — traced {len(zones_seen)} zones over {used} steps, "
          f"latest {when:%Y-%m-%d %H:%M} UTC, "
          f"{out['now']['domesticPct']:.0f}% domestic")


if __name__ == "__main__":
    main()
