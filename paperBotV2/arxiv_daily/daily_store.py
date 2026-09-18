"""每日数据文件的唯一存取接口。

业务日（business date）是全系统唯一的日期口径：北京时间 UTC+8。北京无夏令时，
用固定偏移以兼容 CI 的 Python 3.8（zoneinfo 需要 3.9+）。

数据文件是 data/ 目录下的 YYYYMMDD.json（arxiv_id -> paper 的原始字典），
文件名必须是严格 8 位数字日期——这是文件有效性的唯一规则。
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_DATE_FILE = re.compile(r"\d{8}\.json\Z")
_DATE_KEY = re.compile(r"\d{8}\Z")


def business_date(now=None):
    """返回当前业务日（北京时间 YYYYMMDD）。

    now 为 None 时取真实时钟；传入 naive datetime 视为北京时间。
    """
    moment = now if now is not None else datetime.now(BEIJING_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING_TZ)
    return moment.astimezone(BEIJING_TZ).strftime("%Y%m%d")


def _path(date):
    if not _DATE_KEY.fullmatch(date or ""):
        raise ValueError(f"非法日期: {date!r}（应为 YYYYMMDD）")
    return os.path.join(DATA_DIR, f"{date}.json")


def save(raw_papers, date=None):
    """写入某业务日的论文数据（arxiv_id -> paper 原始字典），返回文件路径。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _path(date or business_date())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw_papers, f, ensure_ascii=False, indent=2)
    return path


def load_raw(date):
    """读取某业务日的原始数据（arxiv_id -> paper）。文件缺失/损坏时抛异常。"""
    with open(_path(date), "r", encoding="utf-8") as f:
        return json.load(f)


def load_papers(date):
    """读取某业务日的论文列表（每篇注入 arxiv_id 字段）。文件缺失/损坏时抛异常。"""
    return [
        dict(paper_info, arxiv_id=arxiv_id)
        for arxiv_id, paper_info in load_raw(date).items()
    ]


def all_dates():
    """全部有效数据日期，升序。目录不存在时返回空列表。"""
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(name[:-5] for name in os.listdir(DATA_DIR) if _DATE_FILE.fullmatch(name))


def latest():
    """最新一天：(date, papers 列表)；目录不存在或没有数据文件时返回 None。"""
    dates = all_dates()
    if not dates:
        return None
    newest = dates[-1]
    return newest, load_papers(newest)
