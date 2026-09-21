"""arXiv 每日论文页面生成：CLI + 渲染编排。

- 纯决策逻辑（排序/折叠/配色/统计/净化）在 page_logic.py，可单测；
- 前端资产（样式/脚本/卡片模板）住 frontend/，由资产管线复制到 output/static/，
  Python 不内嵌任何 JS/CSS；
- 页面骨架（frontend/index.html）的令牌渲染集中在 _apply_tokens()，契约单点可见。
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta

from jinja2 import Environment, BaseLoader, select_autoescape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import daily_store
from page_logic import (
    TRACK_LABELS,
    build_arxiv_url,
    build_category_tags,
    category_stats,
    coerce_score,
    fold_display_class,
    paper_stats,
    paper_track,
    render_category_stats_html,
    sanitize_arxiv_id,
    sanitize_date,
    sanitize_url,
    score_color,
    sort_papers,
    split_papers_by_track,
    track_badge,
    truncate_authors,
)

TEMPLATE_ENV = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(default=True, default_for_string=True),
)

# 骨架模板的静态资产与卡片模板清单（frontend/ → output/static/）
STATIC_ASSET_FILES = [
    'styles.css', 'tailwind.config.js', 'app.js', 'index.html',
    'collapse.css', 'collapse.js', 'calendar.js',
]
CARD_TEMPLATE_FILES = ['normal_paper_template.html', 'selected_paper_template.html']
PAPERS_DATA_BLOCK = re.compile(
    r'<script id="papers-data" type="application/json">[\s\S]*?</script>\s*'
)


def read_frontend_file(directory, file_name):
    """读取文件内容

    Args:
        directory: 文件所在目录
        file_name: 文件名

    Returns:
        str: 文件内容
    """
    file_path = os.path.join(directory, file_name)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取文件 {file_name} 失败: {e}")
        return ''


def generate_date_options(current_date):
    """生成日期选择器的选项HTML

    Args:
        current_date: 当前日期

    Returns:
        str: 日期选项HTML
    """
    current_date = sanitize_date(current_date)
    options = []
    # 生成最近7天的日期选项
    for i in range(7):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime('%Y%m%d')
        display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        selected = ' selected' if date_str == current_date else ''
        options.append(f'<option value="{date_str}"{selected}> {display_date} </option>')
    return ''.join(options)


def render_template(template_content, context):
    """使用Jinja2渲染模板，支持条件逻辑、循环等功能"""
    template = TEMPLATE_ENV.from_string(template_content)
    return template.render(**context)


def generate_papers_html(papers, frontend_dir, static_dir=None):
    """生成论文列表的HTML（后端渲染）

    Args:
        papers: 论文数据列表
        frontend_dir: 前端目录路径
        static_dir: 静态资源目录路径（可选，优先读取其中已复制的卡片模板）

    Returns:
        str: 论文列表HTML
    """
    papers_sorted = sort_papers(papers)

    # 读取卡片模板：优先 static_dir（资产管线产物），回落 frontend_dir（源）
    if static_dir:
        templates_dir = os.path.join(static_dir, 'templates')
    else:
        templates_dir = os.path.join(frontend_dir, 'templates')
    selected_template = read_frontend_file(templates_dir, 'selected_paper_template.html')
    normal_template = read_frontend_file(templates_dir, 'normal_paper_template.html')

    papers_html = []

    for paper in papers_sorted:
        score = coerce_score(paper.get('rerank_relevance_score') or paper.get('relevance_score') or 0)
        is_selected = paper.get('is_fine_ranked', False)
        template = selected_template if is_selected else normal_template

        # 分级折叠与评分配色（page_logic 纯函数）
        display_class = fold_display_class(is_selected, score)
        color = score_color(score)
        category_tags = build_category_tags(paper.get('categories'))
        authors = truncate_authors(paper.get('authors', ''))
        # 保留1位小数，避免8.7被截断成8
        score_display = f"{score:.1f}".rstrip('0').rstrip('.')
        # 优先使用非空 rerank_reasoning，否则 reasoning，均为空显示"无"
        reasoning_text = paper.get('rerank_reasoning') or paper.get('reasoning') or '无'

        safe_arxiv_id = sanitize_arxiv_id(paper.get('arxiv_id', ''))
        fallback_url = build_arxiv_url(safe_arxiv_id)
        context = {
            'URL': sanitize_url(paper.get('url'), fallback_url),
            'TRANSLATION': paper.get('translation', paper.get('title', '')),
            'TITLE': paper.get('title', ''),
            'SCORE': score_display,
            'SCORE_COLOR': color,
            'TRACK_BADGE': track_badge(paper_track(paper)),
            'ABSTRACT': paper.get('abstract', paper.get('summary', '暂无摘要')),
            'ORI_SUMMARY': paper.get('ori_summary', paper.get('abstract', paper.get('summary', '暂无摘要'))),
            'AUTHORS': authors,
            'SUMMARY': paper.get('summary', ''),
            'REASONING': reasoning_text,
            'PUB_DATE': paper.get('pub_date', ''),
            'ARXIV_ID': safe_arxiv_id,
            'CATEGORY_TAGS': category_tags,
            'DISPLAY_CLASS': display_class,
        }

        papers_html.append(render_template(template, context))

    return ''.join(papers_html)


def _copy_assets(script_dir, frontend_dir, static_dir, static_templates_dir):
    """frontend/ 为源复制静态资产与卡片模板；frontend 缺失时回退上一轮的 output/static。"""
    if os.path.exists(frontend_dir):
        static_src = frontend_dir
        templates_src = os.path.join(frontend_dir, "templates")
    else:
        fallback = os.path.join(script_dir, "output", "static")
        if not os.path.exists(fallback) or os.path.abspath(fallback) == os.path.abspath(static_dir):
            return
        static_src = fallback
        templates_src = os.path.join(fallback, "templates")

    for name in STATIC_ASSET_FILES:
        src = os.path.join(static_src, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(static_dir, name))
            print(f"已复制静态资源: {name}")
    for name in CARD_TEMPLATE_FILES:
        src = os.path.join(templates_src, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(static_templates_dir, name))
            print(f"已复制模板文件: {name}")


def _apply_tokens(template, tokens):
    """骨架模板令牌的唯一渲染点（frontend/index.html 中的 {{TOKEN}} 占位）。"""
    content = template
    for token, value in tokens.items():
        content = content.replace(token, value)
    return content


def generate_html(papers, date_str, script_dir, output_file=None):
    """生成HTML页面

    Args:
        papers: 论文数据列表
        date_str: 日期字符串，格式为YYYYMMDD
        script_dir: 脚本所在目录
        output_file: 输出文件路径，默认为None（自动生成）

    Returns:
        str: 生成的HTML文件路径
    """
    date_str = sanitize_date(date_str)
    if not date_str:
        print("日期格式无效，应为YYYYMMDD")
        return None

    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    settings = config.load()

    # 双列表：core/related 两轨各自成榜，未过粗排或 off 的论文不入榜（只计总数）
    core_list, related_list, off_count = split_papers_by_track(
        papers, settings.rough_score_threshold
    )
    core_list = sort_papers(core_list)
    related_all = sort_papers(related_list)
    related_shown = related_all[:settings.related_max_papers]

    core_total, core_selected, _ = paper_stats(core_list)
    category_stats_html = (
        render_category_stats_html(
            category_stats(core_list, settings.target_categories),
            title="核心榜单 · 来源统计",
        )
        + render_category_stats_html(
            category_stats(related_shown, settings.target_categories),
            title="沾边速览 · 来源统计",
        )
    )

    frontend_dir = os.path.join(script_dir, "frontend")

    if output_file is None:
        output_dir = os.path.join(script_dir, "output")
        output_file = os.path.join(output_dir, f"arxiv_{date_str}.html")
    else:
        output_file = os.path.abspath(output_file)
        output_dir = os.path.dirname(output_file) or os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    static_dir = os.path.join(output_dir, "static")
    static_templates_dir = os.path.join(static_dir, "templates")
    os.makedirs(static_templates_dir, exist_ok=True)

    _copy_assets(script_dir, frontend_dir, static_dir, static_templates_dir)

    # 骨架模板：优先 static_dir（上一轮产物），回落 frontend_dir（源）
    html_template = read_frontend_file(static_dir, 'index.html')
    if not html_template and os.path.exists(frontend_dir):
        html_template = read_frontend_file(frontend_dir, 'index.html')
    if not html_template:
        print("无法读取HTML模板文件")
        return None

    core_papers_html = generate_papers_html(core_list, frontend_dir, static_dir)
    related_papers_html = generate_papers_html(related_shown, frontend_dir, static_dir)
    date_options = generate_date_options(date_str)

    current_date_config_js = json.dumps({
        "ymd": date_str,
        "display": display_date,
        "year": int(date_str[:4]),
        "month": int(date_str[4:6]),
        "day": int(date_str[6:8]),
    })
    available_dates_js = json.dumps(daily_store.all_dates())
    timestamp = int(time.time())

    html_content = _apply_tokens(html_template, {
        '{{DISPLAY_DATE}}': display_date,
        '{{CORE_COUNT}}': str(core_total),
        '{{CORE_SELECTED}}': str(core_selected),
        '{{RELATED_COUNT}}': str(len(related_shown)),
        '{{RELATED_TOTAL}}': str(len(related_all)),
        '{{TOTAL_FETCHED}}': str(len(papers)),
        '{{CATEGORY_STATS_HTML}}': category_stats_html,
        '{{DATE_OPTIONS}}': date_options,
        '{{CORE_PAPERS_HTML}}': core_papers_html,
        '{{RELATED_PAPERS_HTML}}': related_papers_html,
        '{{CURRENT_DATE_CONFIG}}': current_date_config_js,
        '{{AVAILABLE_DATES}}': available_dates_js,
        '{{TIMESTAMP}}': str(timestamp),
    })

    # 移除骨架中不需要的JSON数据块
    html_content = PAPERS_DATA_BLOCK.sub('', html_content)
    # 资源引用路径：骨架内 ../frontend/ 前缀统一改写为部署相对路径
    html_content = html_content.replace('../frontend/', 'static/')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML页面已生成: {output_file}")

    # 创建默认首页（index.html），重定向到当天页面
    index_file = os.path.join(output_dir, "index.html")
    index_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>arXiv 每日论文精选 - 重定向</title>
    <meta http-equiv="refresh" content="0;url=arxiv_{date_str}.html">
</head>
<body>
    <p>正在重定向到当天的论文精选页面...</p>
    <p>如果没有自动跳转，请<a href="arxiv_{date_str}.html">点击这里</a></p>
</body>
</html>
"""
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_content)
    print(f"默认首页已创建: {index_file}")

    return output_file


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='生成arXiv每日论文HTML页面')
    parser.add_argument('--date', type=str, help='指定日期（格式：YYYYMMDD），如不指定则使用最新日期')
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--all', action='store_true', help='回溯生成data目录下所有日期的HTML')
    args = parser.parse_args()

    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if args.all and args.date:
        print("--all 与 --date 不能同时使用")
        return
    if args.all and args.output:
        print("--all 不支持同时指定 --output")
        return

    if args.all:
        dates = daily_store.all_dates()
        if not dates:
            print("未找到可回溯生成的日期JSON文件，程序退出")
            sys.exit(1)
        success_count = 0
        for date_str in dates:
            try:
                papers = daily_store.load_papers(date_str)
            except (OSError, ValueError) as exc:
                print(f"日期 {date_str} 加载失败，跳过: {exc}")
                continue
            if not papers:
                print(f"日期 {date_str} 未加载到论文数据，跳过")
                continue
            if generate_html(papers, date_str, script_dir):
                success_count += 1
        print(f"批量生成完成：成功 {success_count}/{len(dates)} 个日期")
        return

    if args.date:
        date_str = sanitize_date(args.date)
        if not date_str:
            print("日期格式无效，应为YYYYMMDD")
            return
        try:
            papers = daily_store.load_papers(date_str)
        except OSError as exc:
            print(f"未找到日期为 {date_str} 的JSON文件: {exc}")
            sys.exit(1)
    else:
        latest_entry = daily_store.latest()
        if not latest_entry:
            print("无法获取JSON文件，程序退出")
            sys.exit(1)
        date_str, papers = latest_entry

    # 生成HTML页面
    generate_html(papers, date_str, script_dir, args.output)


if __name__ == "__main__":
    main()
