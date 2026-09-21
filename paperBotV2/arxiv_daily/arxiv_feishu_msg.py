import os
import sys

# 同级模块（daily_store）与包级模块（notify）都需要在 sys.path 上
_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.dirname(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import daily_store
import config
import notify
import page_logic

# 推送篇数与主流程同一配置源（paperBotV2/arxiv_daily/config.py）
RETURN_PAPERS = config.load().return_papers
RELATED_PREVIEW_COUNT = 10  # 沾边速览附卡最多条数（只列标题+粗排分）


def main():
    """主函数，读取最新论文数据并发送飞书消息"""
    if not os.path.isdir(daily_store.DATA_DIR):
        print(f"❌ 数据目录不存在: {daily_store.DATA_DIR}（说明 arxiv_daily_full 尚未成功运行）")
        sys.exit(1)

    # 获取最新一天的数据
    latest_entry = daily_store.latest()
    if not latest_entry:
        print("无法获取最新的JSON文件，程序退出")
        sys.exit(1)

    # 业务日闸门：只有当日数据才推送（文件日期与业务日口径统一，均为北京时间）
    file_date_str, papers = latest_entry
    today = daily_store.business_date()
    if file_date_str != today:
        print(f"⚠️ 最新文件的日期 {file_date_str} 不是今天 {today}，避免重复发送，程序退出")
        return
    
    # 按照精排分数排序并选择前N篇论文
    papers_with_score = [p for p in papers if 'rerank_relevance_score' in p and p.get('is_fine_ranked', False)]
    papers_with_score.sort(key=lambda x: x['rerank_relevance_score'], reverse=True)
    selected_papers = papers_with_score[:RETURN_PAPERS]

    # 沾边速览：related 过线且未进精选的论文，按粗排分取前 N 条标题
    threshold = config.load().rough_score_threshold
    related_papers = [
        p for p in papers
        if not p.get('is_filtered', True)
        and page_logic.paper_track(p, threshold) == page_logic.TRACK_RELATED
        and not p.get('is_fine_ranked', False)
    ]
    related_papers.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    related_preview = related_papers[:RELATED_PREVIEW_COUNT]

    # 检查是否有有效的飞书URL
    feishu_urls = notify.parse_urls(os.environ.get("FEISHU_URL", ""))
    if not feishu_urls:
        print("⚠️ 环境变量FEISHU_URL未设置或为空，无法发送飞书消息")
        return

    print(f"📤 准备发送 {len(selected_papers)} 篇核心精选 + {len(related_preview)} 条沾边速览到 {len(feishu_urls)} 个飞书URL...")

    # 发送到飞书：核心精选主卡 + 沾边速览附卡（任一有内容即发）
    if not selected_papers and not related_preview:
        print("⚠️ 没有符合条件的论文可以发送")
        return

    display_date = f"{file_date_str[:4]}-{file_date_str[4:6]}-{file_date_str[6:]}"
    if selected_papers:
        notify.send(feishu_urls, notify.papers_card(selected_papers, date=display_date))
        print(f"✅ 核心精选 {len(selected_papers)} 篇发送完成！")
    if related_preview:
        notify.send(feishu_urls, notify.related_brief_card(related_preview, date=display_date))
        print(f"✅ 沾边速览 {len(related_preview)} 条发送完成！")


if __name__ == "__main__":
    main()
