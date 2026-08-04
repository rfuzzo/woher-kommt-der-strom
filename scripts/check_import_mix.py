#!/usr/bin/env python3
"""One-off check: does flow-tracing change the import-mix numbers enough to
matter, compared with the simple source-country attribution the site uses?

Method: average participation (Bialek / Tranberg). For every zone i,

    T_i * c_i = P_i + sum_j F_ji * c_j

where P_i is domestic production by technology, F_ji the inflow from j to i,
T_i total power entering i, and c_i the resulting mix of everything flowing
through i. Solving the linear system propagates origin across the network,
so Czech imports carry Polish coal rather than being counted as Czech.

Austria's import mix is then the inflow-weighted average of its neighbours'
*traced* mixes, instead of their raw production mixes.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

CACHE = Path(os.environ.get("TRACE_CACHE", "/tmp/echarts"))
ZONES = ["at", "cz", "de", "hu", "it", "si", "ch", "pl", "sk",
         "fr", "nl", "be", "dk", "hr", "rs", "ro"]

SERIES_TO_ZONE = {
    "austria": "at", "czech_republic": "cz", "germany": "de", "hungary": "hu",
    "italy": "it", "slovenia": "si", "switzerland": "ch", "poland": "pl",
    "slovakia": "sk", "france": "fr", "netherlands": "nl", "belgium": "be",
    "denmark": "dk", "croatia": "hr", "serbia": "rs", "romania": "ro",
}

GROUPS = {
    "nuclear": "nuclear",
    "fossil_gas": "fossil", "fossil_hard_coal": "fossil",
    "fossil_brown_coal_lignite": "fossil", "fossil_oil": "fossil",
    "fossil_coal_derived_gas": "fossil",
    "hydro_run_of_river": "hydro", "hydro_water_reservoir": "hydro",
    "hydro_pumped_storage": "hydro",
    "wind_onshore": "wind", "wind_offshore": "wind",
    "solar": "solar",
}
KEYS = ["hydro", "fossil", "wind", "solar", "nuclear", "other"]
NOT_GEN = {"load", "residual_load", "renewable_share_of_load",
           "renewable_share_of_generation", "cross_border_electricity_trading",
           "hydro_pumped_storage_consumption", "battery_consumption"}


def load(name):
    p = CACHE / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def fetch_all():
    """Populate the cache. 32 requests, so it is deliberately unhurried —
    the API returns 429 if you rush it."""
    CACHE.mkdir(parents=True, exist_ok=True)
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=2)
    for z in ZONES:
        for ep, name in (("public_power", z), ("cbpf", f"cbpf_{z}")):
            p = CACHE / f"{name}.json"
            if p.exists() and p.stat().st_size > 400:
                continue
            url = (f"https://api.energy-charts.info/v2/{ep}"
                   f"?country={z}&start={start}&end={end}")
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(url, timeout=90) as r:
                        p.write_bytes(r.read())
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        print(f"  no data: {name}")
                        break
                    time.sleep(4 * (attempt + 1))
                except urllib.error.URLError:
                    time.sleep(4 * (attempt + 1))
            time.sleep(2)


def ts_of(row):
    return int(datetime.fromisoformat(row["timestamp"]).timestamp())


def production():
    """zone -> ts -> {group: MW}"""
    out = {}
    for z in ZONES:
        d = load(z)
        if not d:
            continue
        scale = 1000.0 if (d.get("unit") or "MW").upper() == "GW" else 1.0
        byts = {}
        for row in d["data"]:
            acc = {k: 0.0 for k in KEYS}
            for sid, v in row["values"].items():
                if sid in NOT_GEN or v is None or v <= 0:
                    continue
                acc[GROUPS.get(sid, "other")] += v * scale
            if sum(acc.values()) > 0:
                byts[ts_of(row)] = acc
        out[z] = byts
    return out


def inflows():
    """zone -> ts -> {source zone: MW imported}"""
    out = {}
    for z in ZONES:
        d = load(f"cbpf_{z}")
        if not d:
            continue
        scale = 1000.0 if (d.get("unit") or "MW").upper() == "GW" else 1.0
        names = {s["id"]: s["id"] for s in d["series"]}
        byts = {}
        for row in d["data"]:
            acc = {}
            for sid, v in row["values"].items():
                if sid == "sum" or v is None:
                    continue
                src = SERIES_TO_ZONE.get(names.get(sid, sid))
                if src and v > 0:
                    acc[src] = v * scale
            byts[ts_of(row)] = acc
        out[z] = byts
    return out


def solve(A, B):
    """Gaussian elimination with partial pivoting; B has multiple columns."""
    n = len(A)
    M = [A[i][:] + B[i][:] for i in range(n)]
    w = len(M[0])
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-9:
            continue
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        for k in range(col, w):
            M[col][k] /= d
        for r in range(n):
            if r == col or abs(M[r][col]) < 1e-12:
                continue
            f = M[r][col]
            for k in range(col, w):
                M[r][k] -= f * M[col][k]
    return [row[n:] for row in M]


def nearest(byts, ts):
    ks = [k for k in byts if k <= ts]
    return byts[max(ks)] if ks else None


def trace_at(ts, prod, flow):
    """Returns (traced import mix, naive import mix) as MW dicts for Austria."""
    zones = [z for z in ZONES if prod.get(z) and nearest(prod[z], ts)]
    idx = {z: i for i, z in enumerate(zones)}
    n = len(zones)

    P, F, T = {}, {}, {}
    for z in zones:
        P[z] = nearest(prod[z], ts)
        F[z] = {s: mw for s, mw in (nearest(flow.get(z, {}), ts) or {}).items()
                if s in idx}
        T[z] = sum(P[z].values()) + sum(F[z].values())

    A = [[0.0] * n for _ in range(n)]
    B = [[0.0] * len(KEYS) for _ in range(n)]
    for z in zones:
        i = idx[z]
        A[i][i] = T[z] if T[z] > 0 else 1.0
        for s, mw in F[z].items():
            A[i][idx[s]] -= mw
        for k, key in enumerate(KEYS):
            B[i][k] = P[z][key]

    C = solve(A, B)   # traced share vector per zone (sums to ~1)

    at_in = F["at"]
    total = sum(at_in.values()) or 1.0
    traced = {k: 0.0 for k in KEYS}
    naive = {k: 0.0 for k in KEYS}
    for s, mw in at_in.items():
        for k, key in enumerate(KEYS):
            traced[key] += mw * C[idx[s]][k]
        ptot = sum(P[s].values()) or 1.0
        for key in KEYS:
            naive[key] += mw * P[s][key] / ptot
    return traced, naive, total


def main():
    fetch_all()
    prod, flow = production(), inflows()
    stamps = sorted(t for t in flow.get("at", {}) if flow["at"][t])
    stamps = stamps[-96:]

    agg_t = {k: 0.0 for k in KEYS}
    agg_n = {k: 0.0 for k in KEYS}
    used = 0
    for ts in stamps:
        try:
            tr, na, tot = trace_at(ts, prod, flow)
        except Exception:
            continue
        if tot <= 0:
            continue
        used += 1
        for k in KEYS:
            agg_t[k] += tr[k]
            agg_n[k] += na[k]

    st, sn = sum(agg_t.values()) or 1, sum(agg_n.values()) or 1
    print(f"zones in network: {len([z for z in ZONES if prod.get(z)])}, "
          f"timesteps: {used}\n")
    print(f"{'group':10s} {'naive %':>9s} {'traced %':>10s} {'delta':>8s}")
    for k in KEYS:
        a, b = agg_n[k] / sn * 100, agg_t[k] / st * 100
        print(f"{k:10s} {a:9.1f} {b:10.1f} {b - a:+8.1f}")
    dn = (agg_n['fossil'] + agg_n['nuclear']) / sn * 100
    dt = (agg_t['fossil'] + agg_t['nuclear']) / st * 100
    print(f"\nfossil+nuclear: naive {dn:.1f} %  traced {dt:.1f} %  "
          f"({dt - dn:+.1f} pts)")


if __name__ == "__main__":
    main()
