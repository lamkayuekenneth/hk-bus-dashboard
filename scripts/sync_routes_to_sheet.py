#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 config.json 路線清單到「Github」spreadsheet 嘅 config sheet。

等價於網頁「匯出路線表 CSV」功能（index.html 嘅 exportRoutesCsv）：
將 config.json 嘅 groups/routes 輸出成 CSV 表格寫入飛書 spreadsheet「config」子表，
欄位：組別、地區、營運商、路線、車站、車站ID、方向、目的地、班次類型。

用法：python3 scripts/sync_routes_to_sheet.py
（使用 --as user 身份；寫入前會清空 config sheet 再重寫，保證同網頁匯出一致）
"""
import json
import os
import subprocess
import sys

SHEET_URL = "https://my.feishu.cn/sheets/SuPnsHw8Ohl6XNt1F4KcbPJpn3d"
SHEET_NAME = "config"
CLEAR_RANGE = "config!A1:I200"

CO_NAMES = {"kmb": "九巴", "ctb": "城巴", "gmb": "小巴"}
HEADERS = ["組別", "地區", "營運商", "路線", "車站", "車站ID", "方向", "目的地", "班次類型"]


def load_config():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo_dir, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def build_rows(cfg):
    rows = []
    for g in cfg.get("groups", []):
        for r in g.get("routes", []):
            rows.append([
                g.get("title", ""),
                g.get("region", "") or "",
                CO_NAMES.get(r.get("co"), r.get("co", "")),
                str(r.get("route", "")),
                r.get("stopName", "") or "",
                str(r.get("stopId", "")),
                "去程" if r.get("dir") == "O" else "回程" if r.get("dir") == "I" else "不適用",
                r.get("dest", "") or "",
                str(r.get("serviceType", 1)),
            ])
    return rows


def run_cli(args, input_data=None):
    proc = subprocess.run(args, input=input_data, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        sys.stderr.write("命令失敗: " + " ".join(args) + "\n")
        sys.stderr.write(proc.stderr + "\n")
        sys.exit(1)
    return proc


def main():
    cfg = load_config()
    rows = build_rows(cfg)
    if not rows:
        sys.stderr.write("config.json 無路線資料，唔同步。\n")
        sys.exit(1)

    # 1) 清空 config sheet（保留空白格式內容重寫，避免殘留舊行）
    run_cli([
        "lark-cli", "sheets", "+cells-batch-clear",
        "--url", SHEET_URL,
        "--ranges", json.dumps([CLEAR_RANGE], ensure_ascii=False),
        "--scope", "all", "--yes", "--as", "user",
    ])

    # 2) 寫入（table-put：全部欄位以文本寫入，保留前導零等字面值）
    payload = json.dumps({
        "sheets": [{
            "name": SHEET_NAME,
            "columns": HEADERS,
            "data": rows,
            "dtypes": {h: "object" for h in HEADERS},
        }]
    }, ensure_ascii=False)
    run_cli([
        "lark-cli", "sheets", "+table-put",
        "--url", SHEET_URL,
        "--sheets", "-", "--as", "user",
    ], input_data=payload)

    print(f"✅ 已同步 {len(rows)} 條路線去「{SHEET_NAME}」sheet")


if __name__ == "__main__":
    main()
