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

# 推送篇数与主流程同一配置源（paperBotV2/arxiv_daily/config.py）
RETURN_PAPERS = config.load().return_papers


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
    
    # 检查是否有有效的飞书URL
    feishu_urls = notify.parse_urls(os.environ.get("FEISHU_URL", ""))
    if not feishu_urls:
        print("⚠️ 环境变量FEISHU_URL未设置或为空，无法发送飞书消息")
        return

    print(f"📤 准备发送 {len(selected_papers)} 篇论文到 {len(feishu_urls)} 个飞书URL...")

    # 发送到飞书
    if selected_papers:
        display_date = f"{file_date_str[:4]}-{file_date_str[4:6]}-{file_date_str[6:]}"
        notify.send(feishu_urls, notify.papers_card(selected_papers, date=display_date))
        print("✅ 飞书消息发送完成！")
    else:
        print("⚠️ 没有符合条件的论文可以发送")


if __name__ == "__main__":
    main()
