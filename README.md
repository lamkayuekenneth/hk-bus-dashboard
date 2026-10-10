# 巴士到站 Dashboard (HK Bus ETA Dashboard)

一個可公開瀏覽嘅香港巴士／小巴實時到站儀表板：支援 **城巴、九巴、綠色小巴** 官方開放數據 ETA，可隨時新增／刪除你關注嘅路線同車站、自訂組別（group）標題、按地區同路線篩選，並可部署到 **GitHub Pages** 免費公開瀏覽。

## 功能

- **即時到站（ETA）**：九巴、城巴、綠色小巴三間營運商官方開放數據，顯示下一班到站分鐘數＋鐘面時間＋後續兩班，仲有「訊號未回傳 NEXT SIGNAL」／「API ERROR」狀態顯示
- **自訂組別**：路線歸入你自己命名嘅組別（例如「觀塘:往港島」），每個組別有獨立板塊
- **隨時增刪**：喺網頁上「編輯路線」刪除個別路線、「+ 新增組別」建組、「編輯組別／刪除組別」管理；所有改動即時生效並記入瀏覽器
- **篩選**：按地區、組別、路線號即時過濾
- **GPS 距離**：開啟 GPS 顯示每個車站同你嘅直線距離（米）
- **自訂排序**：上移／下移調整路線顯示次序
- **自動更新**：預設每 60 秒自動刷新，可手動「刷新全部」
- **該站車費**：每條路線顯示由該站上車至該方向終點嘅分段車費（非全程價）。巴士數據經 `scripts/sync_fare.py`（運輸署全程收費）＋ `scripts/sync_fare_v2.py`（681 巴士總站分段收費表，整理自營運商官方收費，套用至逐站）生成 `fare_bus.json`；小巴經 `scripts/sync_fare_gmb_v2.py`（運輸署 HK eMobility GMB Faretable，逐站分段）生成 `fare_gmb.json`。已驗證與城巴 App 逐站車費一致（如 81 寶峰園→勵德邨 $5.5、8H 寶峰園→東華東院 $5.5、65 立德里→北角碼頭 $5.5、小巴 69 逸港居→數碼港 $7.0）。已知限制：巴士循環線維持全程收費（循環線分段屬「落車分段」模型，與「上車→終點」唔相容）；九巴站名無街道後綴，681 分段表街道名未能完全對應嘅路線維持全程價；小巴只有能可靠對照分段邊界嘅路線（目前 69）套用分段，其餘維持運輸署全程收費。

## 檔案結構

```
hk-bus-dashboard/
├── index.html      # 主應用程式（單檔自包含，CSS + JS 全內聯）
├── config.json     # 種子設定：組別、地區、路線、車站、方向、目的地
├── fare_bus.json   # 巴士車費資料 v2（分段收費：每站「上車→該方向終點」車費；681 分段表＋運輸署站點）
├── fare_gmb.json   # 綠色小巴車費資料 v2（分段收費：69 等已套用分段，其餘維持全程價）
└── README.md       # 本文件
```

`config.json` 欄位對應你嘅豆包雲端 spreadsheet「關注路線」：
`組別 → groups[].title`、`地區 → groups[].region`、`營運商 → routes[].co`、`路線 → routes[].route`、`車站 → routes[].stopName`、`車站ID → routes[].stopId`、`方向 → routes[].dir`、`目的地 → routes[].dest`、`班次類型 → routes[].serviceType`。

## 部署到 GitHub Pages（公開瀏覽）

### 方法 A：自己 push（推薦，最快）

1. 喺 GitHub 開一個新 repository（Public）
2. 將呢個資料夾入面嘅 `index.html` 同 `config.json` 放喺 repo 根部
3. 開啓 GitHub Pages：
   - Repo → **Settings** → **Pages**
   - **Source** 揀 `Deploy from a branch` → Branch 揀 `main`（或 master）→ `/ (root)` → **Save**
4. 等 1–2 分鐘，即可喺 `https://<你的用戶名>.github.io/<repo名>/` 公開瀏覽

### 方法 B：由我幫你 push

如果你想我直接幫你上傳，請：

1. 喺 GitHub 開好 Public repo（或者話我知你想要嘅 repo 名）
2. 提供一個 **Personal Access Token**（權限只需 `repo`）——設定路徑：GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → 勾 `Contents: Read and write`，scope 只限你嘅目標 repo
3. 話我知 repo 名，我就會幫你 push 埋 `index.html`、`config.json`、`README.md`

