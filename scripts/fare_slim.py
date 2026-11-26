#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 config.json 篩出網頁實際用到嘅路線，產生輕量車費檔：
    fare_bus_slim.json（巴士）、fare_gmb_slim.json（小巴）

全量檔 5.5MB（2366+1164 條路線、約 6.9 萬個站），頁面只需要 config 內 99 條，
slim 版通常 300-500KB，瀏覽器解析後 heap 由 ~20MB 降到 ~1MB。

匹配規則同 index.html fareRoutesFor() 一致：
- 巴士：config row co ∈ {kmb, ctb, joint} → 按路線號 r 保留所有同名 record（含聯營／LWB）
- 小巴：config row co = gmb → 按 routeId（= fare_gmb.json 嘅 id）保留

用法：
    python3 scripts/fare_slim.py            # 兩個都生成
    from fare_slim import build; build("bus") / build("gmb")
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUS_CO = {"kmb", "ctb", "joint"}


def load_config():
    with open(os.path.join(REPO, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def wanted(cfg):
    """回傳 config 用到嘅巴士路線號集合、小巴 routeId 集合。"""
    bus, gmb = set(), set()
    for g in cfg.get("groups", []):
        for r in g.get("routes", []):
            co = (r.get("co") or "").lower()
            if co in BUS_CO and r.get("route") is not None:
                bus.add(str(r["route"]))
            elif co == "gmb" and r.get("routeId") is not None:
                gmb.add(str(r["routeId"]))
    return bus, gmb


def build(kind):
    """kind = 'bus' | 'gmb'；讀全量檔篩選後寫 slim 檔，回傳保留路線數。"""
    bus, gmb = wanted(load_config())
    if kind == "bus":
        src, out, want = "fare_bus.json", "fare_bus_slim.json", bus
        keyf = lambda x: str(x.get("r"))
    elif kind == "gmb":
        src, out, want = "fare_gmb.json", "fare_gmb_slim.json", gmb
        keyf = lambda x: str(x.get("id"))
    else:
        raise ValueError("kind 只接受 bus / gmb")

    with open(os.path.join(REPO, src), encoding="utf-8") as f:
        data = json.load(f)
    routes = [x for x in data.get("routes", []) if keyf(x) in want]
    slim = dict(data)
    slim["routes"] = routes
    slim["slim"] = True
    slim["slimFor"] = len(want)
    path = os.path.join(REPO, out)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(path) / 1024
    print(f"{out}: {len(routes)} 條路線（config 需要 {len(want)} 個），{size_kb:.0f} KB")
    return len(routes)


if __name__ == "__main__":
    build("bus")
    build("gmb")
