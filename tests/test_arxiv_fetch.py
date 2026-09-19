"""get_daily_arxiv_papers 抓取流程测试：公告页主路径、去重过滤与窗口回退。"""
from types import SimpleNamespace

import requests

from paperBotV2.arxiv_daily import arxiv, new_listing


def _atom_feed(pids):
    items = "".join(
        "<entry>"
        f"<id>http://arxiv.org/abs/{pid}</id>"
        f"<title>Title {pid}</title>"
        "<summary>abstract</summary>"
        "<author><name>Author</name></author>"
        "<published>2026-09-17T17:59:58Z</published>"
        "<category term='cs.CL'/>"
        "</entry>"
        for pid in pids
    )
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'>" + items + "</feed>"
    )
    return SimpleNamespace(
        content=xml.encode("utf-8"), headers={}, raise_for_status=lambda: None
    )


def _listing_html(ids):
    body = "".join(f'<div class="list-title">arXiv:{i}</div>' for i in ids)
    return (
        "<html><body>"
        f"<h3>New submissions (showing {len(ids)} of {len(ids)} entries)</h3>{body}"
        "</body></html>"
    )


def test_listing_path_dedupes_seen_and_fetches_fresh(monkeypatch):
    monkeypatch.setattr(
        new_listing, "fetch_listing_html",
        lambda *a, **k: _listing_html(["2609.00001", "2609.00002", "2609.00003"]),
    )
    captured = {}

    def fake_request(base_urls, params):
        captured["params"] = params
        return _atom_feed(["2609.00001v1", "2609.00003v1"])

    monkeypatch.setattr(arxiv, "request_arxiv_page", fake_request)

    results, pages = arxiv.get_daily_arxiv_papers(
        "cs.CL", max_results=100, seen_ids={"2609.00002"}
    )

    # 已见的 2609.00002 不进 id_list；保序
    assert captured["params"]["id_list"] == "2609.00001,2609.00003"
    assert pages == 1
    assert set(results) == {"2609.00001v1", "2609.00003v1"}
    assert results["2609.00001v1"]["title"] == "Title 2609.00001v1"
    assert "cs.CL" in results["2609.00001v1"]["categories"]


def test_listing_path_all_seen_skips_api(monkeypatch):
    monkeypatch.setattr(
        new_listing, "fetch_listing_html",
        lambda *a, **k: _listing_html(["2609.00001", "2609.00002"]),
    )

    def fail_request(base_urls, params):
        raise AssertionError("全部已见时不应请求 arXiv API")

    monkeypatch.setattr(arxiv, "request_arxiv_page", fail_request)

    results, pages = arxiv.get_daily_arxiv_papers(
        "cs.CL", max_results=100, seen_ids={"2609.00001", "2609.00002"}
    )
    assert results == {}
    assert pages == 0


def test_listing_path_splits_id_list_into_batches(monkeypatch):
    ids = ["2609.%05d" % i for i in range(45)]
    monkeypatch.setattr(
        new_listing, "fetch_listing_html", lambda *a, **k: _listing_html(ids)
    )
    batches = []

    def fake_request(base_urls, params):
        batches.append(params["id_list"].split(","))
        return _atom_feed(params["id_list"].split(","))

    monkeypatch.setattr(arxiv, "request_arxiv_page", fake_request)
    monkeypatch.setattr(arxiv, "sleep_with_jitter", lambda *a, **k: None)

    results, pages = arxiv.get_daily_arxiv_papers("cs.CL", max_results=100)
    assert [len(b) for b in batches] == [40, 5]
    assert pages == 2
    assert len(results) == 45


def test_listing_path_respects_max_results_cap(monkeypatch):
    ids = ["2609.%05d" % i for i in range(10)]
    monkeypatch.setattr(
        new_listing, "fetch_listing_html", lambda *a, **k: _listing_html(ids)
    )
    captured = {}

    def fake_request(base_urls, params):
        captured["id_list"] = params["id_list"]
        return _atom_feed([])  # 返回空：关注的是请求侧截断

    monkeypatch.setattr(arxiv, "request_arxiv_page", fake_request)

    arxiv.get_daily_arxiv_papers("cs.CL", max_results=3)
    assert len(captured["id_list"].split(",")) == 3


def test_falls_back_to_window_query_when_listing_unavailable(monkeypatch):
    def broken_fetch(*a, **k):
        raise requests.exceptions.ConnectionError("listing page down")

    monkeypatch.setattr(new_listing, "fetch_listing_html", broken_fetch)
    captured = {}

    def fake_request(base_urls, params):
        captured["params"] = params
        return _atom_feed([])

    monkeypatch.setattr(arxiv, "request_arxiv_page", fake_request)

    results, pages = arxiv.get_daily_arxiv_papers("cs.CL", max_results=100)

    assert "search_query" in captured["params"]
    assert "submittedDate" in captured["params"]["search_query"]
    assert "cat:cs.CL" in captured["params"]["search_query"]
    assert results == {}
    assert pages == 1


def test_falls_back_when_listing_structure_changed(monkeypatch):
    monkeypatch.setattr(
        new_listing, "fetch_listing_html", lambda *a, **k: "<html>maintenance</html>"
    )
    captured = {}

    def fake_request(base_urls, params):
        captured["params"] = params
        return _atom_feed([])

    monkeypatch.setattr(arxiv, "request_arxiv_page", fake_request)

    arxiv.get_daily_arxiv_papers("cs.CL", max_results=100)
    assert "search_query" in captured["params"]
