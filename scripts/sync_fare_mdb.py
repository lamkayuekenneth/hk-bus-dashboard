#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用官方 MDB（ROUTE + RSTOP + FARE）重建 fare_bus.json —— 權威分段收費。
取代舊 GeoJSON fullFare（垃圾值）＋ 681 民間網站（分段唔可靠）＋ SECTION_OVERRIDES。

資料來源（DATA.GOV.HK「公共交通路線及收費資料」）：
  ROUTE_BUS.mdb  https://static.data.gov.hk/td/routes-and-fares/ROUTE_BUS.mdb
  RSTOP_BUS.mdb  https://static.data.gov.hk/td/routes-and-fares/RSTOP_BUS.mdb
  FARE_BUS.mdb   https://static.data.gov.hk/td/routes-and-fares/FARE_BUS.mdb
  JSON_BUS.json  https://static.data.gov.hk/td/routes-fares-geojson/JSON_BUS.json（GPS）

邏輯：
  每條路線 = (ROUTE_ID, ROUTE_SEQ) 一個班次；
  每站車費 = FARE 表「該站上車(ON_SEQ) → 總站(最大 OFF_SEQ)」嘅 PRICE（×1/10000 = 元）；
  只落車站（FARE 冇 ON 記錄）沿用前一個有價站嘅價（單調遞減，總站都有價）；
  GPS 由 GeoJSON 按 (routeId, routeSeq, stopSeq) 攞。

用法：python3 scripts/sync_fare_mdb.py
"""
import json, os, sys, time, re, urllib.request

BASE = "https://static.data.gov.hk/td/routes-and-fares/"
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".faretmp")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {
    "ROUTE_BUS.mdb": BASE + "ROUTE_BUS.mdb",
    "RSTOP_BUS.mdb": BASE + "RSTOP_BUS.mdb",
    "FARE_BUS.mdb": BASE + "FARE_BUS.mdb",
    "JSON_BUS.json": "https://static.data.gov.hk/td/routes-fares-geojson/JSON_BUS.json",
}

def download(name, url):
    path = os.path.join(TMP, name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    os.makedirs(TMP, exist_ok=True)
    print(f"下載 {name} ...", flush=True)
    urllib.request.urlretrieve(url, path)
    return path

def main():
    t0 = time.time()
    from access_parser import AccessParser

    # 1) ROUTE 表
    rdb = AccessParser(download("ROUTE_BUS.mdb", FILES["ROUTE_BUS.mdb"])).parse_table("ROUTE")
    cols = list(rdb.keys()); idx = {c: i for i, c in enumerate(cols)}
    route_mdb = {}
    for r in zip(*rdb.values()):
        route_mdb[r[idx["ROUTE_ID"]]] = {
            "co": r[idx["COMPANY_CODE"]], "name": str(r[idx["ROUTE_NAMEC"]]),
            "full": round(r[idx["FULL_FARE"]] / 10000, 2),
        }
    print(f"ROUTE: {len(route_mdb)} 條  ({time.time()-t0:.1f}s)", flush=True)

    # 2) RSTOP 表（站序）
    rs = AccessParser(download("RSTOP_BUS.mdb", FILES["RSTOP_BUS.mdb"])).parse_table("RSTOP")
    cols = list(rs.keys()); idx = {c: i for i, c in enumerate(cols)}
    rstop = {}
    for r in zip(*rs.values()):
        key = (r[idx["ROUTE_ID"]], r[idx["ROUTE_SEQ"]])
        rstop.setdefault(key, []).append({
            "seq": r[idx["STOP_SEQ"]], "n": r[idx["STOP_NAMEC"]],
            "sid": r[idx["STOP_ID"]], "pd": r[idx["STOP_PICK_DROP"]],
        })
    print(f"RSTOP: {len(rstop)} 個班次  ({time.time()-t0:.1f}s)", flush=True)

    # 3) FARE 表：每 (rid, rseq) 嘅「上車 → 總站」價
    fa = AccessParser(download("FARE_BUS.mdb", FILES["FARE_BUS.mdb"])).parse_table("FARE")
    cols = list(fa.keys()); idx = {c: i for i, c in enumerate(cols)}
    term = {}
    for r in zip(*fa.values()):
        key = (r[idx["ROUTE_ID"]], r[idx["ROUTE_SEQ"]])
        off = r[idx["OFF_SEQ"]]
        if off > term.get(key, 0):
            term[key] = off
    fare = {}
    for r in zip(*fa.values()):
        key = (r[idx["ROUTE_ID"]], r[idx["ROUTE_SEQ"]])
        if r[idx["OFF_SEQ"]] == term[key]:
            fare.setdefault(key, {})[r[idx["ON_SEQ"]]] = r[idx["PRICE"]] / 10000
    print(f"FARE: {len(fare)} 班次有全程價  ({time.time()-t0:.1f}s)", flush=True)

    # 4) GeoJSON：GPS（WGS84）
    gj = json.load(open(download("JSON_BUS.json", FILES["JSON_BUS.json"]), encoding="utf-8-sig"))
    gps = {}
    for f in gj["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        gps[(p["routeId"], p["routeSeq"], p["stopSeq"])] = (round(lat, 5), round(lon, 5))
    print(f"GeoJSON GPS: {len(gps)} 站  ({time.time()-t0:.1f}s)", flush=True)

    # 5) 生成
    routes = []
    no_term = 0
    for key in sorted(rstop):
        rid, rseq = key
        rm = route_mdb.get(rid)
        if rm is None:
            continue
        fk = fare.get(key)
        stops_in = sorted(rstop[key], key=lambda s: s["seq"])   # STOP_SEQ = 行車次序（RSTOP 表掃描順序唔可靠）
        n = len(stops_in)
        # 站序整理（RSTOP 已按序）
        fmap = fk or {}
        last_f = rm["full"]
        stops = []
        for st in stops_in:
            f = fmap.get(st["seq"])
            if f is None:
                f = last_f          # 只落車站 / 總站：沿用前站價
            else:
                f = round(f, 1)
                last_f = f
            lat, lon = gps.get((rid, rseq, st["seq"]), (None, None))
            stops.append({"n": st["n"], "f": f, "s": st["seq"], "lat": lat, "lon": lon})
        routes.append({
            "co": rm["co"], "r": rm["name"], "rid": rid, "seq": rseq,
            "dest": stops[-1]["n"] if stops else "",
            "stops": stops,
        })
        if fk is None:
            no_term += 1

    out = {
        "v": 3,
        "updated": time.strftime("%Y-%m-%d"),
        "source": "TD FARE_BUS.mdb (ROUTE+RSTOP+FARE 官方分段收費)",
        "matchedRoutes": len(routes),
        "noFareTerminal": no_term,
        "routes": routes,
    }
    path = os.path.join(REPO, "fare_bus.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"寫入 {path}: {len(routes)} 條路線（{no_term} 班次冇 FARE）  ({time.time()-t0:.1f}s)", flush=True)

if __name__ == "__main__":
    main()
