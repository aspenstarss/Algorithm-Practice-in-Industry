"""arXiv /list/{category}/new 公告页的抓取与解析：提取新论文 ID 列表。

/new 页是唯一按"公告批次"组织的数据源：submittedDate 与公告时间脱节
（无公告的周五/周六晚窗口必空；积压释放的论文 submittedDate 会沉底），
任何 submittedDate 查询都无法完整覆盖公告批次，因此以公告页为唯一
新论文来源。本模块只提取 ID，元数据仍由调用方走 arXiv API 获取。

页面结构（三节，各含一个 <h3> 标题）：
  New submissions / Cross submissions / Replacement submissions
只取 New + Cross：Replacements 是老论文的新版本，现有管道本就不含
（等价于旧 cat:{category} 查询的语义）。
"""
import re

import requests

_ID_PATTERN = re.compile(r"arXiv:(\d{4}\.\d{4,5})(?=v\d|\b)")

# 节标题前缀 -> 是否纳入抓取；顺序即输出顺序（New 在前）
_SECTIONS = (("New submissions", True), ("Cross", True), ("Replacement", False))


class ListingParseError(RuntimeError):
    """公告页结构不符（找不到 New submissions 节），通常意味着页面改版。"""


def listing_url(base_url, category):
    return f"{base_url.rstrip('/')}/{category}/new"


def fetch_listing_html(category, base_url, user_agent, timeout=(5, 30)):
    """抓取公告页 HTML；网络错误/非 2xx 抛 requests 异常，由调用方决定回退。"""
    response = requests.get(
        listing_url(base_url, category),
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def parse_new_listing_ids(html):
    """解析公告页 HTML，返回 New+Cross 节的去重 ID 列表（保序）。

    结构不符时抛 ListingParseError。
    """
    included_ids = []
    found_new_section = False
    for chunk in html.split("<h3>")[1:]:
        head = chunk.split("</h3>")[0]
        include = False
        for prefix, keep in _SECTIONS:
            if head.startswith(prefix):
                include = keep
                if prefix == "New submissions":
                    found_new_section = True
                break
        if not include:
            continue
        for match in _ID_PATTERN.finditer(chunk):
            arxiv_id = match.group(1)
            if arxiv_id not in included_ids:
                included_ids.append(arxiv_id)
    if not found_new_section:
        raise ListingParseError("公告页缺少 New submissions 节，页面结构可能已改版")
    return included_ids
