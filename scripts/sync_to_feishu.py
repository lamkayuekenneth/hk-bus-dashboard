#!/usr/bin/env python3
"""將 config.json 同步寫入飛書（豆包雲端）表格「關注路線」。

觸發：每次 push 更新 config.json 之後，由 GitHub Actions 自動執行。
認證資料由 GitHub Secrets 提供（FEISHU_APP_ID / FEISHU_APP_SECRET /
FEISHU_SPREADSHEET_TOKEN），不會寫入任何檔案或輸出。
"""
import json
import os
import sys
import urllib.request

CONFIG_FILE = "config.json"
SHEET_NAME = "關注路線"
HEADERS = ["組別", "地區", "營運商", "路線", "車站", "車站ID", "方向", "目的地", "班次類型"]
CO_NAME = {"kmb": "九巴", "ctb": "城巴", "gmb": "綠色小巴"}


def api(url, payload, token=None, method="POST"):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    spreadsheet_token = os.environ.get("FEISHU_SPREADSHEET_TOKEN", "")
    if not (app_id and app_secret and spreadsheet_token):
        print("缺少 Secrets：FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_SPREADSHEET_TOKEN")
        sys.exit(1)

    # 1) 攞 tenant_access_token
    tok = api("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
              {"app_id": app_id, "app_secret": app_secret})
    if tok.get("code") != 0:
        print("攞 token 失敗：", tok)
        sys.exit(1)
    token = tok["tenant_access_token"]

    # 2) 由 config.json 組行列（同飛書表格欄位一致）
    cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
    rows = [HEADERS]
    for g in cfg.get("groups", []):
        for r in g.get("routes", []):
            rows.append([
                g.get("title", ""), g.get("region", ""),
                CO_NAME.get(r.get("co", ""), r.get("co", "")),
                r.get("route", ""), r.get("stopName", ""), r.get("stopId", ""),
                "去程" if r.get("dir") == "O" else ("回程" if r.get("dir") == "I" else "不適用"),
                r.get("dest", ""), r.get("serviceType", 1),
            ])

    last_col = chr(ord("A") + len(HEADERS) - 1)
    range_spec = "%s!A1:%s%d" % (SHEET_NAME, last_col, len(rows))

    # 3) 覆寫寫入表格
    res = api("https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/%s/values" % spreadsheet_token,
              {"valueRange": {"range": range_spec, "values": rows}}, token=token, method="PUT")
    if res.get("code") != 0:
        print("寫入失敗：", json.dumps(res, ensure_ascii=False))
        sys.exit(1)
    print("SYNC_OK：已寫入 %d 行（含表頭）到「%s」" % (len(rows), SHEET_NAME))


if __name__ == "__main__":
    main()
