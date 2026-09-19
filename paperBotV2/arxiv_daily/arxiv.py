import re
import os
import requests
import json
import time
import feedparser
import random
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .prompts import PRERANK_PROMPT, FINERANK_PROMPT
from .status import ArxivDailyStatus
from . import daily_store as _store
from . import new_listing as _listing
from .. import llm as _llm
from .config import load as _load_config

# 抓取/排序配置唯一来源：paperBotV2/arxiv_daily/config.py（调参走 git，勿在 yml 重复）
SETTINGS = _load_config()

ID_LIST_BATCH_SIZE = 40  # id_list 单批大小：官方未公布上限，40 为已验证的稳妥值


class ArxivFetchError(RuntimeError):
    """Raised when arXiv data cannot be fetched reliably."""


def sleep_with_jitter(base_seconds, reason):
    """带随机抖动的 sleep，降低固定节奏触发 arXiv 限流的概率。"""
    if base_seconds <= 0:
        return
    jitter = random.randint(0, SETTINGS.jitter_seconds) if SETTINGS.jitter_seconds > 0 else 0
    total_seconds = base_seconds + jitter
    print(f"⏱️ {reason}，等待 {total_seconds}s（基础 {base_seconds}s + 抖动 {jitter}s）")
    time.sleep(total_seconds)


def get_category_max_pages(category):
    """优先使用分类级页数上限，降低低产分类不必要请求次数。"""
    return SETTINGS.category_max_pages.get(category, SETTINGS.max_pages)


def load_today_cached_papers(category):
    """同一天手动重跑时优先复用已有成功结果，减少重复请求 arXiv。"""
    if not SETTINGS.use_daily_cache:
        return {}

    try:
        today_data = _store.load_raw(_store.business_date())
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"⚠️ 读取今日缓存失败，将继续请求 arXiv: {exc}")
        return {}

    cached = {
        arxiv_id: paper
        for arxiv_id, paper in today_data.items()
        if category in paper.get('categories', '')
    }
    if cached:
        print(f"📦 分类 '{category}' 复用今日缓存 {len(cached)} 篇论文，跳过 arXiv 请求。")
    return cached


def parse_arxiv_entry(entry):
    """将 arXiv feed entry 转换为内部论文结构。"""
    title = re.sub(r'\s+', ' ', entry.title.replace('\n', ' ').strip())
    arxiv_id = entry.id.split('/abs/')[-1]
    alphaxiv_link = f"https://www.alphaxiv.org/abs/{arxiv_id}"
    authors = ', '.join(author.name for author in entry.authors)
    summary = re.sub(r'\s+', ' ', entry.summary.replace('\n', ' ').strip())
    published_date = entry.published_parsed
    published_str = datetime(*published_date[:6]).strftime('%Y-%m-%d %H:%M:%S')
    categories = ', '.join(tag.term for tag in entry.tags)

    return arxiv_id, {
        'title': title,
        'url': alphaxiv_link,
        'arxiv_id': arxiv_id,
        'authors': authors,
        'categories': categories,
        'pub_date': published_str,
        'ori_summary': summary,
        'summary': '',  # 占位，后续由 LLM 填充
        'translation': '',  # 占位，后续由 LLM 填充
        'relevance_score': 0,  # 占位，后续由 LLM 填充
        'reasoning': '',  # 占位，后续由 LLM 填充
        'rerank_relevance_score': 0,  # 占位，后续由 LLM 填充
        'rerank_reasoning': '',  # 占位，后续由 LLM 填充
    }


def get_retry_wait_seconds(response, attempt):
    """优先遵循 Retry-After，否则使用指数退避。"""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return min(int(retry_after), SETTINGS.retry_max_wait)
        except ValueError:
            pass
    return min(SETTINGS.retry_base_wait * (2 ** (attempt - 1)), SETTINGS.retry_max_wait)


