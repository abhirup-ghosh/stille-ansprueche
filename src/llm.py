"""Single OpenAI wrapper: cost tracking + disk cache. All LLM calls go through this module."""
import atexit
import hashlib
import json
from pathlib import Path
from typing import Any, Type

from openai import OpenAI
from pydantic import BaseModel

from src import config

CACHE_DIR = config.LLM_CACHE_DIR
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# USD per 1M tokens
COST_TABLE = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

TOTAL_COST_USD = 0.0

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _cache_key(model: str, temperature: float, messages: list[dict]) -> str:
    raw = json.dumps({"model": model, "temperature": temperature, "messages": messages}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = COST_TABLE.get(model, {"input": 0.0, "output": 0.0})
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000


class LLMClient:
    def chat(
        self,
        messages: list[dict],
        model: str = config.LLM_MODEL,
        temperature: float = 0.0,
        response_model: Type[BaseModel] | None = None,
    ) -> tuple[Any, dict]:
        global TOTAL_COST_USD

        key = _cache_key(model, temperature, messages)
        cache_file = _cache_path(key)
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            usage = {"prompt_tokens": cached["prompt_tokens"], "completion_tokens": cached["completion_tokens"], "cost_usd": 0.0}
            if response_model is not None:
                parsed = response_model.model_validate_json(cached["content"])
                return parsed, usage
            return cached["content"], usage

        client = _get_client()

        if response_model is not None:
            try:
                completion = client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_model,
                )
                parsed = completion.choices[0].message.parsed
                content_str = completion.choices[0].message.content
            except AttributeError:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                content_str = completion.choices[0].message.content
                parsed = response_model.model_validate_json(content_str)
        else:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            content_str = completion.choices[0].message.content
            parsed = content_str

        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
        cost = _cost_usd(model, prompt_tokens, completion_tokens)
        TOTAL_COST_USD += cost

        cache_file.write_text(json.dumps({
            "content": content_str,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }))

        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost_usd": cost}
        return parsed, usage


@atexit.register
def _print_total_cost():
    print(f"[llm.py] Total OpenAI cost this run: ${TOTAL_COST_USD:.6f}")
