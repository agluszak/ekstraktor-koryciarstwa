from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.config import PipelineConfig
from pipeline.llm.adapter import LLMExtractionAdapter, candidates_from_payload
from pipeline.llm.dto import LLMExtractionCandidateSet
from pipeline.llm.schema import build_llm_response_schema
from pipeline.models import ExtractionResult, PipelineInput, extraction_result_from_document
from pipeline.preprocessing import TrafilaturaPreprocessor
from pipeline.scoring import RuleBasedNepotismScorer
from pipeline.segmentation import ParagraphSentenceSegmenter


class LLMChatClient(Protocol):
    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: Mapping[str, object],
        temperature: float,
        max_tokens: int,
    ) -> object: ...


LLMClientFactory = Callable[[PipelineConfig], LLMChatClient]


class OllamaLLMExtractionPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        client_factory: LLMClientFactory | None = None,
    ) -> None:
        self.config = config
        self.preprocessor = TrafilaturaPreprocessor()
        self.segmenter = ParagraphSentenceSegmenter(config)
        self.adapter = LLMExtractionAdapter()
        self.scorer = RuleBasedNepotismScorer(config)
        self.client = (client_factory or _load_ollama_client)(config)
        self.schema = build_llm_response_schema()

    def run(self, data: PipelineInput) -> ExtractionResult:
        t0 = time.perf_counter()
        document = self.preprocessor.run(data)
        document.execution_times["preprocessor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.segmenter.run(document)
        document.execution_times["segmenter"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        chunks = self._chunks_for_document(document.cleaned_text)
        document.execution_times["llm_chunking"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        candidate_sets = [self._extract_chunk(chunk) for chunk in chunks]
        document.execution_times["llm_extractor"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.adapter.apply(document, candidate_sets)
        document.execution_times["llm_adapter"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        document = self.scorer.run(document)
        document.execution_times["scorer"] = time.perf_counter() - t0
        return extraction_result_from_document(document)

    def _chunks_for_document(self, cleaned_text: str) -> list[str]:
        max_input_tokens = max(
            256,
            self.config.llm.context_size - self.config.llm.max_output_tokens - 512,
        )
        chunks: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0
        for paragraph in cleaned_text.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            paragraph_tokens = _estimate_token_count(paragraph)
            if paragraph_tokens > max_input_tokens:
                raise ValueError("Article paragraph exceeds the configured LLM context window")
            if current_parts and current_tokens + paragraph_tokens > max_input_tokens:
                chunks.append("\n".join(current_parts))
                current_parts = []
                current_tokens = 0
            current_parts.append(paragraph)
            current_tokens += paragraph_tokens
        if current_parts:
            chunks.append("\n".join(current_parts))
        return chunks

    def _extract_chunk(self, chunk_text: str) -> LLMExtractionCandidateSet:
        response = self.client.create_chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(chunk_text)},
            ],
            response_format={"type": "json_object", "schema": self.schema},
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_output_tokens,
        )
        content = _chat_content(response)
        payload = json.loads(content)
        return candidates_from_payload(payload)


GemmaLLMExtractionPipeline = OllamaLLMExtractionPipeline


def _load_ollama_client(config: PipelineConfig) -> LLMChatClient:
    model_name = _configured_ollama_model(config)
    return _OllamaChatClient(
        base_url=config.llm.base_url,
        model_name=model_name,
        context_size=config.llm.context_size,
        request_timeout_seconds=config.llm.request_timeout_seconds,
    )


class _OllamaChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        context_size: int,
        request_timeout_seconds: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._context_size = context_size
        self._request_timeout_seconds = request_timeout_seconds

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: Mapping[str, object],
        temperature: float,
        max_tokens: int,
    ) -> object:
        schema = response_format.get("schema")
        if not isinstance(schema, Mapping):
            raise ValueError("LLM response_format.schema must be an object")
        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": False,
            "format": dict(schema),
            "options": {
                "temperature": temperature,
                "num_ctx": self._context_size,
                "num_predict": max_tokens,
            },
        }
        request = Request(
            f"{self._base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._request_timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama request failed with status {exc.code}: {body or exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Ollama is not reachable at {self._base_url}. "
                "Start the Ollama service or set llm.base_url / --llm-host."
            ) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama returned invalid JSON") from exc


def _configured_ollama_model(config: PipelineConfig) -> str:
    if config.llm.model:
        return config.llm.model
    if config.llm.model_path:
        return config.llm.model_path
    raise ValueError("--llm-model or llm.model is required when --engine llm is used")


def _chat_content(response: object) -> str:
    response = _object_mapping(response, "Ollama response")
    message = response.get("message")
    message = _object_mapping(message, "Ollama message")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("Ollama response content must be a non-empty string")
    return content


def _object_mapping(payload: object, label: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be an object")
    output: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} object keys must be strings")
        output[key] = value
    return output


def _estimate_token_count(text: str) -> int:
    utf8_bytes = len(text.encode("utf-8"))
    return max(1, utf8_bytes // 4)


def _system_prompt() -> str:
    return (
        "Jesteś ekstraktorem faktów z polskich artykułów o publicznych nominacjach, "
        "finansach publicznych, przetargach, relacjach rodzinnych i politycznych. "
        "Zwróć tylko JSON zgodny ze schematem. Każdy fakt musi mieć dokładny cytat "
        "evidence_quote skopiowany z tekstu wejściowego. Używaj tylko pól wymaganych "
        "przez schemat oraz opcjonalnego value_text wtedy, gdy dokładny krótki opis "
        "roli, kwoty albo innej istotnej wartości występuje w cytacie. Nie twórz "
        "identyfikatorów globalnych, spanów znakowych, sentence_id, paragraph_id, "
        "aliasów, confidence ani metadanych wykonania."
    )


def _user_prompt(chunk_text: str) -> str:
    return (
        "Wyodrębnij encje i fakty. Używaj stabilnych lokalnych kluczy encji, np. "
        "person_1 albo org_1, a fakty odwołuj do tych kluczy. Każda encja ma tylko "
        "key, entity_type i canonical_name. Każdy fakt ma tylko fact_type, "
        "subject_key, object_key, evidence_quote oraz opcjonalne value_text. "
        "Jeśli cytat nie potwierdza faktu, nie emituj faktu.\n\nTEKST:\n"
        f"{chunk_text}"
    )
