from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.base import DocumentStage
from pipeline.config import PipelineConfig
from pipeline.domain_types import Json
from pipeline.llm.adapter import LLMExtractionAdapter, candidates_from_payload
from pipeline.llm.dto import LLMExtractionCandidateSet
from pipeline.llm.postprocessing import LLMPostProcessor
from pipeline.llm.schema import build_llm_response_schema
from pipeline.models import ArticleDocument


class LLMChatClient(Protocol):
    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Json],
        temperature: float,
        max_tokens: int,
    ) -> Json: ...


LLMClientFactory = Callable[[PipelineConfig], LLMChatClient]


class OllamaLLMEngine(DocumentStage):
    """
    Opt-in LLM extraction engine implemented as a PipelineStage.
    """

    def __init__(
        self,
        config: PipelineConfig,
        *,
        client_factory: LLMClientFactory | None = None,
    ) -> None:
        self.config = config
        self.adapter = LLMExtractionAdapter()
        self.postprocessor = LLMPostProcessor(config)
        self.client = (client_factory or _load_ollama_client)(config)
        self.schema = build_llm_response_schema()

    def name(self) -> str:
        return "ollama_llm_engine"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        t0 = time.perf_counter()
        chunks = self._chunks_for_document(document.cleaned_text)
        document.execution_times["llm_chunking"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        candidate_sets: list[LLMExtractionCandidateSet] = []
        for chunk in chunks:
            candidate_sets.extend(self._extract_chunk_recursive(chunk))
        document.execution_times["llm_extractor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.adapter.apply(document, candidate_sets)
        document.execution_times["llm_adapter"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.postprocessor.apply(document)
        document.execution_times["llm_postprocessing"] = time.perf_counter() - t0

        return document

    def _chunks_for_document(self, cleaned_text: str) -> list[str]:
        prompt_token_overhead = _estimate_token_count(_system_prompt()) + _estimate_token_count(
            _user_prompt("")
        )
        max_chunk_tokens = self.config.llm.context_size - prompt_token_overhead - 512
        if max_chunk_tokens <= 256:
            return [cleaned_text]

        paragraphs = cleaned_text.split("\n\n")
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = _estimate_token_count(para)
            if current_tokens + para_tokens > max_chunk_tokens and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0
            current_chunk.append(para)
            current_tokens += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        return chunks

    def _extract_chunk_recursive(
        self, text: str, depth: int = 0
    ) -> list[LLMExtractionCandidateSet]:
        if depth > 2:
            return []
        try:
            response = self.client.create_chat_completion(
                messages=[
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": _user_prompt(text)},
                ],
                response_format={"type": "json_object", "schema": self.schema},
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_output_tokens,
            )
            content = _chat_content(response)
            payload = json.loads(content)
            return [candidates_from_payload(payload)]
        except (ValueError, json.JSONDecodeError):
            if len(text) > 1000:
                mid = len(text) // 2
                split_idx = text.find("\n\n", mid - 200)
                if split_idx < 0:
                    split_idx = mid
                return self._extract_chunk_recursive(
                    text[:split_idx], depth + 1
                ) + self._extract_chunk_recursive(text[split_idx:], depth + 1)
            return []
        except Exception:
            return []


class _OllamaChatClient:
    def __init__(self, base_url: str, model_name: str, timeout: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Json],
        temperature: float,
        max_tokens: int,
    ) -> Json:
        schema = response_format.get("schema")
        if not isinstance(schema, Mapping):
            raise ValueError("LLM response_format.schema must be an object")
        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        req = Request(
            f"{self._base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self._timeout) as response:
                return cast(Json, json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            raise ValueError(f"Ollama API error: {exc.code} {exc.reason}") from exc
        except URLError as exc:
            raise ValueError(f"Ollama connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ollama response is not valid JSON: {exc}") from exc


def _load_ollama_client(config: PipelineConfig) -> LLMChatClient:
    return _OllamaChatClient(
        base_url=config.llm.base_url,
        model_name=config.llm.model,
        timeout=config.llm.request_timeout_seconds,
    )


def _system_prompt() -> str:
    return (
        "Jesteś ekspertem w analizie polskiego nepotyzmu i powiązań politycznych. "
        "Twoim zadaniem jest wydobycie encji i faktów z artykułu prasowego."
    )


def _user_prompt(text: str) -> str:
    return f"Przeanalizuj poniższy tekst i wyodrębnij fakty zgodnie ze schematem:\n\n{text}"


def _chat_content(response: Json) -> str:
    if not isinstance(response, dict):
        raise ValueError("Ollama response must be an object")
    response_object = cast(dict[str, Json], response)
    message = response_object.get("message")
    if not isinstance(message, dict):
        raise ValueError("Ollama message must be an object")
    message_object = cast(dict[str, Json], message)
    content = message_object.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("Ollama response content must be a non-empty string")
    return content


def _estimate_token_count(text: str) -> int:
    utf8_bytes = len(text.encode("utf-8"))
    return max(1, utf8_bytes // 4)
