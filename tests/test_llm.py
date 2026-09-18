"""llm adapter 的配置解析与调用语义测试（fake client，无网络）。"""
import json
import types

import pytest

from paperBotV2 import llm


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_resolve_defaults_to_deepseek():
    assert llm.resolve_config() == {
        "api_key": None,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    }


def test_resolve_prefers_llm_api_key_with_fallback(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fallback-key")
    assert llm.resolve_config()["api_key"] == "fallback-key"
    monkeypatch.setenv("LLM_API_KEY", "primary-key")
    assert llm.resolve_config()["api_key"] == "primary-key"


def test_empty_env_vars_fall_back(monkeypatch):
    # GitHub vars 未配置时渲染为空字符串，应视为未设置
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    cfg = llm.resolve_config()
    assert cfg["model"] == "deepseek-chat"
    assert cfg["base_url"] == "https://api.deepseek.com/v1"


def test_env_overrides_win(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "glm-4.5-air")
    monkeypatch.setenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
    cfg = llm.resolve_config()
    assert cfg["model"] == "glm-4.5-air"
    assert cfg["base_url"] == "https://open.bigmodel.cn/api/paas/v4/"


def test_json_call_missing_key_raises():
    with pytest.raises(RuntimeError):
        llm.json_call("x", attempts=1)


def _patch_openai(monkeypatch, content):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    calls = {}

    def fake_create(**kwargs):
        calls.update(kwargs)
        message = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: client)
    return calls


def test_json_call_parses_json_response(monkeypatch):
    calls = _patch_openai(monkeypatch, '{"score": 5}')
    assert llm.json_call("请输出 json", attempts=1) == {"score": 5}
    assert calls["response_format"] == {"type": "json_object"}


def test_json_call_invalid_json_raises_fast(monkeypatch):
    _patch_openai(monkeypatch, "not json")
    with pytest.raises(json.JSONDecodeError):
        llm.json_call("x", attempts=1)


def test_translate_strips_content(monkeypatch):
    _patch_openai(monkeypatch, "  翻译结果  ")
    assert llm.translate("hello", attempts=1) == "翻译结果"
