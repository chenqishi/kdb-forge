#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
LLM Client - 多渠道 LLM 请求客户端

移植自 stone_fish/agents/commons/llm_client.py，去掉了 function calling 和流式接口
（本模块只做文本补全），并且**不内置任何真实凭证**——凭证一律从
`config/llm_config.json` 注入，见 chat_qa_extract/config.py。

支持渠道（根据 model_name 自动路由，默认 openrouter）：
  - openrouter  : model 含 '/'，如 anthropic/claude-sonnet-4、google/gemini-2.5-flash-lite
  - openai      : model 以 'gpt-' 开头（无 '/'），且 openai apikey 已配置
  - qwen        : model 以 'qwen' 开头
  - gemini      : model 以 'gemini-' 开头（无 '/'）
  - volcengine  : model 以 'ep-'/'doubao' 开头
  - deepseek    : model 以 'deepseek' 开头（官方 https://api.deepseek.com）

备选模型：主模型请求失败或输出退化后，自动切换备选模型+备选渠道重试一次。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


# ---------------------------------------------------------------------------
# 渠道配置：api_key 默认全空，必须由 configure_providers 注入
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_FALLBACK_MODEL = "google/gemini-2.5-flash-lite"

_PROVIDER_CONFIGS: Dict[str, Dict[str, str]] = {
    "openrouter": {"api_url": "", "api_key": ""},
    "openai": {"api_url": "", "api_key": ""},
    "qwen": {"api_url": "", "api_key": ""},
    "gemini": {"api_url": "", "api_key": ""},
    "volcengine": {"api_url": "", "api_key": ""},
    "deepseek": {"api_url": "https://api.deepseek.com/v1/chat/completions", "api_key": ""},
}

_FALLBACK_MODEL: str = DEFAULT_FALLBACK_MODEL
_FALLBACK_PROVIDER: str = "openrouter"
_FORCE_USE_BACKUP: bool = False


def configure_providers(llm_config: Dict[str, Any]) -> None:
    """
    从配置字典更新渠道凭证和全局备选模型，进程启动时调用一次。

    llm_config 结构见 config/llm_config.json.example。
    """
    global _FALLBACK_MODEL, _FALLBACK_PROVIDER, _FORCE_USE_BACKUP

    for name, cfg in (llm_config.get("providers") or {}).items():
        if name in _PROVIDER_CONFIGS:
            _PROVIDER_CONFIGS[name].update(cfg)
        else:
            _PROVIDER_CONFIGS[name] = dict(cfg)

    if llm_config.get("fallback_model"):
        _FALLBACK_MODEL = llm_config["fallback_model"]
    if llm_config.get("fallback_provider"):
        _FALLBACK_PROVIDER = llm_config["fallback_provider"]
    if "force_use_backup" in llm_config:
        _FORCE_USE_BACKUP = bool(llm_config["force_use_backup"])

    configured = [n for n, c in _PROVIDER_CONFIGS.items() if c.get("api_key")]
    logging.info(
        "llm_client configure_providers: configured_providers=%s, fallback=%r@%r, force_use_backup=%s",
        configured, _FALLBACK_MODEL, _FALLBACK_PROVIDER, _FORCE_USE_BACKUP,
    )


def is_configured() -> bool:
    """是否已注入过至少一个可用渠道"""
    return any(c.get("api_url") and c.get("api_key") for c in _PROVIDER_CONFIGS.values())


# ---------------------------------------------------------------------------
# 渠道路由
# ---------------------------------------------------------------------------

def _detect_provider(model_name: str) -> str:
    m = (model_name or "").lower()
    if "/" in m:
        return "openrouter"
    if m.startswith("qwen"):
        return "qwen"
    if m.startswith("gemini-"):
        return "gemini"
    if m.startswith("ep-") or m.startswith("doubao"):
        return "volcengine"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("gpt-") and _PROVIDER_CONFIGS.get("openai", {}).get("api_key"):
        return "openai"
    return "openrouter"


