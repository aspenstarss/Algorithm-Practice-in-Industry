# data

本分支存放 arxiv_daily 的每日论文 JSON（YYYYMMDD.json）。
- 由 arxiv_daily_full / arxiv_daily_recovery workflow 自动写入
- feishu 推送与 HTML 生成通过 checkout 挂载到 paperBotV2/arxiv_daily/data 读取
- main 分支只放代码，不存数据