def request_arxiv_page(base_urls, query_params):
    """请求单页 arXiv API；遇到 429/5xx 时长退避重试。"""
    headers = {"User-Agent": SETTINGS.user_agent}
    last_error = None
    if isinstance(base_urls, str):
        base_urls = [base_urls]

    for attempt in range(1, SETTINGS.retry_attempts + 1):
        retryable_failure = False
        last_response = None
        for base_url in base_urls:
            try:
                response = requests.get(
                    base_url,
                    params=query_params,
                    headers=headers,
                    timeout=(5, 30),
                )
                last_response = response
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    last_error = requests.exceptions.HTTPError(
                        f"{response.status_code} error from {base_url}"
                    )
                    retryable_failure = True
                    print(
                        f"⏳ arXiv API {base_url} 返回 {response.status_code}，"
                        f"第 {attempt}/{SETTINGS.retry_attempts} 轮重试..."
                    )
                    continue

                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as exc:
                last_error = exc
                retryable_failure = True
                print(
                    f"⏳ arXiv API {base_url} 请求异常: {exc}，"
                    f"第 {attempt}/{SETTINGS.retry_attempts} 轮重试..."
                )

        if attempt == SETTINGS.retry_attempts:
            break

        wait_seconds = get_retry_wait_seconds(last_response if retryable_failure else None, attempt)
        jitter = random.randint(0, SETTINGS.jitter_seconds) if SETTINGS.jitter_seconds > 0 else 0
        total_wait = min(wait_seconds + jitter, SETTINGS.retry_max_wait)
        print(
            f"⏳ 本轮 arXiv API 请求未成功，等待 {total_wait}s "
            f"（基础 {wait_seconds}s + 抖动 {jitter}s）后重试..."
        )
        time.sleep(total_wait)

    raise ArxivFetchError(f"arXiv API 请求多次失败: {last_error}")


def get_daily_arxiv_papers(category='cs.CL', max_results=20, seen_ids=None):
    """
    获取指定 arXiv 分类当前公告批次的新论文。

    主路径：/list/{category}/new 公告页提取 ID（公告批次语义，含积压释放的
    论文——任何 submittedDate 查询都无法完整覆盖），滚动去重后经 id_list
    批量取元数据。公告页不可用时回退 submittedDate 窗口查询（有周末漏批
    的已知缺陷，仅作降级）。

    Args:
        category: 你感兴趣的 arXiv 类别，例如 'cs.CL', 'cs.AI', 'stat.ML'。
        max_results: 单类抓取论文数上限。
        seen_ids: 最近 N 天已入库的论文 ID（裸 ID，无版本号），用于滚动去重。
    """
    seen_ids = seen_ids or set()
    try:
        html = _listing.fetch_listing_html(
            category, SETTINGS.listing_base_url, SETTINGS.user_agent)
        listing_ids = _listing.parse_new_listing_ids(html)
    except (requests.exceptions.RequestException, _listing.ListingParseError) as exc:
        print(f"⚠️ 公告页抓取/解析失败，回退 submittedDate 窗口查询: {exc}")
        return _get_papers_by_window(category, max_results)

    fresh_ids = [arxiv_id for arxiv_id in listing_ids if arxiv_id not in seen_ids]
    skipped = len(listing_ids) - len(fresh_ids)
    truncated = len(fresh_ids) > max_results
    fresh_ids = fresh_ids[:max_results]
    print(
        f"📰 分类 '{category}' 公告批次共 {len(listing_ids)} 篇，"
        f"滚动去重剔除 {skipped} 篇已见论文，待抓取 {len(fresh_ids)} 篇"
        + ("（超出单类上限，已截断）" if truncated else "")
    )
    print("=" * 50)

    if not fresh_ids:
        print(f"📭 分类 '{category}' 公告批次内没有未入库的新论文。")
        return {}, 0

    return _fetch_papers_by_ids(fresh_ids, category)


def _fetch_papers_by_ids(arxiv_ids, category):
    """经 arXiv API id_list 批量拉取论文元数据，返回 (results, 批次数)。"""
    results = {}
    pages = 0
    for start in range(0, len(arxiv_ids), ID_LIST_BATCH_SIZE):
        batch = arxiv_ids[start:start + ID_LIST_BATCH_SIZE]
        response = request_arxiv_page(SETTINGS.api_base_urls, {
            'id_list': ','.join(batch),
            'max_results': len(batch),
        })
        feed = feedparser.parse(response.content)
        pages += 1
        for entry in feed.entries:
            arxiv_id, paper = parse_arxiv_entry(entry)
            results[arxiv_id] = paper
        missing = len(batch) - len(feed.entries)
        if missing > 0:
            print(f"⚠️ 分类 '{category}' 有 {missing} 篇论文未从 API 返回（可能已被撤稿）")
        if start + ID_LIST_BATCH_SIZE < len(arxiv_ids):
            sleep_with_jitter(SETTINGS.request_interval, f"分类 '{category}' id_list 批次间隔")

    print(f"✅ 分类 '{category}' 共抓取 {len(results)} 篇论文。")
    return results, pages


