#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步車費資料：由運輸署開放數據 GeoJSON（每月更新兩次）+ 官方 ROUTE_BUS.xml 生成精簡版
fare_bus.json（巴士）+ fare_gmb.json（綠色小巴），供前端查詢「該站車費」。

用法：python3 scripts/sync_fare.py
輸出：fare_bus.json / fare_gmb.json（repo 根部，部署後前端自動讀取）

v3 修正（2026-10-12）：
1. 站序交叉：原按 (companyCode, routeNameC, routeSeq) 分組，運輸署 GeoJSON 同一
   routeSeq 內含多個班次（routeId 唔同、stopSeq 各自由 1 開始），會將多班次站點
   串埋成幾百站。改為先按 (companyCode, routeId, routeSeq) 拆開班次，再按
   (co, routeNameC, routeSeq) 聚合揀站數最多嘅主班次 → 站序交叉清零。
2. 垃圾值：以官方 ROUTE_BUS.xml 嘅 FULL_FARE 做權威，覆蓋 GeoJSON 垃圾值
   （如 KMB 40 = $1970 → $10.1）；攞唔到 XML 先保留 GeoJSON fullFare。
3. 每組保留 rid（routeId），前端可精確匹配班次。

車費定義：fullFare = 由該站上車嘅車費（運輸署「公共交通路線及收費資料」）。
"""
import json
import collections
import os
import sys
import urllib.request
import gzip
import xml.etree.ElementTree as ET

BASE = "https://static.data.gov.hk/td/routes-fares-geojson/"
XML_URL = "https://static.data.gov.hk/td/routes-fares-xml/ROUTE_BUS.xml"
FILES = {
    "bus": "JSON_BUS.json",   # 巴士（KMB / CTB / LWB / NWFB）
    "gmb": "JSON_GMB.json",   # 綠色小巴
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch(url, dest=None):
    print("下載:", url)
    req = urllib.request.Request(url, headers={"User-Agent": "hk-bus-dashboard-fare-sync"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
    if dest:
        with open(dest, "wb") as f:
            f.write(body)
        print("   ->", dest, "%.1f MB" % (len(body) / 1e6))
    return body


def load(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def load_xml_full_fare():
    """官方 ROUTE_BUS.xml -> {(CO, routeNameC, locStartC, locEndC): fullFare}
    同時存一份去 .faretmp 畀 sync_fare_v2 重用。"""
    body = fetch(XML_URL)
    tmp = os.path.join(ROOT, ".faretmp")
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "ROUTE_BUS.xml"), "wb") as f:
        f.write(body)
    root = ET.fromstring(body)
    out = {}
    for r in root.iter("ROUTE"):
        d = {c.tag.split("}")[-1]: (c.text or "").strip() for c in r}
        try:
            ff = float(d.get("FULL_FARE"))
        except (TypeError, ValueError):
            continue
        out[(d["COMPANY_CODE"], d["ROUTE_NAMEC"], d["LOC_START_NAMEC"], d["LOC_END_NAMEC"])] = ff
    print("   XML FULL_FARE 權威表:", len(out), "條")
    return out


def slim_bus(fc, xml_fare):
    """巴士：先按 (companyCode, routeId, routeSeq) 拆開班次，再聚合揀主班次"""
    by_rid = collections.defaultdict(list)
    for feat in fc["features"]:
        pr = feat["properties"]
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        by_rid[(pr["companyCode"], pr.get("routeId"), pr.get("routeSeq"))].append({
            "n": pr["stopNameC"], "f": pr.get("fullFare"), "s": pr.get("stopSeq"),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "locStart": pr.get("locStartNameC", ""), "locEnd": pr.get("locEndNameC", ""),
            "rn": pr["routeNameC"],
        })

    # 每個班次內按 stopSeq 排序
    for k in by_rid:
        by_rid[k].sort(key=lambda x: (x["s"] is None, x["s"]))

    # 聚合：同一 (co, routeNameC, routeSeq) 揀站數最多嘅主班次
    groups = collections.defaultdict(list)
    for (co, rid, seq), stops in by_rid.items():
        if not stops:
            continue
        rn = stops[0]["rn"]
        groups[(co, rn, seq)].append((rid, stops))

    out = []
    for (co, rn, seq), cands in sorted(groups.items()):
        # 揀站數最多嘅主班次（通常係全程班次）
        best_rid, best_stops = max(cands, key=lambda g: len(g[1]))
        loc_start, loc_end = best_stops[0]["locStart"], best_stops[0]["locEnd"]
        # XML fullFare 權威覆蓋 GeoJSON 垃圾值
        xml_ff = xml_fare.get((co, rn, loc_start, loc_end))
        new_stops = []
        for st in best_stops:
            f = xml_ff if xml_ff is not None else st["f"]
            new_stops.append({"n": st["n"], "f": f, "s": st["s"], "lat": st["lat"], "lon": st["lon"]})
        out.append({"co": co, "r": rn, "rid": best_rid, "seq": seq, "dest": best_stops[-1]["n"], "stops": new_stops})
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

        xml_fare = load_xml_full_fare()

        fare_bus = {"v": 3, "kind": "bus", "updated": latest_update(raw["bus"]), "routes": slim_bus(raw["bus"], xml_fare)}
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
        # 保留 ROUTE_BUS.xml 畀 v2 用；清理原始大檔（約 100MB）
        for fn in FILES.values():
            p = os.path.join(tmpdir, fn)
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    sys.exit(main())
