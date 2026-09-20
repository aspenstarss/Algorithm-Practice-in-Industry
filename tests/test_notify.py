"""notify 的发送失败语义与卡片构建测试（monkeypatch requests，无网络）。"""
import json
import types

import pytest
import requests

from paperBotV2 import notify


def _resp(ok=True, payload=None, text="{}"):
    r = types.SimpleNamespace()
    r.ok = ok
    r.status_code = 200 if ok else 500
    r.text = text

    def _json():
        return payload if payload is not None else json.loads(text)

    r.json = _json
    return r


def _patch_post(monkeypatch, results):
    """results 为逐次调用的 (ok, payload, text) 或异常实例，返回已发送的 body 列表。"""
    posted = []
    seq = list(results)

    def fake_post(url, data, headers, timeout):
        posted.append(json.loads(data) if isinstance(data, str) else data)
        item = seq.pop(0) if seq else (True, {"StatusCode": 0}, "{}")
        if isinstance(item, Exception):
            raise item
        ok, payload, text = item
        return _resp(ok=ok, payload=payload, text=text)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    return posted


def test_parse_urls_strips_and_drops_empty():
    assert notify.parse_urls(" https://a , ,https://b ,") == ["https://a", "https://b"]
    assert notify.parse_urls("") == []
    assert notify.parse_urls(None) == []


def test_send_posts_body_to_every_url(monkeypatch):
    posted = _patch_post(monkeypatch, [])
    body = notify.markdown_card("标题", "**内容**")
    notify.send(["https://a", "https://b"], body)
    assert len(posted) == 2
    assert posted[0]["msg_type"] == "interactive"
    assert json.loads(posted[0]["card"])["header"]["title"]["content"] == "标题"


def test_send_no_urls_is_noop(monkeypatch):
    posted = _patch_post(monkeypatch, [])
    notify.send([], notify.text_post("t", []))
    assert posted == []


def test_send_collects_partial_failures_then_raises(monkeypatch):
    results = [
        (True, {"StatusCode": 0}, "{}"),                      # 第一个成功
        (True, {"code": 19001, "msg": "keyword miss"}, "{}")  # 第二个业务失败
    ]
    posted = _patch_post(monkeypatch, results)
    with pytest.raises(RuntimeError) as exc_info:
        notify.send(["https://a", "https://b"], notify.text_post("t", []))
    # 失败也要发完所有 URL 再统一上抛
    assert len(posted) == 2
    assert "[2/2]" in str(exc_info.value)
    assert "19001" in str(exc_info.value)


def test_send_collects_request_exceptions(monkeypatch):
    results = [requests.ConnectionError("boom")]
    _patch_post(monkeypatch, results)
    with pytest.raises(RuntimeError, match="boom"):
        notify.send(["https://a"], notify.markdown_card("t", "c"))


def test_papers_card_structure_and_score_rendering():
    papers = [
        {"title": "T1", "url": "https://arxiv.org/abs/1", "translation": "译",
         "summary": "s", "rerank_relevance_score": 3, "categories": ["cs.IR", "cs.CL"]},
        {"title": "T2", "url": "https://arxiv.org/abs/2"},
        {"title": "T3", "url": "https://arxiv.org/abs/3", "translation": "译3",
         "categories": "cs.AI, cs.CL", "is_filtered": False},
        {"title": "T4", "url": "https://arxiv.org/abs/4", "translation": "译4",
         "categories": "cs.AI", "is_filtered": False},
    ]
    subscribed = ["cs.IR", "cs.CL", "cs.CV", "cs.GT"]
    body = notify.papers_card(papers, date="2026-09-19", subscribed_categories=subscribed)
    assert body["msg_type"] == "interactive"
    card = json.loads(body["card"])
    data = card["data"]
    assert data["template_id"] == notify.PAPERS_CARD_TEMPLATE_ID
    # 不钉模板版本:飞书侧发布新版卡片后,推送自动使用最新版
    assert "template_version_name" not in data
    assert data["template_variable"]["date"] == "2026-09-19"
    assert data["template_variable"]["list_url"] == {"url": notify.FULL_LIST_URL}
    stats_var = data["template_variable"]["stats"]
    assert stats_var.startswith("**来源统计:**")
    # 飞书只展示订阅源(按订阅顺序),非订阅源 cs.AI 不出现;全源口径计数:
    # cs.CL 被 T1/T3 命中 -> 粗排 2;两篇均未精排 -> 精排 0
    assert "cs.IR</text_tag> 粗排 1 / 精排 0" in stats_var
    assert "cs.CL</text_tag> 粗排 2 / 精排 0" in stats_var
    assert "cs.CV</text_tag> 粗排 0 / 精排 0" in stats_var  # 订阅源当天为 0 也显示
    assert "cs.GT</text_tag> 粗排 0 / 精排 0" in stats_var
    assert "cs.AI" not in stats_var
    loop = data["template_variable"]["loop"]
    assert loop[0]["paper"] == "[T1](https://arxiv.org/abs/1)"
    # 每个来源分类一枚胶囊(全部分类,与页面单篇标签同口径)
    assert loop[0]["translation"] == (
        "<text_tag color='violet'>cs.IR</text_tag>"
        " <text_tag color='violet'>cs.CL</text_tag> 译"
    )
    assert loop[1]["translation"] == "N/A"  # 无分类时不标注
    assert loop[2]["translation"] == (  # 字符串形态的分类拆成多枚胶囊
        "<text_tag color='violet'>cs.AI</text_tag>"
        " <text_tag color='violet'>cs.CL</text_tag> 译3"
    )
    assert "⭐️⭐️⭐️" in loop[0]["score"] and "3分" in loop[0]["score"]
    assert loop[1]["score"] == "N/A"


def test_text_post_structure():
    body = notify.text_post("标题", [["内容"]])
    assert body["msg_type"] == "post"
    assert body["content"]["post"]["zh_cn"]["title"] == "标题"
    assert body["content"]["post"]["zh_cn"]["content"] == [["内容"]]
