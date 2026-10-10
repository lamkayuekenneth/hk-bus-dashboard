#!/bin/bash
# 驗證式 push：commit + push + 確認 remote 已收到相同 commit 先至成功
# 用法：GITHUB_TOKEN=<token> ./scripts/push_verified.sh "<commit message>"
set -e
cd "$(dirname "$0")/.."

if [ -z "$1" ]; then
  echo "用法: GITHUB_TOKEN=<token> $0 \"<commit message>\"" >&2
  exit 2
fi
MSG="$1"
TOKEN="${GITHUB_TOKEN:?需設定 GITHUB_TOKEN 環境變數}"
REMOTE="https://lamkayuekenneth:${TOKEN}@github.com/lamkayuekenneth/hk-bus-dashboard.git"

# 1) 先 fetch 最新 remote，有分歧就 merge（保留雙方改動）
git -c http.version=HTTP/1.1 fetch "$REMOTE" main -q || { echo "❌ fetch 失敗" >&2; exit 1; }
if git log --oneline HEAD..FETCH_HEAD | grep -q .; then
  echo "→ remote 有新 commit，合併中..."
  git merge FETCH_HEAD --no-edit
fi

# 2) 冇變更（含未追蹤新檔）就唔 commit
if git diff --cached --quiet && git diff --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "ℹ️  沒有變更需要提交"
  exit 0
fi

# 3) commit + push
git add -A
git commit -m "$MSG"
git -c http.version=HTTP/1.1 push "$REMOTE" main

# 4) 驗證：再 fetch，比較 local HEAD 同 remote HEAD 是否一致
git -c http.version=HTTP/1.1 fetch "$REMOTE" main -q
LOCAL=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse FETCH_HEAD)
if [ "$LOCAL" = "$REMOTE_HEAD" ]; then
  echo "✅ PUSH 驗證成功：commit $LOCAL 已確認喺 GitHub main"
else
  echo "❌ PUSH 驗證失敗：local=$LOCAL remote=$REMOTE_HEAD（可能被其他 commit 超越，或 push 未完成）" >&2
  exit 1
fi
