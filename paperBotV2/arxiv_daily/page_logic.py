"""页面渲染的纯决策函数：排序、折叠、配色、统计与安全净化。

本模块零模板、零磁盘依赖（除标准库），是 generate_arxiv_html 的可测试内核。
"""
import re
from urllib.parse import urlparse

from markupsafe import Markup, escape

MAX_AUTHORS_DISPLAY_LENGTH = 80  # 作者名最大显示长度
ALLOWED_URL_SCHEMES = {"http", "https"}
ALLOWED_URL_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
ALLOWED_ARXIV_PATH_PREFIXES = ("/abs/", "/pdf/", "/html/")
DATE_PATTERN = re.compile(r"^\d{8}$")
ARXIV_ID_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,80}$")


def safe_text(value, default=""):
    """将任意值转换为可安全渲染的文本。"""
    if value is None:
        return default
    return str(value)


def sanitize_date(date_str):
    """仅允许YYYYMMDD格式日期，避免写入HTML/JS时混入非日期内容。"""
    date_str = safe_text(date_str)
    return date_str if DATE_PATTERN.fullmatch(date_str) else ""


def sanitize_arxiv_id(arxiv_id):
    """限制arXiv ID字符集并拒绝路径穿越片段，避免将异常内容拼入URL路径。"""
    arxiv_id = safe_text(arxiv_id).strip()
    if not arxiv_id or ".." in arxiv_id:
        return ""
    return arxiv_id if ARXIV_ID_PATTERN.fullmatch(arxiv_id) else ""


def build_arxiv_url(arxiv_id):
    """根据安全的arXiv ID构造默认论文链接。"""
    safe_arxiv_id = sanitize_arxiv_id(arxiv_id)
    if not safe_arxiv_id:
        return "https://arxiv.org"
    return f"https://arxiv.org/abs/{safe_arxiv_id}"


def sanitize_url(url, fallback_url):
    """只允许跳转到白名单内的arXiv URL。"""
    url = safe_text(url).strip()
    fallback_url = safe_text(fallback_url, "https://arxiv.org")
    if not url:
        return fallback_url

    parsed = urlparse(url)
    host = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme.lower() not in ALLOWED_URL_SCHEMES
        or host not in ALLOWED_URL_HOSTS
        or parsed.username
        or parsed.password
        or not parsed.path.startswith(ALLOWED_ARXIV_PATH_PREFIXES)
    ):
        return fallback_url

    return url


def build_category_tags(categories):
    """生成分类标签HTML，标签文本始终进行HTML转义。"""
    if isinstance(categories, list):
        category_values = categories
    elif categories:
        category_values = [cat.strip() for cat in safe_text(categories).split(',')]
    else:
        category_values = []

    tags = [
        f'<span class="category-tag">{escape(safe_text(category).strip())}</span>'
        for category in category_values
        if safe_text(category).strip()
    ]
    return Markup(''.join(tags))


def coerce_score(score):
    """将评分转换为数字，异常值按0处理。"""
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def paper_score(paper):
    """论文评分的统一取值口径：优先精排分，回落粗排分。"""
    return coerce_score(paper.get('rerank_relevance_score') or paper.get('relevance_score') or 0)


def sort_papers(papers):
    """精选论文优先，其内按评分从高到低；非精选按评分从高到低。返回新列表。"""
    return sorted(
        papers,
        key=lambda x: (
            not x.get('is_fine_ranked', False),
            -paper_score(x),
        ),
    )


def fold_display_class(is_selected, score):
    """非精选论文按分数分级折叠：score<=1 二级（默认隐藏），其余一级（只显示标题）。"""
    if is_selected:
        return "expanded"
    if coerce_score(score) <= 1:
        return "collapsed-level-2"
    return "collapsed-level-1"


def score_color(score):
    """评分颜色分档：>=6 绿、>=4 蓝、其余灰。"""
    if score >= 6:
        return 'bg-green-100 text-green-800'
    if score >= 4:
        return 'bg-blue-100 text-blue-800'
    return 'bg-gray-100 text-gray-800'


def paper_stats(papers):
    """页面统计：(总数, 精选数, 平均分字符串保留1位小数)。"""
    total = len(papers)
    selected = len([p for p in papers if p.get('is_fine_ranked', False)])
    if total > 0:
        avg = f"{sum(paper_score(p) for p in papers) / total:.1f}"
    else:
        avg = "0"
    return total, selected, avg


def primary_category(paper):
    """论文主分类：categories 首项；缺失时归入 other。"""
    categories = paper.get('categories')
    if isinstance(categories, list):
        for category in categories:
            text = safe_text(category).strip()
            if text:
                return text
    return safe_text(categories).strip() if categories else "other"


def category_stats(papers):
    """按主分类统计：rough=通过粗排数（is_filtered=False），fine=精排数。

    返回 [{category, rough, fine}]，按粗排数降序、分类名升序。
    """
    stats = {}
    for paper in papers:
        category = primary_category(paper)
        item = stats.setdefault(category, {"category": category, "rough": 0, "fine": 0})
        if not paper.get('is_filtered', False):
            item["rough"] += 1
        if paper.get('is_fine_ranked', False):
            item["fine"] += 1
    return sorted(stats.values(), key=lambda x: (-x["rough"], x["category"]))


def render_category_stats_html(stats):
    """来源统计渲染为一行富文本；无数据返回空串（整行隐藏）。分类文本经转义。"""
    if not stats:
        return ""
    segments = []
    for item in stats:
        segments.append(
            f'<span class="mr-3">'
            f'<span class="font-medium">{escape(item["category"])}</span>'
            f'<span class="text-gray-500"> 粗排 </span>'
            f'<span class="font-semibold text-primary">{item["rough"]}</span>'
            f'<span class="text-gray-500"> 精排 </span>'
            f'<span class="font-semibold text-accent">{item["fine"]}</span>'
            f'</span>'
        )
    return (
        '<span class="text-gray-500 mr-1"><i class="fa fa-pie-chart"></i> 来源统计:</span>'
        + '<span class="text-gray-300 mx-1">|</span>'.join(segments)
    )


def truncate_authors(authors, max_length=MAX_AUTHORS_DISPLAY_LENGTH):
    """作者名超长截断，追加省略号。"""
    authors = safe_text(authors)
    if len(authors) > max_length:
        return authors[:max_length] + '...'
    return authors
