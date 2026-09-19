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


def test_category_stats_counts_rough_and_fine_by_primary_category():
    papers = [
        {"categories": ["cs.IR", "cs.CL"], "is_filtered": False, "is_fine_ranked": True},
        {"categories": ["cs.IR"], "is_filtered": False, "is_fine_ranked": False},
        {"categories": ["cs.CL"], "is_filtered": True, "is_fine_ranked": False},
        {"categories": [], "is_filtered": False, "is_fine_ranked": False},
    ]
    assert pl.category_stats(papers) == [
        {"category": "cs.IR", "rough": 2, "fine": 1},
        {"category": "other", "rough": 1, "fine": 0},
        {"category": "cs.CL", "rough": 0, "fine": 0},
    ]
    assert pl.category_stats([]) == []


def test_render_category_stats_html_line():
    stats = [
        {"category": "cs.IR", "rough": 2, "fine": 1},
        {"category": "<b>x</b>", "rough": 0, "fine": 0},
    ]
    html = pl.render_category_stats_html(stats)
    assert "来源统计" in html
    assert "cs.IR" in html and "粗排" in html and "精排" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html  # 分类文本转义
    assert pl.render_category_stats_html([]) == ""


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
