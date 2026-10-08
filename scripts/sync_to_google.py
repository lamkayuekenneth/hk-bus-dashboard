#!/usr/bin/env python3
"""將 config.json 同步寫入 Google Sheets（第一張工作表）。

觸發：每次 push 更新 config.json 之後，由 GitHub Actions 自動執行。
認證用 Google Cloud service account（GitHub Secret：GOOGLE_SERVICE_ACCOUNT_JSON），
寫入目標（GitHub Secret：GOOGLE_SHEET_ID）由 Actions 環境提供。
"""
import json
import os
import sys
import urllib.request

CONFIG_FILE = "config.json"
HEADERS = ["組別", "地區", "營運商", "路線", "車站", "車站ID", "方向", "目的地", "班次類型"]
CO_NAME = {"kmb": "九巴", "ctb": "城巴", "gmb": "綠色小巴"}
CLEAR_RANGE = "A1:I2000"  # 先清空預留範圍，再寫入，避免舊資料殘留


def google_request(url, method, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    cred_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not (cred_json and sheet_id):
        print("缺少 Secrets：GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SHEET_ID")
        sys.exit(1)

    # 1) service account → OAuth2 access token
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(
        json.loads(cred_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    token = creds.token

    base = "https://sheets.googleapis.com/v4/spreadsheets/%s/values" % sheet_id

    # 2) 由 config.json 組行列（同 Google Sheet 欄位一致）
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

    # 3) 清空預留範圍，再寫入
    google_request(base + "/" + CLEAR_RANGE + ":clear", "POST", token, {})
    n = len(rows)
    write_range = "A1:%s%d" % (chr(ord("A") + len(HEADERS) - 1), n)
    res = google_request(base + "/" + write_range + "?valueInputOption=USER_ENTERED",
                         "PUT", token, {"values": rows, "majorDimension": "ROWS"})
    updated = res.get("updatedCells", 0)
    print("SYNC_OK：已寫入 %d 行（%d 格）到 Google Sheets" % (n, updated))


if __name__ == "__main__":
    main()