def _get_papers_by_window(category='cs.CL', max_results=20):
    """回退路径：submittedDate 窗口查询。

    公告滞后于提交（周五/周六晚无公告、积压释放的论文 submittedDate 更早），
    该路径在周末与积压场景会漏批，仅作公告页不可用时的降级。
    """
    results = {}
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=SETTINGS.lookback_hours)
    start_date_str = start_utc.strftime('%Y%m%d%H%M%S')
    end_date_str = end_utc.strftime('%Y%m%d%H%M%S')
    search_query = f'cat:{category} AND submittedDate:[{start_date_str} TO {end_date_str}]'

    page_size = min(max_results, SETTINGS.page_size)
    max_pages = get_category_max_pages(category)
    print(
        f"🔍 [回退] 开始抓取分类 '{category}'，窗口: {start_utc.isoformat()} -> {end_utc.isoformat()}，"
        f"page_size={page_size}, max_pages={max_pages}"
    )
    print("=" * 50)

    pages_fetched = 0
    for page in range(max_pages):
        query_params = {
            'search_query': search_query,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending',
            'start': page * page_size,
            'max_results': page_size,
        }

        response = request_arxiv_page(SETTINGS.api_base_urls, query_params)
        feed = feedparser.parse(response.content)
        entries = feed.entries
        pages_fetched = page + 1
        print(f"📄 分类 '{category}' 第 {page + 1} 页返回 {len(entries)} 篇论文")

        if not entries:
            break

        for entry in entries:
            arxiv_id, paper = parse_arxiv_entry(entry)
            results[arxiv_id] = paper

        if len(entries) < page_size:
            break

        sleep_with_jitter(SETTINGS.request_interval, f"分类 '{category}' 分页请求间隔")

    if not results:
        print(f"📭 分类 '{category}' 在 {SETTINGS.lookback_hours} 小时窗口内没有新论文。")
    else:
        print(f"✅ 分类 '{category}' 共抓取 {len(results)} 篇论文。")

    return results, pages_fetched


def rough_analyze_paper(arxiv_id, paper):
    prompt = PRERANK_PROMPT.format(title=paper['title'])
    analysis = _llm.json_call(prompt)
    if analysis:
        # 将分析结果合并到原始论文信息中
        paper.update(analysis)
        return paper
    else:
        # 即使分析失败，也打印日志，但返回 None
        print(f"❌ [{arxiv_id}] {paper['title']} - 分析失败")
        return None


def rough_analyze_papers_cocurrent(results, max_workers=10):
    analyzed_papers = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_paper = {
            executor.submit(rough_analyze_paper, arxiv_id, paper): paper
            for arxiv_id, paper in results.items()
        }
        print(f"\n🚀 开始并发分析 {len(results)} 篇论文，使用 {max_workers} 个工作线程...")
        progress_bar = tqdm(as_completed(future_to_paper),
                            total=len(results), desc="分析进度")
        failed = 0
        for future in progress_bar:
            try:
                updated_paper = future.result()
                if updated_paper:
                    analyzed_papers.append(updated_paper)
            except Exception as exc:
                failed += 1
                paper_info = future_to_paper[future]
                print(f"⚠️ 处理论文 {paper_info['title']} 时产生异常: {exc}")
    total = len(results)
    if total and failed == total:
        raise RuntimeError(f"LLM 粗排全部失败（{failed}/{total}），疑似 API 故障，终止本次运行")
    if failed:
        print(f"⚠️ 粗排部分失败：{failed}/{total} 篇被丢弃（已计入 status 的 rough_rank_failed）")
    if not analyzed_papers:
        print("📭 \n没有成功分析任何论文。")
        return []
    print(f"\n✅ 所有论文分析完成，成功处理 {len(analyzed_papers)} 篇。")
    return analyzed_papers


def rough_rank_papers(results, filter_threshold=2, max_workers=10):
    # LLM rough analyze papers concurrently
    analyzed_papers = rough_analyze_papers_cocurrent(
        results, max_workers=max_workers)

    # 核心排序逻辑：按 relevance_score 降序排序
    analyzed_papers.sort(key=lambda p: p.get(
        'relevance_score', 0), reverse=True)

    # 打印排序和过滤前的结果预览
    print("\n--- 分析结果预览 (按相关性排序) ---")
    for paper in analyzed_papers:
        print("-" * 60)
        print(f"✅ [{paper['arxiv_id']}] {paper['title']}")
        print(f"  - 翻译: {paper.get('translation', 'N/A')}")
        print(f"  - 相关性评分: {paper.get('relevance_score', 'N/A')}/10")
        print(f"  - 理由: {paper.get('reasoning', 'N/A')}")
    print("-" * 60)

    # 过滤低分论文
    filtered_papers = [p for p in analyzed_papers if p.get(
        'relevance_score', 0) >= filter_threshold]
    print(
        f"\n⚠️ 过滤掉 {len(analyzed_papers) - len(filtered_papers)} 篇低分论文，剩余 {len(filtered_papers)} 篇高质量论文。")
    return filtered_papers, analyzed_papers