# ---------------------------------------------------------------------------
# 底层 HTTP 调用
# ---------------------------------------------------------------------------

def _call_provider(provider: str, payload: Dict[str, Any],
                   timeout: int = 180) -> Tuple[Optional[Dict[str, Any]], str]:
    cfg = _PROVIDER_CONFIGS.get(provider)
    if not cfg:
        return None, f"渠道 {provider!r} 未配置"

    api_url = cfg.get("api_url", "")
    api_key = cfg.get("api_key", "")
    if not api_url:
        return None, f"渠道 {provider!r} api_url 为空"
    if not api_key:
        return None, f"渠道 {provider!r} api_key 为空"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "knowledge_database_builder",
    }
    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json(), ""
    except requests.exceptions.RequestException as e:
        return None, str(e)
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e}"


def _parse_text_response(result: Dict[str, Any]) -> Tuple[str, str]:
    if not result.get("choices"):
        return "", ""
    message = result["choices"][0].get("message") or {}
    return (message.get("content") or "").strip(), message.get("reasoning") or ""


def _finish_reason(result: Dict[str, Any]) -> str:
    try:
        return (result.get("choices") or [{}])[0].get("finish_reason") or ""
    except Exception:  # noqa: BLE001
        return ""


def _warn_if_reasoning_starved(result: Dict[str, Any], content: str,
                               model: str, max_tokens: int) -> None:
    """reasoning 模型思考没写完就被 max_tokens 截断时给出明确告警。

    deepseek-v4-pro/flash 这类模型的思考 token 计入 max_tokens，预算太小会
    `finish_reason='length'` 且 content 为空——只看 content 会误判成「模型坏了」。
    """
    if content or _finish_reason(result) != "length":
        return
    usage = (result or {}).get("usage") or {}
    reasoning = ((usage.get("completion_tokens_details") or {})
                 .get("reasoning_tokens") or 0)
    if reasoning:
        logging.warning(
            "request_llm: 模型 %r 的思考 token(%s) 已耗尽 max_tokens(%s)，正文为空。"
            "这是预算不足不是模型故障，请调大 max_tokens",
            model, reasoning, max_tokens)


# ---------------------------------------------------------------------------
# 输出退化检测（重复坍缩）
# ---------------------------------------------------------------------------

_DEGEN_GATE_LEN = 3000
_DEGEN_TAIL = 2000
_DEGEN_MIN_UNIQUE = 15
_DEGEN_UNIT_MAX = 12
_DEGEN_REPEAT_MIN = 15
_DEGEN_KGRAM = 8
_DEGEN_KGRAM_RATIO = 0.15


def _tail_has_short_period(tail: str) -> bool:
    n = len(tail)
    for unit in range(1, _DEGEN_UNIT_MAX + 1):
        if unit * _DEGEN_REPEAT_MIN > n:
            break
        seg = tail[-unit:]
        if not seg.strip():
            continue
        reps, i = 1, n - unit
        while i - unit >= 0 and tail[i - unit:i] == seg:
            reps += 1
            i -= unit
            if reps >= _DEGEN_REPEAT_MIN:
                return True
    return False


def _tail_kgram_low_diversity(tail: str) -> bool:
    k = _DEGEN_KGRAM
    total = len(tail) - k + 1
    if total < 50:
        return False
    grams = {tail[i:i + k] for i in range(total)}
    return len(grams) / total < _DEGEN_KGRAM_RATIO


