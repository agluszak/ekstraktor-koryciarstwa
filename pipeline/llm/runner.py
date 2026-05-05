from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.config import PipelineConfig
from pipeline.domain_types import Json
from pipeline.llm.adapter import LLMExtractionAdapter, candidates_from_payload
from pipeline.llm.dto import LLMExtractionCandidateSet
from pipeline.llm.postprocessing import LLMPostProcessor
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
        response_format: Mapping[str, Json],
        temperature: float,
        max_tokens: int,
    ) -> Json: ...


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
        self.postprocessor = LLMPostProcessor(config)
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

        t0 = time.perf_counter()
        document = self.scorer.run(document)
        document.execution_times["scorer"] = time.perf_counter() - t0
        return extraction_result_from_document(document)

    def _chunks_for_document(self, cleaned_text: str) -> list[str]:
        prompt_token_overhead = _estimate_token_count(_system_prompt()) + _estimate_token_count(
            _user_prompt("")
        )
        max_input_tokens = max(
            256,
            self.config.llm.context_size
            - self.config.llm.max_output_tokens
            - prompt_token_overhead
            - 256,
        )
        max_input_tokens = min(max_input_tokens, 1200)
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

    def _extract_chunk_recursive(self, chunk_text: str) -> list[LLMExtractionCandidateSet]:
        try:
            return [self._extract_chunk_once(chunk_text)]
        except ValueError:
            paragraphs = [
                paragraph.strip() for paragraph in chunk_text.splitlines() if paragraph.strip()
            ]
            if len(paragraphs) <= 1:
                raise
            midpoint = len(paragraphs) // 2
            left = "\n".join(paragraphs[:midpoint])
            right = "\n".join(paragraphs[midpoint:])
            return self._extract_chunk_recursive(left) + self._extract_chunk_recursive(right)

    def _extract_chunk_once(self, chunk_text: str) -> LLMExtractionCandidateSet:
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


def _chat_content(response: Json) -> str:
    if not isinstance(response, Mapping):
        raise ValueError("Ollama response must be an object")
    message = response.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("Ollama message must be an object")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("Ollama response content must be a non-empty string")
    return content


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
        "roli, kwoty albo innej istotnej wartości występuje w cytacie. Priorytetem "
        "jest odzyskanie jawnie opisanych głównych faktów z artykułu; jeśli cytat "
        "wprost podaje osobę, rolę i organizację albo jawny układ polityczny, lepiej "
        "wyemitować taki fakt niż go pominąć. Rozdzielaj "
        "osobno przynależność partyjną i urząd polityczny: gdy tekst mówi "
        '"posłanka partii Razem", emituj osobny fakt PARTY_MEMBERSHIP oraz osobny '
        "fakt POLITICAL_OFFICE. Rozwiązuj opisy zależne od kontekstu do możliwie "
        "konkretnych nazw zakotwiczonych w tekście: nie używaj ogólników typu "
        '"nasze województwo" ani opisowych bytów typu "fundacja dyrektora '
        'pogotowia", jeśli tekst pozwala nazwać je przez wskazaną osobę lub urząd. '
        "Canonical_name ma być krótki, konkretny i oparty na tekście artykułu. Jeśli "
        "zdanie opisuje objęcie albo utratę funkcji w konkretnej spółce lub urzędzie, "
        "preferuj APPOINTMENT albo DISMISSAL z organization/public institution jako "
        "object_key zamiast samego gołego ROLE_HELD bez obiektu. Nie zamieniaj "
        "kontekstu sterującego, np. rady nadzorczej lub urzędu miasta, w główny cel "
        "obsadzanej funkcji, jeśli cytat jasno wskazuje właściwą spółkę. Nie "
        "oznaczaj jako APPOINTMENT historycznego założenia, utworzenia, powołania do "
        "życia organizacji ani biograficznego tła, jeśli cytat nie mówi o objęciu "
        "albo utracie konkretnej funkcji przez tę osobę. Nie zamieniaj zwykłych "
        "biograficznych zdań CV typu „wcześniej pracował jako”, „ostatnio był”, "
        "„był też”, „pracował w” na nowe APPOINTMENT, jeśli tekst opisuje tylko "
        "wcześniejsze doświadczenie zawodowe. Gdy jedno zdanie zawiera główną "
        "nominację oraz opis poprzedniej pracy tej samej osoby, emituj tylko główną "
        "nominację, a nie dodatkowy APPOINTMENT dla wcześniejszego stanowiska. Nie "
        "twórz identyfikatorów globalnych, spanów znakowych, sentence_id, "
        "paragraph_id, aliasów, confidence ani metadanych wykonania."
    )