def fine_analyze_paper(arxiv_id, paper):
    prompt = FINERANK_PROMPT.format(
        title=paper['title'], summary=paper['ori_summary'])
    analysis = _llm.json_call(prompt)
    if analysis:
        # 将分析结果合并到原始论文信息中
        paper.update(analysis)
        return paper
    else:
        # 即使分析失败，也打印日志，但返回 None
        print(f"❌ [{arxiv_id}] {paper['title']} - 分析失败")
        return None


def fine_analyze_papers_cocurrent(papers, max_workers=10):
    analyzed_papers = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_paper = {
            executor.submit(fine_analyze_paper, paper['arxiv_id'], paper): paper
            for paper in papers
        }
        print(f"\n🚀 开始并发精排 {len(papers)} 篇论文，使用 {max_workers} 个工作线程...")
        progress_bar = tqdm(as_completed(future_to_paper),
                            total=len(papers), desc="精排进度")
        failed = 0
        for future in progress_bar:
            try:
                updated_paper = future.result()
                if updated_paper:
                    analyzed_papers.append(updated_paper)
            except Exception as exc:
                failed += 1
                paper_info = future_to_paper[future]
                print(f"处理论文 {paper_info['title']} 时产生异常: {exc}")
    total = len(papers)
    if total and failed == total:
        raise RuntimeError(f"LLM 精排全部失败（{failed}/{total}），疑似 API 故障，终止本次运行")
    if failed:
        print(f"⚠️ 精排部分失败：{failed}/{total} 篇被丢弃")
    if not analyzed_papers:
        print("\n没有成功精排任何论文。")
        return []
    print(f"\n✅ 所有论文精排完成，成功处理 {len(analyzed_papers)} 篇。")
    return analyzed_papers


def fine_rank_papers(papers, max_workers=10, paper_count=5):
    papers = papers[:paper_count]  # 只精排前 N 篇论文

    # LLM fine analyze papers concurrently
    analyzed_papers = fine_analyze_papers_cocurrent(
        papers, max_workers=max_workers)

    # 核心排序逻辑：按 rerank_relevance_score 降序排序
    analyzed_papers.sort(key=lambda p: p.get(
        'rerank_relevance_score', 0), reverse=True)

    # 打印排序后的结果预览
    print("\n--- 精排结果预览 (按精排评分排序) ---")
    for paper in analyzed_papers:
        print("-" * 60)
        print(f"✅ [{paper['arxiv_id']}] {paper['title']}")
        print(f"  - 翻译: {paper.get('translation', 'N/A')}")
        print(f"  - 精排相关性评分: {paper.get('rerank_relevance_score', 'N/A')}/10")
        print(f"  - 理由: {paper.get('rerank_reasoning', 'N/A')}")
        print(f"  - 总结: {paper.get('summary', 'N/A')}")
    print("-" * 60)

    return analyzed_papers


def get_papers_from_all_categories(run_status=None):
    """从所有指定分类获取当前公告批次的新论文并初始化状态标记（抓取层已去重）。"""
    all_papers = {}

    # 滚动去重：公告页整周末保持不变（周五/周六晚无公告），靠最近 N 天
    # 已入库 ID 跳过已处理批次；缺失的历史文件容忍（当作没见过，宁可重算不漏发）
    seen = _store.seen_ids(days=SETTINGS.dedup_days)
    print(f"📋 已加载最近 {SETTINGS.dedup_days} 天的已见论文 {len(seen)} 篇。")

    # 获取当前日期的所有分类论文
    for index, category in enumerate(SETTINGS.target_categories):
        category_results = load_today_cached_papers(category)
        pages_fetched = 0
        if not category_results:
            for attempt in range(1, SETTINGS.category_retry_attempts + 1):
                try:
                    category_results, pages_fetched = get_daily_arxiv_papers(
                        category=category,
                        max_results=SETTINGS.max_papers,
                        seen_ids=seen,
                    )
                    break
                except ArxivFetchError as exc:
                    if attempt == SETTINGS.category_retry_attempts:
                        if run_status:
                            run_status.record_category_fetch(
                                category,
                                success=False,
                                papers=0,
                                pages=pages_fetched,
                                error=exc,
                            )
                        raise
                    print(
                        f"⚠️ 分类 '{category}' 第 {attempt}/{SETTINGS.category_retry_attempts} 次抓取失败: {exc}"
                    )
                    sleep_with_jitter(SETTINGS.category_interval, f"分类 '{category}' 失败后重试间隔")
        if run_status:
            run_status.record_category_fetch(
                category,
                success=True,
                papers=len(category_results),
                pages=pages_fetched,
            )
        
        # 添加到all_papers并初始化状态标记（已见论文在抓取层已被剔除）
        for arxiv_id, paper in category_results.items():
            paper['is_filtered'] = False  # 默认为未过滤
            paper['is_fine_ranked'] = False  # 默认为未精排
            all_papers[arxiv_id] = paper
        if index < len(SETTINGS.target_categories) - 1:
            sleep_with_jitter(SETTINGS.category_interval, "分类之间请求间隔")

    print(f"📚 获取到 {len(all_papers)} 篇论文。")
    return all_papers