def is_degenerate_output(content: str, finish_reason: str = "") -> bool:
    """输出是否重复坍缩。门控在前：finish_reason=length 或超长才检测。"""
    if not content:
        return False
    if finish_reason != "length" and len(content) < _DEGEN_GATE_LEN:
        return False
    tail = content[-_DEGEN_TAIL:]
    if len(set(tail)) < _DEGEN_MIN_UNIQUE:
        return True
    if _tail_has_short_period(tail):
        return True
    return _tail_kgram_low_diversity(tail)


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def request_llm(
    model_name: str,
    query: str,
    system_message: Optional[str] = None,
    max_tokens: int = 16000,
    temperature: float = 0.2,
    top_p: float = 1.0,
    provider: Optional[str] = None,
    fallback_model: Optional[str] = None,
    fallback_provider: Optional[str] = None,
    timeout: int = 180,
    usage_out: Optional[dict] = None,
) -> Tuple[str, str]:
    """
    发送一次文本补全请求，自动路由渠道，主模型失败/退化时切备选重试一次。

    Returns:
        (content, detail_info)；两次都失败时 content 为空字符串
    """
    model_name = model_name or DEFAULT_MODEL

    msgs: List[Dict[str, Any]] = []
    if system_message:
        msgs.append({"role": "system", "content": system_message})
    msgs.append({"role": "user", "content": query})

    primary_provider = provider or _detect_provider(model_name)
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }

    fb_model = fallback_model or _FALLBACK_MODEL
    fb_provider = fallback_provider or (
        _FALLBACK_PROVIDER if not fallback_model else _detect_provider(fallback_model))

    detail_info = ""

    if not _FORCE_USE_BACKUP:
        result, err = _call_provider(primary_provider, payload, timeout=timeout)
        if result is not None:
            content, _ = _parse_text_response(result)
            _warn_if_reasoning_starved(result, content, model_name, max_tokens)
            if is_degenerate_output(content, _finish_reason(result)):
                logging.warning(
                    "request_llm: 主模型 %r 输出退化(len=%d, finish=%r)，切备选重试",
                    model_name, len(content), _finish_reason(result))
                detail_info += f"attempt:0 {primary_provider} degenerate len={len(content)}\n"
            else:
                _fill_usage(usage_out, result, model_name, primary_provider)
                return content, detail_info
        else:
            detail_info += f"attempt:0 {primary_provider} error:{err}\n"
            logging.warning("request_llm 主模型失败: model=%r, error=%s", model_name, err)

    time.sleep(1)
    payload["model"] = fb_model
    result, err = _call_provider(fb_provider, payload, timeout=timeout)
    if result is not None:
        content, _ = _parse_text_response(result)
        _warn_if_reasoning_starved(result, content, fb_model, max_tokens)
        if is_degenerate_output(content, _finish_reason(result)):
            logging.error("request_llm: 主备模型均输出退化，按失败处理 (primary=%r, fallback=%r)",
                          model_name, fb_model)
            return "", detail_info + f"attempt:1(fallback) {fb_provider} degenerate\n"
        _fill_usage(usage_out, result, fb_model, fb_provider)
        return content, detail_info

    detail_info += f"attempt:1(fallback) {fb_provider} error:{err}\n"
    logging.error("request_llm 主备模型均失败: primary=%r@%s, fallback=%r@%s | %s",
                  model_name, primary_provider, fb_model, fb_provider, detail_info[:400])
    return "", detail_info


def _fill_usage(usage_out: Optional[dict], result: Optional[dict],
                model: str, provider: str) -> None:
    """把单次调用的 token 用量写进调用方传入的 dict（成本统计用，非侵入）"""
    if not isinstance(usage_out, dict):
        return
    u = (result or {}).get("usage") or {}
    pt = int(u.get("prompt_tokens") or 0)
    ct = int(u.get("completion_tokens") or 0)
    usage_out["model"] = model
    usage_out["provider"] = provider
    usage_out["prompt_tokens"] = usage_out.get("prompt_tokens", 0) + pt
    usage_out["completion_tokens"] = usage_out.get("completion_tokens", 0) + ct
    usage_out["total_tokens"] = usage_out.get("total_tokens", 0) + int(u.get("total_tokens") or (pt + ct))
    usage_out["calls"] = usage_out.get("calls", 0) + 1
