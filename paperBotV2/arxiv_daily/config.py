"""arXiv 主线的唯一配置源（paperBotV2/arxiv_daily）。

默认值即生产行为，与 CI workflow 保持一致；workflow 的 env 只注入 Secrets
与 LLM 相关 vars，抓取/排序参数不再在 yml 重复——调参改这里（走 git 评审）。

env 在 load() 调用时读取（非 import 时），非法整数抛带字段名的 ValueError。
"""
import os
from dataclasses import dataclass

DEFAULT_TARGET_CATEGORYS = ["cs.IR", "cs.CL", "cs.CV", "cs.GT"]
DEFAULT_CATEGORY_MAX_PAGES = "cs.IR:8,cs.CL:8,cs.CV:5,cs.GT:3"
DEFAULT_API_BASE_URLS = [
    "https://export.arxiv.org/api/query",
    "https://arxiv.org/api/query",
]
DEFAULT_LISTING_BASE_URL = "https://arxiv.org/list"
# 滚动去重回看天数：覆盖"周五抓过 -> 下一次公告在周一"的最长间隔（周五/周六晚无公告）
DEFAULT_DEDUP_DAYS = 7
DEFAULT_USER_AGENT = (
    "Algorithm-Practice-in-Industry paperBotV2 arxiv_daily; "
    "https://github.com/Doragd/Algorithm-Practice-in-Industry"
)


@dataclass(frozen=True)
class Settings:
    target_categories: list
    max_papers: int                  # 单类抓取论文数上限
    rough_score_threshold: int       # 粗排分数线
    fine_rank_papers: int            # 进入精排的篇数上限（按粗排分取前 N）
    return_papers: int               # 精排后返回篇数
    related_max_papers: int          # 沾边榜单页展示篇数上限（防刷屏）
    lookback_hours: int              # 抓取回看窗口
    page_size: int                   # arXiv API 单页条数
    max_pages: int                   # 分类未单列时的最大页数
    request_interval: int            # 同分类翻页间隔（秒）
    category_interval: int           # 分类之间间隔（秒）
    jitter_seconds: int              # 间隔随机抖动上限（秒）
    category_retry_attempts: int     # 分类级抓取重试次数
    use_daily_cache: bool            # 同日重跑复用当日缓存
    retry_attempts: int              # 请求级重试次数
    retry_base_wait: int             # 重试基础等待（秒）
    retry_max_wait: int              # 重试最大等待（秒）
    api_base_urls: list              # arXiv API 端点（多端点容灾）
    category_max_pages: dict         # 分类级页数上限
    listing_base_url: str            # /list/{分类}/new 公告页基地址（新论文 ID 唯一来源）
    dedup_days: int                  # 滚动去重回看天数（对比最近 N 天已入库 ID）
    user_agent: str


def parse_category_max_pages(raw_config):
    """解析分类级最大页数配置，例如 cs.IR:8,cs.CL:8,cs.CV:5；无效项容忍并提示。"""
    parsed = {}
    for item in raw_config.split(','):
        if ':' not in item:
            continue
        category, max_pages = item.split(':', 1)
        category = category.strip()
        try:
            parsed[category] = int(max_pages.strip())
        except ValueError:
            print(f"⚠️ 忽略无效的分类页数配置: {item}")
    return parsed


def load(env=None):
    """从 env 读取配置（缺省回回落内置默认值），返回只读 Settings。"""
    env = os.environ if env is None else env

    def get_str(name, default):
        raw = env.get(name)
        return raw if raw not in (None, "") else default

    def get_int(name, default):
        raw = env.get(name)
        if raw in (None, ""):
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"配置项 {name} 不是合法整数: {raw!r}") from None

    def get_bool(name, default):
        raw = env.get(name)
        if raw in (None, ""):
            return default
        return raw.lower() == "true"

    def get_list(name, default):
        raw = env.get(name)
        if raw in (None, ""):
            return list(default)
        return [url.strip() for url in raw.split(',') if url.strip()]

    return Settings(
        target_categories=[
            cat.strip() for cat in get_str(
                "TARGET_CATEGORYS", ",".join(DEFAULT_TARGET_CATEGORYS)
            ).split(',')
            if cat.strip()
        ],
        max_papers=get_int("MAX_PAPERS", 100),
        rough_score_threshold=get_int("ROUGH_SCORE_THRESHOLD", 4),
        fine_rank_papers=get_int("FINE_RANK_PAPERS", 50),
        return_papers=get_int("RETURN_PAPERS", 20),
        related_max_papers=get_int("RELATED_MAX_PAPERS", 40),
        lookback_hours=get_int("ARXIV_LOOKBACK_HOURS", 36),
        page_size=get_int("ARXIV_PAGE_SIZE", 100),
        max_pages=get_int("ARXIV_MAX_PAGES", 20),
        request_interval=get_int("ARXIV_REQUEST_INTERVAL", 60),
        category_interval=get_int("ARXIV_CATEGORY_INTERVAL", 120),
        jitter_seconds=get_int("ARXIV_JITTER_SECONDS", 120),
        category_retry_attempts=get_int("ARXIV_CATEGORY_RETRY_ATTEMPTS", 1),
        use_daily_cache=get_bool("ARXIV_USE_DAILY_CACHE", True),
        retry_attempts=get_int("ARXIV_RETRY_ATTEMPTS", 4),
        retry_base_wait=get_int("ARXIV_RETRY_BASE_WAIT", 600),
        retry_max_wait=get_int("ARXIV_RETRY_MAX_WAIT", 2400),
        api_base_urls=get_list("ARXIV_API_BASE_URLS", DEFAULT_API_BASE_URLS),
        listing_base_url=get_str("ARXIV_LISTING_BASE_URL", DEFAULT_LISTING_BASE_URL),
        dedup_days=get_int("ARXIV_DEDUP_DAYS", DEFAULT_DEDUP_DAYS),
        category_max_pages=parse_category_max_pages(
            get_str("ARXIV_CATEGORY_MAX_PAGES", DEFAULT_CATEGORY_MAX_PAGES)
        ),
        user_agent=get_str("ARXIV_USER_AGENT", DEFAULT_USER_AGENT),
    )
