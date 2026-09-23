"""LLM 调用的唯一接入口（OpenAI 兼容协议）。

提供商由环境变量决定，**调用时读取**（非 import 时），换提供商零代码改动：
- LLM_API_KEY   优先；回落 DEEPSEEK_API_KEY（兼容既有 Secret 名）
- LLM_BASE_URL  缺省 https://api.deepseek.com/v1；智谱为 https://open.bigmodel.cn/api/paas/v4/
- LLM_MODEL     缺省 deepseek-chat；智谱可选 glm-4.5 / glm-4.5-air / glm-4-flash

两个动作：
- json_call：结构化输出（粗排/精排），强制 JSON mode，重试 ×5 后上抛
- translate：摘要翻译（英→中），重试 ×3 后上抛，降级方式由调用方决定

CI 建议：模型与端点配置为 Actions Variables（vars.LLM_MODEL / vars.LLM_BASE_URL），
key 存 Secrets（LLM_API_KEY 或沿用 DEEPSEEK_API_KEY），切换提供商全程无需改代码。
"""
import json
import os

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
JSON_CALL_ATTEMPTS = 5
TRANSLATE_ATTEMPTS = 3

# 每次 LLM 调用的 token usage（含 DeepSeek 缓存命中数），由调用方在阶段结束时
# drain 聚合（list.append 线程安全，粗排/精排的并发线程可直接记录）
_USAGE_LOG = []


def drain_usage_stats():
    """取走并清空累计的 usage 记录，返回 [{prompt_tokens, completion_tokens,
    cache_hit_tokens}, ...]；非 DeepSeek 端点缺缓存字段时记 0。"""
    stats, _USAGE_LOG[:] = list(_USAGE_LOG), []
    return stats


def _record_usage(response):
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    _USAGE_LOG.append({
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", 0) or 0,
    })

_TRANSLATE_SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "你是一位专业的翻译人员，擅长在人工智能领域内进行高质量的英文到中文翻译。"
        "请准确翻译论文摘要，保留专业术语和技术细节。"
    ),
}


def resolve_config():
    """调用时解析提供商配置。空字符串视为未设置（GitHub vars 未配置时渲染为空）。"""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    return {"api_key": api_key, "base_url": base_url, "model": model}


def _retrying(attempts):
    return retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(attempts),
        reraise=True,
    )


def _complete(messages, *, model, base_url, api_key):
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content


def json_call(prompt, *, model=None, base_url=None, api_key=None, attempts=None):
    """结构化调用：强制 JSON 输出并解析为 dict；重试耗尽后上抛异常。"""
    cfg = resolve_config()
    model = model or cfg["model"]
    base_url = base_url or cfg["base_url"]
    api_key = api_key or cfg["api_key"]
    if not api_key:
        raise RuntimeError("LLM_API_KEY / DEEPSEEK_API_KEY 均未设置")

    @_retrying(attempts or JSON_CALL_ATTEMPTS)
    def _call():
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        _record_usage(response)
        return json.loads(response.choices[0].message.content)

    return _call()


def translate(text, *, model=None, base_url=None, api_key=None, attempts=None):
    """摘要翻译（英→中，temperature=1.3）；重试耗尽后上抛异常。"""
    cfg = resolve_config()
    model = model or cfg["model"]
    base_url = base_url or cfg["base_url"]
    api_key = api_key or cfg["api_key"]
    if not api_key:
        raise RuntimeError("LLM_API_KEY / DEEPSEEK_API_KEY 均未设置")

    @_retrying(attempts or TRANSLATE_ATTEMPTS)
    def _call():
        content = _complete(
            [_TRANSLATE_SYSTEM_PROMPT, {"role": "user", "content": text}],
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        return content.strip()

    return _call()
