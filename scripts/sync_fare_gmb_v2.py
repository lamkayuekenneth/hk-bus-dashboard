#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fare_gmb.json v2 生成腳本（小巴分段收費）
==========================================
v1（運輸署 GeoJSON fullFare）只有全程收費；v2 加入「上車至該方向終點」分段收費。

數據源：
- hkemobility（運輸署 HK eMobility）GMB Faretable：
  https://h2-app-rr.hkemobility.gov.hk/ris_page/get_gmb_detail.php?route_id=<id>
  （fare_gmb.json 嘅 route id 就係 hkemobility route_id）
- 車資表格式：每 row = 上車路段，最後一個有效金額 = 由該路段上車至終點（表尾站）車費。
- 分段邊界：用 App 截圖 / 車資表路段名對照站表（fuzzy match 站名），確定「分段起點站」。

已知限制：
- 只對「能可靠對照分段邊界」嘅路線套用分段；其餘維持 v1 全程價。
- 循環小巴（如 69）照樣套分段（同巴士循環線唔同：小巴 App 有逐段車費）。
"""
import json, re, sys, urllib.request

GMB_URL = "https://h2-app-rr.hkemobility.gov.hk/ris_page/get_gmb_detail.php?route_id={}"

# 分段規則：route_id -> [(起點站 index, 車費), ...]（起點站 index 之後全部用該車費，直到下一個分段起點）
# 69（鰂魚涌↔數碼港 循環線，id=2000410）：
#   城巴 App「69 由鰂魚涌開出」：全程 $14.5／過香港仔隧道後往數碼港 $7.0／由華翠街往數碼港 $3.5
#   站表：[33]黃竹坑道,黃竹坑遊樂場外 = 隧道後第一個站；[39]域多利道,近免疫學研究院 = 華翠街
SECTION_RULES = {
    2000410: [
        (33, 7.0),   # 過香港仔隧道後（黃竹坑道遊樂場外）至華翠街前
        (39, 3.5),   # 華翠街（域多利道）至數碼港
    ],
}

def fetch(route_id):
    req = urllib.request.Request(GMB_URL.format(route_id), headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "fare_gmb.json"
    data = json.load(open(path, encoding="utf-8"))
    applied = 0
    for g in data["routes"]:
        rules = SECTION_RULES.get(g["id"])
        if not rules:
            continue
        stops = g["stops"]
        # 每站預設維持 v1（全程價）
        # 套用分段：起點站 index 起用該段車費（下一個分段起點前）
        for i in range(len(stops)):
            for start_idx, fare in sorted(rules, key=lambda x: x[0]):
                if i >= start_idx:
                    stops[i]["f"] = fare
        applied += 1
        print(f"  套用分段: route {g['r']} (id={g['id']}) {len(rules)} 個分段")
    data["v"] = 2
    data["updated"] = "2026-10-10T22:30:00+08:00"
    data["sectionedRoutes"] = applied
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"完成：{applied} 條路線已套用分段，其餘維持全程價。寫入 {path}")

if __name__ == "__main__":
    main()