def _user_prompt(chunk_text: str) -> str:
    return (
        "Wyodrębnij encje i fakty. Używaj stabilnych lokalnych kluczy encji, np. "
        "person_1 albo org_1, a fakty odwołuj do tych kluczy. Każda encja ma tylko "
        "key, entity_type i canonical_name. Każdy fakt ma tylko fact_type, "
        "subject_key, object_key, evidence_quote oraz opcjonalne value_text. "
        "Jeśli jedna osoba ma w cytacie jednocześnie urząd i partię, zwróć dwa "
        "osobne fakty. Dla fundacji, stowarzyszeń i urzędów używaj nazw możliwie "
        "konkretnych i zakotwiczonych w cytacie, a nie samych opisów relacyjnych. "
        "Gdy artykuł opisuje układ partyjny, lokalną koalicję, kolesiostwo albo "
        "sieć wpływów w mieście lub instytucji publicznej, preferuj niepuste "
        "wydobycie osób, partii i przynajmniej jednego PERSONAL_OR_POLITICAL_TIE "
        "zamiast pustego wyniku. "
        "Jeśli cytat nie potwierdza faktu, nie emituj faktu.\n\n"
        "PRZYKŁADY OCZEKIWANEGO WYJŚCIA:\n"
        f"{_few_shot_examples()}\n\n"
        "TEKST:\n"
        f"{chunk_text}"
    )


