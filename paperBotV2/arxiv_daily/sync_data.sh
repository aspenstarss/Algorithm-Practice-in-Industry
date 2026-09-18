#!/usr/bin/env bash
# 从远端 data 分支同步每日论文 JSON 到本地 paperBotV2/arxiv_daily/data/
# 用法：仓库内任意位置执行  ./paperBotV2/arxiv_daily/sync_data.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

git fetch origin data

dest="paperBotV2/arxiv_daily/data"
mkdir -p "$dest"

# data 分支根目录平铺 YYYYMMDD.json；README.md 是说明文件，不落进数据目录
git archive origin/data | tar -x -C "$dest" --exclude=README.md

count=$(find "$dest" -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')
echo "✅ 已同步 ${count} 个数据文件到 ${dest}"
