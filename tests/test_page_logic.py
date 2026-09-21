"""page_logic 纯决策函数测试：排序、折叠、配色、统计与安全净化。"""
import pytest

from paperBotV2.arxiv_daily import page_logic as pl


def _paper(score, fine=False, **extra):
    p = {"title": "t", "url": "https://arxiv.org/abs/1", "rerank_relevance_score": score,
         "is_fine_ranked": fine}
    p.update(extra)
    return p


def test_sort_papers_selected_first_then_score_desc():
    papers = [_paper(9), _paper(5, fine=True), _paper(8, fine=True), _paper(10)]
    sorted_papers = pl.sort_papers(papers)
    assert [p["rerank_relevance_score"] for p in sorted_papers] == [8, 5, 10, 9]
    assert [p["is_fine_ranked"] for p in sorted_papers] == [True, True, False, False]


def test_fold_display_class_levels():
    assert pl.fold_display_class(True, 0) == "expanded"
    assert pl.fold_display_class(False, 3) == "collapsed-level-1"
    assert pl.fold_display_class(False, 1) == "collapsed-level-2"
    assert pl.fold_display_class(False, 0) == "collapsed-level-2"


def test_score_color_bands():
    assert "green" in pl.score_color(6)
    assert "blue" in pl.score_color(4)
    assert "gray" in pl.score_color(3.9)


def test_paper_stats_counts_and_avg():
    papers = [_paper(4, fine=True), _paper(6, fine=True), _paper(2)]
    total, selected, avg = pl.paper_stats(papers)
    assert (total, selected) == (3, 2)
    assert avg == "4.0"
    assert pl.paper_stats([]) == (0, 0, "0")


def test_paper_categories_handles_list_and_string():
    assert pl.paper_categories({"categories": ["cs.IR", " cs.CL "]}) == ["cs.IR", "cs.CL"]
    assert pl.paper_categories({"categories": "cs.AI, cs.CL,cs.LG"}) == [
        "cs.AI", "cs.CL", "cs.LG"
    ]
    assert pl.paper_categories({"categories": ""}) == []
    assert pl.paper_categories({}) == []
    assert pl.paper_categories({"categories": ["cs.IR", "cs.IR"]}) == ["cs.IR"]  # 去重


def test_category_stats_counts_every_hit_category():
    # 全源口径：一篇论文命中其每个分类各计一次,总和可超论文数
    papers = [
        {"categories": ["cs.IR", "cs.CL"], "is_filtered": False, "is_fine_ranked": True},
        {"categories": "cs.IR", "is_filtered": False, "is_fine_ranked": False},
        {"categories": ["cs.CL"], "is_filtered": True, "is_fine_ranked": False},
        {"categories": [], "is_filtered": False, "is_fine_ranked": False},
    ]
    assert pl.category_stats(papers, ["cs.IR", "cs.CL"]) == [
        {"category": "cs.IR", "rough": 2, "fine": 1},
        {"category": "cs.CL", "rough": 1, "fine": 1},
    ]
    assert pl.category_stats([], ["cs.IR"]) == [
        {"category": "cs.IR", "rough": 0, "fine": 0}
    ]


def test_category_stats_subscribed_first_and_extra_threshold():
    papers = [
        # cs.AI 两篇过粗排 -> 达到门槛成列;cs.LG 一篇 -> 不出现
        {"categories": ["cs.AI"], "is_filtered": False, "is_fine_ranked": False},
        {"categories": ["cs.AI", "cs.LG"], "is_filtered": False, "is_fine_ranked": False},
        {"categories": ["cs.MM", "cs.AI"], "is_filtered": False, "is_fine_ranked": True},
        # cs.DB 粗排 0 -> 不出现(仅被过滤不算)
        {"categories": ["cs.DB"], "is_filtered": True, "is_fine_ranked": False},
    ]
    stats = pl.category_stats(papers, ["cs.IR", "cs.CL"])
    assert [item["category"] for item in stats] == ["cs.IR", "cs.CL", "cs.AI"]
    assert stats[2] == {"category": "cs.AI", "rough": 3, "fine": 1}  # 排订阅源之后
    # 订阅源按给定顺序恒在列,当天为 0 也显示
    assert stats[0] == {"category": "cs.IR", "rough": 0, "fine": 0}