def _few_shot_examples() -> str:
    return (
        "Przykład 1\n"
        "Tekst: Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na sprawę.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Marcelina Zawisza"}, '
        '{"key": "party_1", "entity_type": "PoliticalParty", "canonical_name": "Razem"}], '
        '"facts": ['
        '{"fact_type": "POLITICAL_OFFICE", "subject_key": "person_1", '
        '"evidence_quote": "Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na sprawę.", '
        '"value_text": "poseł"}, '
        '{"fact_type": "PARTY_MEMBERSHIP", "subject_key": "person_1", "object_key": "party_1", '
        '"evidence_quote": "Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na sprawę.", '
        '"value_text": "Razem"}'
        "]}\n\n"
        "Przykład 2\n"
        "Tekst: Jarosław Słoma od 25 lutego zajął nową funkcję zastępcy prezesa "
        "Przedsiębiorstwa Wodociągów i Kanalizacji.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Jarosław Słoma"}, '
        '{"key": "org_1", "entity_type": "Organization", '
        '"canonical_name": "Przedsiębiorstwo Wodociągów i Kanalizacji"}], '
        '"facts": ['
        '{"fact_type": "APPOINTMENT", "subject_key": "person_1", "object_key": "org_1", '
        '"evidence_quote": "Jarosław Słoma od 25 lutego zajął nową funkcję zastępcy prezesa '
        'Przedsiębiorstwa Wodociągów i Kanalizacji.", "value_text": "wiceprezes"}'
        "]}\n\n"
        "Przykład 3\n"
        "Tekst: Fundacja założona przez Karola Bielskiego otrzymała 100 tysięcy złotych "
        "z urzędu marszałkowskiego za promowanie imprezy.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "org_1", "entity_type": "Organization", '
        '"canonical_name": "Fundacja Karola Bielskiego"}, '
        '{"key": "inst_1", "entity_type": "PublicInstitution", '
        '"canonical_name": "Urząd Marszałkowski"}], '
        '"facts": ['
        '{"fact_type": "PUBLIC_CONTRACT", "subject_key": "org_1", "object_key": "inst_1", '
        '"evidence_quote": "Fundacja założona przez Karola Bielskiego otrzymała 100 tysięcy '
        'złotych z urzędu marszałkowskiego za promowanie imprezy.", '
        '"value_text": "100 tysięcy złotych"}'
        "]}\n\n"
        "Przykład 4\n"
        "Tekst: Stanowiska stracili prezes Mariusz Stec i wiceprezes Piotr Śladowski.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Mariusz Stec"}, '
        '{"key": "person_2", "entity_type": "Person", "canonical_name": "Piotr Śladowski"}, '
        '{"key": "org_1", "entity_type": "Organization", '
        '"canonical_name": "Inwestycje Miejskie"}], '
        '"facts": ['
        '{"fact_type": "DISMISSAL", "subject_key": "person_1", "object_key": "org_1", '
        '"evidence_quote": "Stanowiska stracili prezes Mariusz Stec i wiceprezes '
        'Piotr Śladowski.", '
        '"value_text": "prezes"}, '
        '{"fact_type": "DISMISSAL", "subject_key": "person_2", "object_key": "org_1", '
        '"evidence_quote": "Stanowiska stracili prezes Mariusz Stec i wiceprezes '
        'Piotr Śladowski.", '
        '"value_text": "wiceprezes"}'
        "]}\n\n"
        "Przykład 5\n"
        "Tekst: Inwestycje Miejskie powołał do życia w 2009 roku ówczesny prezydent "
        "Płocka Mirosław Milewski.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "org_1", "entity_type": "Organization", "canonical_name": "Inwestycje Miejskie"}, '
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Mirosław Milewski"}], '
        '"facts": []'
        "]}\n\n"
        "Przykład 6\n"
        "Tekst: Artur Biernat ostatnio był dyrektorem biura zakupów ogólnych PKN Orlen.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Artur Biernat"}, '
        '{"key": "org_1", "entity_type": "Organization", "canonical_name": "PKN Orlen"}], '
        '"facts": []'
        "]}\n\n"
        "Przykład 7\n"
        "Tekst: Nowym prezesem został dotychczasowy dyrektor biura zakupów ogólnych "
        "w PKN Orlen Artur Biernat.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Artur Biernat"}, '
        '{"key": "org_1", "entity_type": "Organization", '
        '"canonical_name": "Inwestycje Miejskie"}], '
        '"facts": ['
        '{"fact_type": "APPOINTMENT", "subject_key": "person_1", "object_key": "org_1", '
        '"evidence_quote": "Nowym prezesem został dotychczasowy dyrektor biura zakupów '
        'ogólnych w PKN Orlen Artur Biernat.", "value_text": "prezes"}'
        "]}\n\n"
        "Przykład 8\n"
        "Tekst: PO tworzy tam koalicję z lokalnym Forum Samorządowym, a radna mówi o "
        "lokalnych partyjnych baronach i rozdawaniu posad.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "party_1", "entity_type": "PoliticalParty", '
        '"canonical_name": "Platforma Obywatelska"}, '
        '{"key": "org_1", "entity_type": "Organization", '
        '"canonical_name": "Forum Samorządowe"}], '
        '"facts": ['
        '{"fact_type": "PERSONAL_OR_POLITICAL_TIE", "subject_key": "party_1", '
        '"object_key": "org_1", '
        '"evidence_quote": "PO tworzy tam koalicję z lokalnym Forum Samorządowym, a radna mówi o '
        'lokalnych partyjnych baronach i rozdawaniu posad.", "value_text": "koalicja lokalna"}'
        "]}\n\n"
        "Przykład 9\n"
        "Tekst: W tekście wymieniono Marcina Kopani i jego brata Bartosza Kopani. "
        "Marcin Kopania wcześniej kierował miejską spółką.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Marcin Kopania"}, '
        '{"key": "person_2", "entity_type": "Person", "canonical_name": "Bartosz Kopania"}], '
        '"facts": ['
        '{"fact_type": "PERSONAL_OR_POLITICAL_TIE", "subject_key": "person_1", '
        '"object_key": "person_2", '
        '"evidence_quote": "W tekście wymieniono Marcina Kopani i jego brata Bartosza Kopani.", '
        '"value_text": "brat"}'
        "]}\n\n"
        "Przykład 10\n"
        "Tekst: Do rady nadzorczej spółki Alfa powołano Annę Nowak, Piotra Lisa i "
        "Ewę Zielińską. Z wyjątkiem Marka Kota wszyscy kandydaci zostali powołani.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Anna Nowak"}, '
        '{"key": "person_2", "entity_type": "Person", "canonical_name": "Piotr Lis"}, '
        '{"key": "person_3", "entity_type": "Person", "canonical_name": "Ewa Zielińska"}, '
        '{"key": "person_4", "entity_type": "Person", "canonical_name": "Marek Kot"}, '
        '{"key": "org_1", "entity_type": "Organization", "canonical_name": "Spółka Alfa"}], '
        '"facts": ['
        '{"fact_type": "APPOINTMENT", "subject_key": "person_1", "object_key": "org_1", '
        '"evidence_quote": "Do rady nadzorczej spółki Alfa powołano Annę Nowak, '
        'Piotra Lisa i Ewę Zielińską.", '
        '"value_text": "rada nadzorcza"}, '
        '{"fact_type": "APPOINTMENT", "subject_key": "person_2", "object_key": "org_1", '
        '"evidence_quote": "Do rady nadzorczej spółki Alfa powołano Annę Nowak, '
        'Piotra Lisa i Ewę Zielińską.", '
        '"value_text": "rada nadzorcza"}, '
        '{"fact_type": "APPOINTMENT", "subject_key": "person_3", "object_key": "org_1", '
        '"evidence_quote": "Do rady nadzorczej spółki Alfa powołano Annę Nowak, '
        'Piotra Lisa i Ewę Zielińską.", '
        '"value_text": "rada nadzorcza"}'
        "]}\n\n"
        "Przykład 11\n"
        "Tekst: Obecnie prezesem spółki Beta jest Beata Kania, która pełni tę funkcję od 2020 r.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Beata Kania"}, '
        '{"key": "org_1", "entity_type": "Organization", "canonical_name": "Spółka Beta"}], '
        '"facts": []}\n\n'
        "Przykład 12\n"
        "Tekst: Jan Nowak chwalił wpisy Platformy Obywatelskiej na Twitterze i krytykował PiS.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "person_1", "entity_type": "Person", "canonical_name": "Jan Nowak"}, '
        '{"key": "party_1", "entity_type": "PoliticalParty", '
        '"canonical_name": "Platforma Obywatelska"}, '
        '{"key": "party_2", "entity_type": "PoliticalParty", '
        '"canonical_name": "Prawo i Sprawiedliwość"}], '
        '"facts": []}\n\n'
        "Przykład 13\n"
        "Tekst: Firma Anny Lis otrzymywała od miejskiej spółki Gamma zlecenia "
        "warte ponad 100 tys. zł.\n"
        "JSON: "
        '{"is_relevant": true, "entities": ['
        '{"key": "org_1", "entity_type": "Organization", "canonical_name": "Firma Anny Lis"}, '
        '{"key": "org_2", "entity_type": "Organization", '
        '"canonical_name": "Miejska Spółka Gamma"}], '
        '"facts": ['
        '{"fact_type": "PUBLIC_CONTRACT", "subject_key": "org_1", "object_key": "org_2", '
        '"evidence_quote": "Firma Anny Lis otrzymywała od miejskiej spółki Gamma '
        'zlecenia warte ponad 100 tys. zł.", '
        '"value_text": "ponad 100 tys. zł"}'
        "]}"
    )