def perform_rough_ranking(all_papers, run_status=None):
    """执行粗排并标记过滤状态"""
    # 直接使用rough_rank_papers函数进行并发粗排，获取过滤后的论文
    filtered_papers, analyzed_papers = rough_rank_papers(
        all_papers,
        filter_threshold=SETTINGS.rough_score_threshold,
        max_workers=10,
    )
    if run_status:
        run_status.record_rough_rank(
            total=len(all_papers),
            success=len(analyzed_papers),
            scores=[paper.get('relevance_score', 0) for paper in analyzed_papers],
        )
    
    # 更新all_papers中的论文信息并标记过滤状态
    for paper in filtered_papers:
        arxiv_id = paper['arxiv_id']
        all_papers[arxiv_id].update(paper)
        all_papers[arxiv_id]['is_filtered'] = False  # 通过粗排的论文
    
    # 标记未通过粗排的论文
    for arxiv_id, paper in all_papers.items():
        if arxiv_id not in [p['arxiv_id'] for p in filtered_papers]:
            all_papers[arxiv_id]['is_filtered'] = True  # 未通过粗排的论文
    
    print(f"✨ 粗排筛选 {len(filtered_papers)} 篇高质量论文。")
    return filtered_papers


def perform_fine_ranking(filtered_papers, all_papers, run_status=None):
    """执行精排并标记精排状态：按粗排分取前 fine_rank_papers 篇进精排，按精排分返回前 return_papers 篇"""
    ranked_papers = fine_rank_papers(filtered_papers, paper_count=SETTINGS.fine_rank_papers)
    final_papers = ranked_papers[:SETTINGS.return_papers]
    if run_status:
        run_status.record_fine_rank(
            total=min(len(filtered_papers), SETTINGS.fine_rank_papers),
            success=len(ranked_papers),
            scores=[paper.get('rerank_relevance_score', 0) for paper in ranked_papers],
        )
    
    for paper in final_papers:
        arxiv_id = paper['arxiv_id']
        all_papers[arxiv_id].update(paper)  # 更新精排信息
        all_papers[arxiv_id]['is_fine_ranked'] = True  # 标记为已精排
    
    print(f"🏆 精排得到 {len(final_papers)} 篇顶级论文。")
    return final_papers


def save_results_to_json(all_papers):
    """保存当天结果到每日数据文件（数据居住在 data 分支，路径约定见 daily_store）"""
    # 如果没有新论文，直接返回
    if not all_papers:
        print("📭 今天没有新论文，跳过保存JSON文件")
        return False

    daily_file = _store.save(all_papers, _store.business_date())
    print(f"💾 当天论文结果已保存到 {daily_file}")
    return True


def process_papers():
    """处理并保存论文的主函数 - 协调各个子函数的执行"""
    run_status = ArxivDailyStatus()
    try:
        # 1. 获取论文
        run_status.update_stage("fetch")
        all_papers = get_papers_from_all_categories(run_status=run_status)

        # 2. 粗排
        run_status.update_stage("rough_rank")
        filtered_papers = perform_rough_ranking(all_papers, run_status=run_status)

        # 3. 精排
        run_status.update_stage("fine_rank")
        perform_fine_ranking(filtered_papers, all_papers, run_status=run_status)

        # 4. 保存结果
        run_status.update_stage("save_json")
        daily_json_written = save_results_to_json(all_papers)
        run_status.mark_daily_json_written(daily_json_written)
        run_status.mark_success()

        print("✅ 论文处理流程已全部完成！")
    except Exception as exc:
        run_status.mark_failed(run_status.data.get("stage", "unknown"), exc)
        print(f"❌ 论文处理流程失败，状态已写入: {exc}")
        raise

    # 注意：飞书消息发送功能已移至独立脚本 send_feishu_message.py
    # 在GitHub Actions工作流中，将在网页生成完成后触发发送


# --- 主程序入口 ---
if __name__ == "__main__":
    process_papers()
