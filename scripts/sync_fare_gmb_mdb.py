#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fare_gmb.json v2 生成腳本（綠色小巴分段收費，官方 MDB 版）
==========================================================
用運輸署官方「公共交通路線及收費資料」小巴版 MDB 重建 fare_gmb.json：
- ROUTE_GMB.mdb  ：路線定義（FULL_FARE 全程價 ×10000）
- RSTOP_GMB.mdb  ：每班次站序（ROUTE_ID+ROUTE_SEQ+STOP_SEQ + 站名）
- FARE_GMB.mdb   ：98,764 行完整分段收費矩陣（ON_SEQ→OFF_SEQ→PRICE ×10000）
- JSON_GMB.json  ：每站 GPS 座標（MDB 冇座標，utf-8-sig BOM）

每站車費 = FARE 表「該站上車 ON_SEQ → 總站(max OFF_SEQ)」嘅 PRICE/10000；
只落車站（FARE 冇該 ON_SEQ）沿用前站價。
GPS 由官方 JSON_GMB.json 按 (routeId, routeSeq, stopSeq) 攞，缺站 fallback 舊 fare_gmb.json。

用法：
    python3 scripts/sync_fare_gmb_mdb.py
輸出：
    fare_gmb.json（repo 根部，v2）
"""
import json, os, subprocess, sys, urllib.request

BASE = "https://static.data.gov.hk/td/routes-and-fares/"
GEO_URL = "https://static.data.gov.hk/td/routes-fares-geojson/JSON_GMB.json"
FILES = ["ROUTE_GMB.mdb", "RSTOP_GMB.mdb", "FARE_GMB.mdb"]
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".faretmp")

def download(name, url=None):
    os.makedirs(TMP, exist_ok=True)
    path = os.path.join(TMP, name)
    if not os.path.exists(path) or os.path.getsize(path) < 100000:
        print(f"下載 {name} ...")
        urllib.request.urlretrieve(url or (BASE + name), path)
    return path

def read_table(mdb, table):
    from access_parser import AccessParser
    t = AccessParser(mdb).parse_table(table)
    cols = list(t.keys())
    rows = [dict(zip(cols, vals)) for vals in zip(*t.values())]
    return rows

def main():
    for f in FILES:
        download(f)
    rp, sp, fp = [os.path.join(TMP, f) for f in FILES]
    gp = download("JSON_GMB.json", GEO_URL)

    route_rows = read_table(rp, "ROUTE")
    rstop_rows = read_table(sp, "RSTOP")
    fare_rows = read_table(fp, "FARE")

    # 全程價（×10000 → 元）
    full_fare = {r["ROUTE_ID"]: r["FULL_FARE"] / 10000 for r in route_rows}

    # 站序（按 STOP_SEQ 排序，RSTOP 掃描順序 ≠ 行車次序）
    rstop = {}
    for r in rstop_rows:
        key = (r["ROUTE_ID"], r["ROUTE_SEQ"])
        rstop.setdefault(key, []).append((r["STOP_SEQ"], r["STOP_NAMEC"]))
    for k in rstop:
        rstop[k].sort(key=lambda x: x[0])

    # 分段矩陣：每班次 max OFF_SEQ = 總站，每 ON_SEQ 上車 → 總站價
    fare = {}
    for r in fare_rows:
        key = (r["ROUTE_ID"], r["ROUTE_SEQ"])
        fare.setdefault(key, []).append((r["ON_SEQ"], r["OFF_SEQ"], r["PRICE"] / 10000))
    terminal = {}
    for k, recs in fare.items():
        maxoff = max(off for on, off, p in recs)
        terminal[k] = {on: p for on, off, p in recs if off == maxoff}

    # GPS index：官方 JSON_GMB.json（utf-8-sig BOM）→ {(rid, rseq, stopSeq): (lat, lon, name)}
    gps = {}
    with open(gp, encoding="utf-8-sig") as fh:
        geo = json.load(fh)
    for feat in geo.get("features", []):
        p, g = feat.get("properties", {}), feat.get("geometry", {})
        rid, rseq, ss = p.get("routeId"), p.get("routeSeq"), p.get("stopSeq")
        if rid is None or ss is None:
            continue
        coord = (g or {}).get("coordinates") or []
        if len(coord) == 2:
            gps[(rid, rseq, ss)] = (coord[1], coord[0], p.get("stopNameC", ""))

    # 舊 fare_gmb.json 做 GPS fallback
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    old_path = os.path.join(repo, "fare_gmb.json")
    old = json.load(open(old_path, encoding="utf-8"))
    old_by_key = {}
    for g in old["routes"]:
        old_by_key.setdefault((g["id"], g["seq"]), []).append(g)

    def norm(s):
        return "".join(ch for ch in (s or "") if ch.isalnum())

    new_routes = []
    missing_fare = 0
    gps_hit = 0
    gps_miss = 0
    for (rid, rseq), stops_mdb in sorted(rstop.items()):
        if rid not in full_fare:
            continue
        tp = terminal.get((rid, rseq))
        if tp is None:
            missing_fare += 1
            continue
        # 舊版 GPS fallback 基底（按站序 s + 站名 fuzzy）
        oldg = None
        cands = old_by_key.get((rid, rseq)) or []
        if cands:
            oldg = cands[0]
        old_stops = {s.get("s"): s for s in (oldg["stops"] if oldg else [])} if oldg else {}

        stops = []
        last_f = None
        for seq, name in stops_mdb:
            f = tp.get(seq)
            if f is None:
                f = last_f          # 只落車站沿用前站價
            last_f = f
            # GPS：官方 JSON_GMB.json 優先，fallback 舊檔
            lat = lon = None
            gp_ = gps.get((rid, rseq, seq))
            if gp_ is not None:
                lat, lon = gp_[0], gp_[1]
                gps_hit += 1
            else:
                gps_miss += 1
                os_ = old_stops.get(seq)
                if os_ is not None:
                    lat, lon = os_.get("lat"), os_.get("lon")
                if (lat is None or lon is None) and oldg:
                    for s in oldg["stops"]:
                        a, b = norm(s.get("n", "")), norm(name)
                        if a and b and (a == b or a in b or b in a):
                            lat, lon = s.get("lat"), s.get("lon")
                            break
            stops.append({"n": name, "f": f, "s": seq,
                          "lat": lat, "lon": lon})
        new_routes.append({"co": "GMB", "id": rid, "r": str(rid),
                           "seq": rseq, "stops": stops})

    out = {
        "v": 2,
        "updated": "2026-10-12",
        "source": "TD FARE_GMB.mdb (ROUTE+RSTOP+FARE 官方分段收費) + JSON_GMB.json GPS",
        "matchedRoutes": len(new_routes),
        "noFareTerminal": missing_fare,
        "routes": new_routes,
    }
    out_path = os.path.join(repo, "fare_gmb.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"寫入 {out_path}: {len(new_routes)} 條路線（{missing_fare} 班次冇 FARE）")
    print(f"GPS: JSON_GMB.json 命中 {gps_hit} 站, fallback {gps_miss} 站")
    print(f"全程價驗證: {sum(1 for r in new_routes if abs(r['stops'][0]['f'] - full_fare.get(r['id'], 0)) < 0.01)}/{len(new_routes)} 首站=全程價")

if __name__ == "__main__":
    main()
