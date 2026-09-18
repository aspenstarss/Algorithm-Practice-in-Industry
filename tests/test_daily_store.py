"""daily_store 的接口与业务日口径测试（全部纯逻辑，无网络）。"""
from datetime import datetime, timedelta, timezone

import pytest

from paperBotV2.arxiv_daily import daily_store as store


def test_business_date_uses_beijing_midnight_boundary():
    # UTC 2026-09-19 16:30 = 北京 2026-09-20 00:30 → 业务日应翻到 20 日
    assert store.business_date(datetime(2026, 9, 19, 16, 30, tzinfo=timezone.utc)) == "20260920"
    # UTC 15:30 仍是北京 19 日
    assert store.business_date(datetime(2026, 9, 19, 15, 30, tzinfo=timezone.utc)) == "20260919"


def test_business_date_treats_naive_as_beijing():
    assert store.business_date(datetime(2026, 9, 19, 23, 0)) == "20260919"


def test_business_date_default_matches_beijing_now():
    assert store.business_date() == datetime.now(store.BEIJING_TZ).strftime("%Y%m%d")


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_save_and_load_roundtrip(store_dir):
    raw = {"2501.00001": {"title": "A", "categories": "cs.IR"}}
    path = store.save(raw, "20260919")
    assert path.endswith("20260919.json")
    assert store.load_raw("20260919") == raw
    assert store.load_papers("20260919") == [
        {"title": "A", "categories": "cs.IR", "arxiv_id": "2501.00001"}
    ]


def test_save_defaults_to_business_date(store_dir):
    path = store.save({"a": {}})
    assert store.business_date() in path


def test_all_dates_and_latest_ignore_non_data_files(store_dir):
    store.save({"a": {"title": "x"}}, "20260918")
    store.save({"b": {"title": "y"}}, "20260919")
    (store_dir / "results.json").write_text("{}", encoding="utf-8")
    (store_dir / "README.md").write_text("x", encoding="utf-8")
    (store_dir / "cache_20260918.json").write_text("{}", encoding="utf-8")
    assert store.all_dates() == ["20260918", "20260919"]
    date, papers = store.latest()
    assert date == "20260919"
    assert papers[0]["arxiv_id"] == "b"


def test_latest_none_when_no_data(store_dir):
    assert store.latest() is None
    assert store.all_dates() == []


def test_load_missing_or_invalid_date_raises(store_dir):
    with pytest.raises(FileNotFoundError):
        store.load_raw("20260101")
    with pytest.raises(ValueError):
        store.load_raw("../evil")


def test_feishu_gate_semantics_with_fake_clock(store_dir):
    """推送闸门：latest 的日期 == 业务日才推送，跨日跳过。"""
    store.save({"a": {}}, "20260918")
    date, _ = store.latest()
    same_day = datetime(2026, 9, 18, 12, 0, tzinfo=store.BEIJING_TZ)
    next_day = same_day + timedelta(days=1)
    assert date == store.business_date(same_day)
    assert date != store.business_date(next_day)
