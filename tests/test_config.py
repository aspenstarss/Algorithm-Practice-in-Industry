"""config.load 的默认值、覆盖与容错测试。"""
import pytest

from paperBotV2.arxiv_daily import config


def test_defaults_match_ci_behavior():
    s = config.load(env={})
    assert s.target_categories == ["cs.IR", "cs.CL", "cs.CV", "cs.GT"]
    assert s.max_papers == 100
    assert s.rough_score_threshold == 4
    assert s.fine_rank_papers == 20
    assert s.related_fill_max == 0
    assert s.return_papers == 20
    assert s.lookback_hours == 36
    assert s.max_pages == 20
    assert s.request_interval == 60
    assert s.category_interval == 120
    assert s.retry_attempts == 4
    assert s.use_daily_cache is True
    assert s.category_max_pages == {"cs.IR": 8, "cs.CL": 8, "cs.CV": 5, "cs.GT": 3}
    assert s.api_base_urls == config.DEFAULT_API_BASE_URLS
    assert s.dedup_days == 7
    assert s.listing_base_url == config.DEFAULT_LISTING_BASE_URL


def test_env_overrides_win():
    s = config.load(env={
        "TARGET_CATEGORYS": "cs.IR",
        "MAX_PAPERS": "50",
        "ROUGH_SCORE_THRESHOLD": "6",
        "FINE_RANK_PAPERS": "30",
        "RETURN_PAPERS": "10",
        "ARXIV_CATEGORY_MAX_PAGES": "cs.IR:3",
        "ARXIV_USE_DAILY_CACHE": "false",
        "ARXIV_LOOKBACK_HOURS": "48",
    })
    assert s.target_categories == ["cs.IR"]
    assert s.max_papers == 50
    assert s.rough_score_threshold == 6
    assert s.fine_rank_papers == 30
    assert s.return_papers == 10
    assert s.lookback_hours == 48
    assert s.category_max_pages == {"cs.IR": 3}
    assert s.use_daily_cache is False


def test_dedup_and_listing_overrides():
    s = config.load(env={
        "ARXIV_DEDUP_DAYS": "3",
        "ARXIV_LISTING_BASE_URL": "https://mirror.example/list",
    })
    assert s.dedup_days == 3
    assert s.listing_base_url == "https://mirror.example/list"


def test_invalid_dedup_days_raises_with_field_name():
    with pytest.raises(ValueError, match="ARXIV_DEDUP_DAYS"):
        config.load(env={"ARXIV_DEDUP_DAYS": "abc"})


def test_empty_string_falls_back_to_default():
    s = config.load(env={"MAX_PAPERS": "", "TARGET_CATEGORYS": ""})
    assert s.max_papers == 100
    assert s.target_categories == ["cs.IR", "cs.CL", "cs.CV", "cs.GT"]


def test_invalid_int_raises_with_field_name():
    with pytest.raises(ValueError, match="MAX_PAPERS"):
        config.load(env={"MAX_PAPERS": "abc"})


def test_category_max_pages_tolerates_bad_entries():
    s = config.load(env={"ARXIV_CATEGORY_MAX_PAGES": "cs.IR:8,broken,cs.CL:x,cs.CV:5"})
    assert s.category_max_pages == {"cs.IR": 8, "cs.CV": 5}


def test_parse_category_max_pages_direct():
    assert config.parse_category_max_pages("cs.IR:8,cs.CV:5") == {"cs.IR": 8, "cs.CV": 5}
    assert config.parse_category_max_pages("no-colon") == {}


def test_settings_is_frozen():
    s = config.load(env={})
    with pytest.raises(Exception):
        s.max_papers = 1
