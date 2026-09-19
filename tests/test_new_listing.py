"""new_listing 公告页解析的回归测试（夹具为 2026-09-18 真实页面快照）。"""
import pathlib
import pytest

from paperBotV2.arxiv_daily import new_listing

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "arxiv_new_csCL_20260918.html"


def _synthetic_html(new_ids=(), cross_ids=(), repl_ids=()):
    def section(title, ids):
        body = "".join(f'<div class="list-title">arXiv:{i}</div>' for i in ids)
        return f"<h3>{title}</h3>\n{body}"

    return (
        "<html><body>"
        + section("New submissions (showing %d of %d entries)" % (len(new_ids), len(new_ids)), new_ids)
        + section("Cross submissions (showing %d of %d entries)" % (len(cross_ids), len(cross_ids)), cross_ids)
        + section("Replacement submissions (showing %d of %d entries)" % (len(repl_ids), len(repl_ids)), repl_ids)
        + "</body></html>"
    )


def test_parse_real_fixture_counts_and_order():
    html = FIXTURE.read_text(encoding="utf-8")
    ids = new_listing.parse_new_listing_ids(html)
    # 2026-09-18 批次：New 72 + Cross 32，两节无重叠
    assert len(ids) == 104
    assert ids[0] == "2609.19148"
    assert len(set(ids)) == 104


def test_parse_real_fixture_excludes_replacements():
    html = FIXTURE.read_text(encoding="utf-8")
    ids = set(new_listing.parse_new_listing_ids(html))
    # Replacement 节的老论文（新版本）不得进入抓取列表
    assert "2503.22727" not in ids
    assert "2609.18766" not in ids


def test_parse_keeps_cross_lists_excludes_replacements_keeps_order():
    html = _synthetic_html(
        new_ids=["2609.00002", "2609.00001"],
        cross_ids=["2609.00002", "2609.00003"],  # 跨节重复只保留首次出现
        repl_ids=["2503.22727"],
    )
    ids = new_listing.parse_new_listing_ids(html)
    assert ids == ["2609.00002", "2609.00001", "2609.00003"]


def test_parse_accepts_versioned_ids():
    html = _synthetic_html(new_ids=["2609.00001"], cross_ids=["2609.00004v2"])
    assert new_listing.parse_new_listing_ids(html) == ["2609.00001", "2609.00004"]


def test_parse_missing_new_section_raises():
    html = "<html><body><h3>Cross submissions (showing 1 of 1 entries)</h3>arXiv:2609.00001</body></html>"
    with pytest.raises(new_listing.ListingParseError):
        new_listing.parse_new_listing_ids(html)


def test_parse_empty_page_raises():
    with pytest.raises(new_listing.ListingParseError):
        new_listing.parse_new_listing_ids("<html><body>maintenance</body></html>")


def test_listing_url_joins_base():
    assert new_listing.listing_url("https://arxiv.org/list", "cs.CL") == "https://arxiv.org/list/cs.CL/new"
    assert new_listing.listing_url("https://arxiv.org/list/", "cs.IR") == "https://arxiv.org/list/cs.IR/new"
