#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步車費資料：由運輸署開放數據 GeoJSON（每月更新兩次）生成精簡版
fare_bus.json（巴士）+ fare_gmb.json（綠色小巴），供前端查詢「該站車費」。

用法：python3 scripts/sync_fare.py
輸出：fare_bus.json / fare_gmb.json（repo 根部，部署後前端自動讀取）

車費定義：fullFare = 由該站上車嘅車費（運輸署「公共交通路線及收費資料」）。
"""
import json
import collections
import os
import sys
import urllib.request
import gzip

BASE = "https://static.data.gov.hk/td/routes-fares-geojson/"
FILES = {
    "bus": "JSON_BUS.json",   # 巴士（KMB / CTB / LWB / NWFB）
    "gmb": "JSON_GMB.json",   # 綠色小巴
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch(url, dest):
    print("下載:", url)
    req = urllib.request.Request(url, headers={"User-Agent": "hk-bus-dashboard-fare-sync"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    print("   ->", dest, "%.1f MB" % (os.path.getsize(dest) / 1e6))


def load(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def slim_bus(fc):
    """巴士：按 (companyCode, routeName, routeSeq) 分組"""
    groups = collections.defaultdict(list)
    for feat in fc["features"]:
        pr = feat["properties"]
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        groups[(pr["companyCode"], pr["routeNameC"], pr.get("routeSeq"))].append({
            "n": pr["stopNameC"], "f": pr.get("fullFare"), "s": pr.get("stopSeq"),
            "lat": round(lat, 5), "lon": round(lon, 5),
        })
    out = []
    for (co, rn, seq), stops in sorted(groups.items()):
        stops.sort(key=lambda x: (x["s"] is None, x["s"]))
        out.append({"co": co, "r": rn, "seq": seq, "stops": stops})
    return out


def slim_gmb(fc):
    """小巴：按 (companyCode, routeId, routeSeq) 分組（同名路線跨地區係唔同線）"""
    groups = collections.defaultdict(list)
    name_map = {}
    for feat in fc["features"]:
        pr = feat["properties"]
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        key = (pr["companyCode"], pr.get("routeId"), pr.get("routeSeq"))
        name_map[key] = pr["routeNameC"]
        groups[key].append({
            "n": pr["stopNameC"], "f": pr.get("fullFare"), "s": pr.get("stopSeq"),
            "lat": round(lat, 5), "lon": round(lon, 5),
        })
    out = []
    for (co, rid, seq), stops in sorted(groups.items()):
        stops.sort(key=lambda x: (x["s"] is None, x["s"]))
        out.append({"co": co, "id": rid, "r": name_map.get((co, rid, seq)), "seq": seq, "stops": stops})
    return out


def latest_update(fc):
    lu = [f["properties"]["lastUpdateDate"] for f in fc["features"] if f.get("properties", {}).get("lastUpdateDate")]
    return max(lu) if lu else None


def main():
    tmpdir = os.path.join(ROOT, ".faretmp")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        raw = {}
        for kind, fn in FILES.items():
            dest = os.path.join(tmpdir, fn)
            fetch(BASE + fn, dest)
            raw[kind] = load(dest)

        fare_bus = {"v": 1, "kind": "bus", "updated": latest_update(raw["bus"]), "routes": slim_bus(raw["bus"])}
        fare_gmb = {"v": 1, "kind": "gmb", "updated": latest_update(raw["gmb"]), "routes": slim_gmb(raw["gmb"])}

        for name, data in (("fare_bus.json", fare_bus), ("fare_gmb.json", fare_gmb)):
            p = os.path.join(ROOT, name)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            raw_size = os.path.getsize(p)
            with open(p, "rb") as f:
                gz = len(gzip.compress(f.read()))
            print("%s  %.2f MB (gzip %.2f MB)  更新日期: %s" % (name, raw_size / 1e6, gz / 1e6, data["updated"]))
        print("完成。將 fare_bus.json / fare_gmb.json commit 入 repo 即可。")
    finally:
        # 清理原始大檔（約 100MB）
        for fn in FILES.values():
            p = os.path.join(tmpdir, fn)
            if os.path.exists(p):
                os.remove(p)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
