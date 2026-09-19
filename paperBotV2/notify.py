"""飞书群通知的唯一入口。

- send(urls, body)：唯一发送实现，收集全部失败后抛 RuntimeError
- parse_urls(raw)：FEISHU_URL 逗号串解析（全项目唯一口径）
- papers_card(papers, date)：arXiv 每日论文卡片（卡片模板版本在此单点维护）
- markdown_card(title, content)：通用 markdown 卡片（顶会日推等）
- text_post(title, content)：post 富文本消息（行业实践更新等）

失败语义：send 收集所有 URL 的失败明细后上抛。专职推送脚本（arxiv_feishu_msg）
让异常直接把任务标红；把通知当副产物的调用方（conf_daily/maintain）自行捕获降级。
"""
import json

import requests

PAPERS_CARD_TEMPLATE_ID = "AAqTHKealEdKC"
FULL_LIST_URL = "https://www.aspenstars.cn/Algorithm-Practice-in-Industry/arxiv_daily/"
_TIMEOUT_SECONDS = 10


def parse_urls(raw):
    """解析逗号分隔的飞书 webhook 串，去除空白与空项。"""
    return [url.strip() for url in (raw or "").split(",") if url.strip()]


def send(urls, body, timeout=_TIMEOUT_SECONDS):
    """向多个 webhook 发送同一消息体；收集全部失败后抛 RuntimeError。"""
    urls = [u for u in urls if u and str(u).strip()]
    if not urls:
        return

    data = body if isinstance(body, str) else json.dumps(body)
    headers = {"Content-Type": "application/json"}
    failures = []

    for idx, url in enumerate(urls, start=1):
        label = f"[{idx}/{len(urls)}]"
        try:
            ret = requests.post(url=url, data=data, headers=headers, timeout=timeout)
            response_body = ret.text[:500]
            if not ret.ok:
                failures.append(f"{label} HTTP失败: {ret.status_code}; body={response_body}")
                continue
            try:
                ret_data = ret.json()
            except ValueError as e:
                failures.append(
                    f"{label} 响应不是有效JSON: {e}; HTTP {ret.status_code}; body={response_body}"
                )
                continue
            status_code = ret_data.get("StatusCode", ret_data.get("code"))
            if status_code != 0:
                status_msg = ret_data.get("StatusMessage", ret_data.get("msg", ""))
                failures.append(
                    f"{label} 业务失败: code={status_code}, msg={status_msg}; body={response_body}"
                )
        except requests.RequestException as e:
            failures.append(f"{label} 请求失败: {e}")

    if failures:
        raise RuntimeError("飞书推送存在失败:\n" + "\n".join(failures))


def papers_card(papers, date=None):
    """arXiv 每日论文卡片。date 为展示用日期串（YYYY-MM-DD）。"""
    card_data = {
        "type": "template",
        "data": {
            "template_id": PAPERS_CARD_TEMPLATE_ID,
            "template_variable": {
                "loop": [],
                "date": date,
                # Url 类型变量要求多端链接对象,不能传纯字符串
                "list_url": {"url": FULL_LIST_URL},
            },
        },
    }
    for paper in papers:
        title = paper["title"]
        translation = paper.get("translation", "N/A")
        score = paper.get("rerank_relevance_score", "N/A")
        summary = paper.get("summary", "N/A")
        url = paper["url"]

        paper_text = f"[{title}]({url})"
        score_text = (
            "⭐️" * score + f" <text_tag color='blue'>{score}分</text_tag>"
            if isinstance(score, int)
            else "N/A"
        )
        card_data["data"]["template_variable"]["loop"].append({
            "paper": paper_text,
            "translation": translation,
            "score": score_text,
            "summary": summary,
        })
    return {"msg_type": "interactive", "card": json.dumps(card_data)}


def markdown_card(title, content):
    """通用 markdown 卡片（绿色标题 + markdown 正文）。"""
    card_data = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [{"tag": "markdown", "content": content}],
    }
    return {"msg_type": "interactive", "card": json.dumps(card_data)}


def text_post(title, content):
    """post 富文本消息（content 为飞书 post 的 zh_cn.content 结构）。"""
    return {
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": title, "content": content}}},
    }
