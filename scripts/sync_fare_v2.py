#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fare v2：由 681 巴士總站收費表（整理自營運商官方收費表）+ 運輸署 GeoJSON 站點，
計算每條路線每個站「由該站上車至終點」嘅分段車費，升級 fare_bus.json。
保留 fallback：攞唔到分段資料嘅路線維持 fullFare（全程價）。
用法：python3 scripts/sync_fare.py 之後再行 python3 scripts/sync_fare_v2.py（可獨立運行）
"""
import json, re, sys, os, time, datetime, urllib.request, concurrent.futures, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FARE_BUS = os.path.join(ROOT, "fare_bus.json")
BASE = "https://www.681busterminal.com/"
UA = {"User-Agent": "Mozilla/5.0 (hk-bus-dashboard fare v2 sync)"}
CACHE = {}

def url_for(co, route):
    """681 URL pattern：CTB→hk-<r>.html；KMB→<r>.html 再試 kn-<r>.html；LWB/NLB→<r>.html"""
    r = route.lower().replace(" ", "")
    if co == "CTB":
        return [BASE + "hk-" + r + ".html"]
    if co in ("KMB", "KMB+CTB"):
        # 聯營線城巴都有份，681 城巴頁收費表齊
        if co == "KMB+CTB":
            return [BASE + "hk-" + r + ".html", BASE + r + ".html", BASE + "kn-" + r + ".html"]
        return [BASE + r + ".html", BASE + "kn-" + r + ".html", BASE + "kmb-" + r + ".html"]
    if co in ("LWB", "NLB"):
        return [BASE + r + ".html"]
    return []  # DB/PI/XB/LRTFeeder：681 未必有，保留 fullFare

def fetch(url):
    if url in CACHE:
        return CACHE[url]
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
        for enc in ("utf-8", "big5"):
            try:
                txt = body.decode(enc)
                break
            except Exception:
                txt = body.decode("utf-8", "ignore")
        CACHE[url] = txt
        return txt
    except Exception:
        CACHE[url] = None
        return None

def parse_fare_table(html):
    """解析 681 收費表 -> {"full": float, "sections": [(描述, 金額)]}"""
    i = html.find("全程收費")
    if i < 0:
        return None
    j = html.find("八達通轉乘優惠")
    if j < 0:
        j = i + 4000
    seg = html[i:j]
    out = {"full": None, "sections": []}
    # 全程收費：`全程收費</td>...<td>6.20</td>`
    m = re.search(r"全程收費\s*</td>.*?<td[^>]*>\s*([\d.]+)\s*</td>", seg, re.S)
    if not m:
        m = re.search(r"全程收費.{0,80}?(\d+(?:\.\d+)?)", seg, re.S)
    if m:
        out["full"] = float(m.group(1))
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S)
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        texts = [re.sub(r"<[^>]+>|&nbsp;|\s", "", t) for t in tds]
        nums = [t for t in texts if re.fullmatch(r"\d+(?:\.\d+)?", t)]
        names = [t for t in texts if re.search(r"往", t)]
        if "小童" in "".join(texts) or "長者" in "".join(texts):
            continue
        if names and nums and not re.search(r"轉乘", "".join(texts)):
            out["sections"].append((names[0], float(nums[0])))
    return out

def _key(s):
    return re.sub(r"[（(].*?[)）]|[，,、\s]", "", s or "")

def match_section_stop(desc, stops):
    """分段描述 -> (站 index, 方向終點描述)。stops 係該 seq 嘅站 list（含 n/lat/lon/s）。
    回傳 (index, dest) 或 None。
    描述例：「筲箕灣道往勵德邨」「過香港仔隧道後往北角碼頭」「英皇道近書局街往興華邨」
    """
    m = re.search(r"^(.*?)往(.+)$", desc.strip())
    if not m:
        return None
    start, dest = m.group(1).strip(), m.group(2).strip()
    names = [st["n"] for st in stops]
    # 1) 過 X 後 -> 最後一個 match X 嘅站嘅下一個（過晒成段隧道/公路區域）
    am = re.match(r"^過(.+?)後$", start)
    if am:
        key = am.group(1).strip()
        hit_idx = None
        for idx, n in enumerate(names):
            if key in n or n in key or _key(key) in _key(n):
                hit_idx = idx
        if hit_idx is not None and hit_idx + 1 < len(stops):
            return hit_idx + 1, dest
        return None
    # 2) 括號內關鍵詞優先（英皇道(書局街) -> 書局街；英皇道(清風街天橋底) -> 清風街）
    bm = re.search(r"[（(]([^（）()]+)[)）]", start)
    if bm:
        k = bm.group(1).strip()
        kk = _key(k)
        if kk.startswith("近"):
            kk = kk[1:]  # 「(近利群道)」-> 利群道
        if kk:
            for idx, n in enumerate(names):
                nn = _key(n)
                if kk in nn or nn in kk:
                    return idx, dest
            # 模糊：key 前 3 字（清風街天橋底 -> 清風街）
            if len(kk) >= 3:
                for idx, n in enumerate(names):
                    nn = _key(n)
                    if kk[:3] in nn:
                        return idx, dest
        # 括號 key match 唔到 -> skip（唔好用寬泛街道 fallback，會提早分段，如 77 寶峰園）
        return None
    # 3) 「近 X」-> X
    nm = re.search(r"近(.+)$", start)
    keys = [nm.group(1).strip()] if nm else []
    # 4) 去除「近」「過」「後」後嘅主要街道
    main = re.sub(r"^過.+?後|近.+$|[（(].*?[)）]", "", start).strip()
    if main:
        keys.append(main)
    for key in keys:
        if not key:
            continue
        kk = _key(key)
        for idx, n in enumerate(names):
            nn = _key(n)
            if kk and (kk in nn or nn.startswith(kk)):
                return idx, dest
    # 5) fallback：頭兩個字 match
    if main:
        pre = _key(main)[:2]
        for idx, n in enumerate(names):
            if pre and _key(n).startswith(pre):
                return idx, dest
    return None

def direction_of(seq_dest, dest_desc):
    """分段終點描述是否屬於該 seq（去空格標點後做子字串匹配，保留括號內容）"""
    norm = lambda s: re.sub(r"[，,、\s]", "", s or "")
    d, t = norm(seq_dest), norm(dest_desc)
    if not d or not t:
        return False
    return d in t or t in d

def is_circular(stops):
    """循環線：首尾站名相同（去空格標點）"""
    norm = lambda s: re.sub(r"[，,、\s]", "", s or "")
    if len(stops) < 2:
        return False
    return norm(stops[0]["n"]) == norm(stops[-1]["n"])

def compute_stop_fares(fare_table, stops, dest_name):
    """對指定 seq（尾站 dest_name）計算每站車費。
    循環線分段表係「上車站→折返點」下車分段模型，同「上車站→終點」唔相容，維持全程價。"""
    full = fare_table["full"]
    bounds = []
    if not is_circular(stops):
        for desc, amt in fare_table["sections"]:
            hit = match_section_stop(desc, stops)
            if hit:
                idx, d = hit
                if direction_of(dest_name, d):
                    bounds.append((idx, amt))
        bounds.sort(key=lambda x: x[0])
    fares = []
    for i in range(len(stops)):
        f = full
        for b_idx, b_amt in bounds:
            if i >= b_idx:
                f = b_amt
        fares.append(f)
    return fares, bounds

def process_route(route_group):
    """處理 fare 檔一組（一條路線一個方向）。回傳 (key, 新 stops) 或 None"""
    co, rn, seq = route_group["co"], route_group["r"], route_group["seq"]
    urls = url_for(co, rn)
    html = None
    for u in urls:
        html = fetch(u)
        if html:
            break
    if not html:
        return None  # 681 冇頁 -> 保留 fullFare
    ft = parse_fare_table(html)
    if not ft or ft["full"] is None:
        return None
    stops = route_group["stops"]
    dest_name = stops[-1]["n"] if stops else ""
    fares, bounds = compute_stop_fares(ft, stops, dest_name)
    # 更新每站 f（有分段計算就用計算值，無分段都係 full）
    new_stops = []
    for st, f in zip(stops, fares):
        ns = dict(st)
        ns["f"] = f
        new_stops.append(ns)
    return (co, rn, seq, new_stops, ft["full"], bounds, dest_name)

def main():
    t0 = time.time()
    data = json.load(open(FARE_BUS, encoding="utf-8"))
    routes = data["routes"]
    print("路線×方向組數:", len(routes))
    circ = sum(1 for g in routes if is_circular(g["stops"]))
    print("循環線組數:", circ, "| 非循環線:", len(routes)-circ)
    results = []
    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        for i, res in enumerate(ex.map(process_route, routes)):
            if res:
                results.append(res)
            if (i + 1) % 200 == 0:
                print(f"  進度 {i+1}/{len(routes)} 已匹配 {len(results)}  ({time.time()-t0:.0f}s)")
    # 重新組裝：matched 嘅替換 stops
    by_key = {(r[0], r[1], r[2]): r for r in results}
    matched = 0
    for g in routes:
        key = (g["co"], g["r"], g["seq"])
        if key in by_key:
            r6 = by_key[key]
            g["stops"] = r6[3]
            g["dest"] = r6[6]
            matched += 1
    data["v"] = 2
    data["updated"] = datetime.date.today().isoformat()
    data["fareSource"] = "681分段收費(官方收費表整理) + 運輸署站點"
    data["matchedRoutes"] = matched
    with open(FARE_BUS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"完成：{matched}/{len(routes)} 組已套用分段收費（其餘保留全程價） 用時 {time.time()-t0:.0f}s")
    # 樣本輸出（81/8H/65 寶峰園/立德里）
    for g in routes:
        if g["co"] == "CTB" and g["r"] in ("81", "8H", "65"):
            for st in g["stops"]:
                if st["n"] in ("寶峰園,英皇道", "立德里,摩理臣山道"):
                    print(f"  CTB {g['r']} seq{g['seq']} {st['n']} -> ${st['f']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