def test_render_category_stats_html_table():
    stats = [
        {"category": "cs.IR", "rough": 2, "fine": 1},
        {"category": "<b>x</b>", "rough": 3, "fine": 0},
    ]
    html = pl.render_category_stats_html(stats)
    assert "来源统计" in html and "<table" in html
    assert "cs.IR" in html and "粗排" in html and "精排" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html  # 分类文本转义
    assert pl.render_category_stats_html([]) == ""  # 空数据整块隐藏


def test_sanitize_date_strict():
    assert pl.sanitize_date("20260919") == "20260919"
    assert pl.sanitize_date("2026-09-19") == ""
    assert pl.sanitize_date("<script>") == ""
    assert pl.sanitize_date(None) == ""


def test_sanitize_url_whitelist():
    ok = "https://arxiv.org/abs/2501.00001"
    assert pl.sanitize_url(ok, "https://arxiv.org") == ok
    assert pl.sanitize_url("https://evil.com/abs/1", "F") == "F"
    assert pl.sanitize_url("javascript:alert(1)", "F") == "F"
    assert pl.sanitize_url("https://user:pass@arxiv.org/abs/1", "F") == "F"
    assert pl.sanitize_url("https://arxiv.org/pdf/1", "F") == "https://arxiv.org/pdf/1"


def test_build_arxiv_url_fallback():
    assert pl.build_arxiv_url("2501.00001") == "https://arxiv.org/abs/2501.00001"
    assert pl.build_arxiv_url("../evil") == "https://arxiv.org"
    assert pl.sanitize_arxiv_id("../evil") == ""


def test_truncate_authors():
    assert pl.truncate_authors("short") == "short"
    long_name = "a" * 100
    assert pl.truncate_authors(long_name) == "a" * 80 + "..."
    assert pl.truncate_authors(None) == ""


def test_coerce_score_tolerates_garbage():
    assert pl.coerce_score("4.5") == 4.5
    assert pl.coerce_score(None) == 0.0
    assert pl.coerce_score("高") == 0.0


def test_normalize_track():
    assert pl.normalize_track("core") == "core"
    assert pl.normalize_track(" RELATED ") == "related"
    assert pl.normalize_track("OFF") == "off"
    assert pl.normalize_track("") == ""
    assert pl.normalize_track("unknown") == ""
    assert pl.normalize_track(None) == ""


def test_paper_track_new_field_and_legacy_fallback():
    # 新数据：直接采用 track 字段
    assert pl.paper_track({"track": "related"}, 4) == "related"
    assert pl.paper_track({"track": "off", "relevance_score": 9}, 4) == "off"
    # 历史数据无 track：精排标记或分数达线 -> core，否则 off
    assert pl.paper_track({"is_fine_ranked": True, "relevance_score": 1}, 4) == "core"
    assert pl.paper_track({"relevance_score": 5}, 4) == "core"
    assert pl.paper_track({"relevance_score": 3}, 4) == "off"
    assert pl.paper_track({}, 4) == "off"


def test_split_papers_by_track():
    papers = [
        {"track": "core", "is_filtered": False},
        {"track": "related", "is_filtered": False},
        {"track": "off", "is_filtered": False},
        {"track": "core", "is_filtered": True},   # 未过粗排 -> off 计数
        {"is_fine_ranked": True},                  # 历史数据回落 core
    ]
    core, related, off = pl.split_papers_by_track(papers, 4)
    assert len(core) == 2 and len(related) == 1 and off == 2


def test_track_badge():
    assert "核心" in pl.track_badge("core")
    assert "沾边" in pl.track_badge("related")
    assert pl.track_badge("off") == ""
    assert pl.track_badge("unknown") == ""


def test_render_category_stats_html_title():
    stats = [{"category": "cs.IR", "rough": 1, "fine": 0}]
    assert "核心榜单 · 来源统计" in pl.render_category_stats_html(stats, title="核心榜单 · 来源统计")
    assert "来源统计" in pl.render_category_stats_html(stats)  # 缺省标题保持兼容
