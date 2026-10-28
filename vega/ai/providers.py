"""LLM providers behind one interface: OpenAI-compatible (OpenAI, OpenRouter, Ollama, custom) and Anthropic.

Internal message format:
  {"role":"user"|"assistant","content":str, "tool_calls":[{"id","name","arguments":dict}]?}
  {"role":"tool","tool_call_id":str,"name":str,"content":str}
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

import httpx

from ..secrets import get_api_key


class ProviderError(Exception):
    """Message is safe/friendly to show (and speak) to the user."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


def _http_message(r: httpx.Response) -> str:
    try:
        body = r.json()
        detail = body.get("error", body)
        detail = detail.get("message", detail) if isinstance(detail, dict) else detail
    except Exception:
        detail = r.text[:200]
    c = r.status_code
    if c in (401, 403):
        return "The AI provider rejected the API key. Open Settings > AI and check the key."
    if c == 404:
        return f"The AI provider could not find that model or endpoint. Check the model name and base URL. ({detail})"
    if c == 429:
        return "The AI provider is rate-limiting you or your quota is used up. Try again shortly."
    if c >= 500:
        return f"The AI provider had a server problem (HTTP {c}). Try again in a moment."
    return f"The AI provider returned an error (HTTP {c}): {detail}"


class BaseProvider:
    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.5,
                 transport: httpx.BaseTransport | None = None):
        if not base_url:
            raise ProviderError("No base URL is set for this AI provider. Open Settings > AI.")
        if not model:
            raise ProviderError("No model name is set. Open Settings > AI.")
        self.base_url, self.model, self.api_key, self.temperature = base_url.rstrip("/"), model, api_key, temperature
        self._client = httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0), transport=transport)

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        try:
            r = self._client.post(url, headers=headers, json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise ProviderError("I can't reach the AI service. Check your internet connection, or the base URL "
                                "(and that Ollama is running, if you use it).")
        except httpx.TimeoutException:
            raise ProviderError("The AI service took too long to respond.")
        except httpx.HTTPError as e:
            raise ProviderError(f"Network error talking to the AI service: {e}")
        if r.status_code >= 400:
            raise ProviderError(_http_message(r))
        try:
            return r.json()
        except Exception:
            raise ProviderError("The AI service returned an unreadable response.")

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        raise NotImplementedError


class OpenAICompat(BaseProvider):
    def _convert(self, system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            r = m["role"]
            if r == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif r == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in m["tool_calls"]]})
            else:
                if out[-1]["role"] == r and r in ("user", "assistant") and not out[-1].get("tool_calls"):
                    out[-1]["content"] += "\n" + m["content"]
                else:
                    out.append({"role": r, "content": m["content"]})
        return out

    def chat(self, system, messages, tools):
        payload = {"model": self.model, "messages": self._convert(system, messages),
                   "temperature": self.temperature}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = self._post(f"{self.base_url}/chat/completions", headers, payload)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError):
            raise ProviderError("The AI service sent an unexpected response.")
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc.get("id") or uuid.uuid4().hex[:12], fn.get("name", ""),
                                  args if isinstance(args, dict) else {}))
        return LLMResponse(content.strip(), calls)


class AnthropicProvider(BaseProvider):
    def _convert(self, messages: list[dict]) -> list[dict]:
        out: list[dict] = []

        def push(role, blocks):
            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": list(blocks)})

        for m in messages:
            if m["role"] == "tool":
                push("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}])
            elif m["role"] == "assistant":
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
                if blocks:
                    push("assistant", blocks)
            else:
                push("user", [{"type": "text", "text": m["content"]}])
        return out

    def chat(self, system, messages, tools):
        payload = {"model": self.model, "max_tokens": 1500, "system": system,
                   "temperature": min(1.0, self.temperature), "messages": self._convert(messages)}
        if tools:
            payload["tools"] = [{"name": t["name"], "description": t["description"],
                                 "input_schema": t["parameters"]} for t in tools]
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        data = self._post(f"{self.base_url}/messages", headers, payload)
        text, calls = [], []
        for b in data.get("content", []):
            if b.get("type") == "text":
                text.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                calls.append(ToolCall(b["id"], b["name"], b.get("input") or {}))
        return LLMResponse("".join(text).strip(), calls)


def make_provider(settings, transport=None) -> BaseProvider:
    name, cfg = settings.provider_name, settings.provider_cfg
    key = get_api_key(name)
    if cfg.get("needs_key", True) and not key:
        raise ProviderError(f"No API key is saved for {cfg.get('label', name)}. Open Settings > AI and add one.")
    cls = AnthropicProvider if cfg.get("kind") == "anthropic" else OpenAICompat
    return cls(cfg.get("base_url", ""), cfg.get("model", ""), key, float(settings.get("ai.temperature", 0.5)), transport)
