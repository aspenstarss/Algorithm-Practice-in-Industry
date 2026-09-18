# CONTEXT

paperBotV2 的领域词汇与既定决策。架构改动应使用这里的名词，不要另造同义词。

## 领域词汇

- **业务日（business date）**：一条每日数据归属的日期，全系统唯一口径 = 北京时间（UTC+8，固定偏移，无夏令时）。由 `paperBotV2/arxiv_daily/daily_store.py` 的 `business_date()` 提供；每日文件的写入、飞书推送的新鲜度闸门、HTML 日历、status 的日期键全部以它为准。
- **每日数据文件**：`data/YYYYMMDD.json`，内容为 `arxiv_id -> paper` 的字典。有效文件 = 严格 8 位数字日期命名，有效性判定只有 daily_store 一处；`results.json`、缓存等其他文件不属于数据集。
- **data 分支**：每日数据文件的居住地。main 分支只放代码、体积恒定；workflow 把 data 分支挂载到 `paperBotV2/arxiv_daily/data` 路径读写，crawl 完成后立即推送（先于生成与部署，任何后续失败都不丢数据）。
- **status 队列**：`status/` 下的运行状态（当日 JSON + runs.csv），只保留最近 30 天，status.py 在每次写入后自动清理。
- **粗排/精排**：LLM 两级筛选。粗排按标题打相关性分（阈值 `ROUGH_SCORE_THRESHOLD`）淘汰；精排对幸存者产出评分、推荐理由与中文翻译，取前 `RETURN_PAPERS` 篇。

## 既定决策（不要回退）

- 每日数据不进 main（2026-09 决策）：数据住 data 分支，main 的 commit 步骤不碰 `data/`。
- `results.json` 累积库已废除（2026-09 决策）：无消费者、单文件无限增长会撞 GitHub 100MB 限制。
- 失败必须显式：加载/渲染/发送失败一律非 0 退出；「最新数据不是今天」属于业务态（exit 0），不是故障。