> 安全提示：token 等同帳號密碼，用完可以即刻喺 GitHub 撤銷。亦可以自己 push 唔使俾 token 我。

## 點樣記錄關注路線（豆包雲端 spreadsheet ↔ 網頁）

- **雲端 spreadsheet**（豆包／飛書表格「香港巴士到站儀表板 - 關注路線」）係你嘅路線登記簿，可以喺度加減路線、睇返每個欄位嘅意思
- **網頁內改動**：喺儀表板按「匯出設定」會下載 `config.json`，將改動貼返入 GitHub repo 再 push，公開發佈版就會同步
- **本地即時生效**：喺網頁上加嘅路線／組別會即刻存喺瀏覽器 localStorage，唔使改檔案

## 開放數據來源

| 營運商 | API |
| --- | --- |
| 九巴 KMB | `https://data.etabus.gov.hk/v1/transport/kmb/` |
| 城巴 CTB | `https://rt.data.gov.hk/v2/transport/citybus/` |
| 綠色小巴 GMB | `https://data.etagmb.gov.hk/` |
| 車費資料（運輸署） | `https://static.data.gov.hk/td/routes-fares-geojson/JSON_BUS.json`、`JSON_GMB.json`（經 `scripts/sync_fare.py` 精簡入 repo；全程收費） |
| 小巴分段收費（運輸署 HK eMobility） | `https://h2-app-rr.hkemobility.gov.hk/ris_page/get_gmb_detail.php?route_id=<id>`（GMB Faretable，路段×路段車資表；`fare_gmb.json` 嘅 route id 即係 hkemobility route_id） |
| 分段收費（681 巴士總站） | `https://www.681busterminal.com/`（收費表整理自營運商官方，經 `scripts/sync_fare_v2.py` 套用至逐站） |

ETA 數據屬官方開放數據，實際到站時間以營運商發佈為準；部分路線（如 641）於非服務時段會顯示「訊號未回傳」。

## 自動同步去 Google Sheets（GitHub Actions）

每次 push `config.json`，GitHub 會自動將路線清單寫入你嘅 Google Sheet，唔使手動貼。設定步驟：

1. **開 Google Cloud Project**：`console.cloud.google.com` → 新建專案（例如 `hkbus-sync`）
2. **啟用 API**：專案內 → API 和服務 → 啟用 API 和服務 → 搜尋並啟用 **Google Sheets API**
3. **建 Service Account**：IAM 和管理 → 服務帳戶 → 建立服務帳戶（例如 `hkbus-sync`）→ 建立後喺「金鑰」分頁 → **新增金鑰 → JSON** → 下載（會得到一個 `xxx.json`）
4. **開 Google Sheet**：用你嘅 Google 帳號喺 Google Drive 開一個新 Google 表格（例如「HK Bus 路線」），記低網址入面嘅 **Spreadsheet ID**（`/spreadsheets/d/XXXX/edit` 中嘅 `XXXX`）
5. **分享俾服務帳戶**：表格右上角「分享」→ 輸入第 3 步嘅 service account email（格式 `xxx@hkbus-sync.iam.gserviceaccount.com`）→ 權限揀「編輯者」
6. **加入 GitHub Secrets**：repo → **Settings → Secrets and variables → Actions** 加兩個：
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = 第 3 步下載嘅 JSON 金鑰成個內容（連大括號，可以直接成段貼入去）
   - `GOOGLE_SHEET_ID` = 第 4 步嘅 Spreadsheet ID
7. 之後每次 push `config.json`，Actions 自動執行 `scripts/sync_to_google.py` 寫入表格（第一張工作表）

另：網頁底部有「匯出路線表 CSV」掣，編輯完可以即刻下載 CSV（Excel 可直接開啟），自己貼返入表格。

## 技術備註

- 單檔自包含 HTML，無需 build、無後端、無 API key
- 全部資料經瀏覽器直接呼叫政府開放數據 API（支援 CORS）
- 響應式設計：手機同桌面都用到
- 如果喺沙箱／開發環境見到 34M 顯示 API ERROR，屬環境網絡限制；喺真實瀏覽器（GitHub Pages）會正常顯示
