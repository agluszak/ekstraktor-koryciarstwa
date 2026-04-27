from __future__ import annotations

import argparse
import json

import pytest

from pipeline.cli import select_pipeline
from pipeline.config import (
    LLMConfig,
    ModelConfig,
    PatternConfig,
    PipelineConfig,
    RegistryConfig,
    ScoreConfig,
)
from pipeline.domain_types import EntityType, FactType, TimeScope
from pipeline.llm.adapter import LLMExtractionAdapter, candidates_from_payload
from pipeline.llm.postprocessing import LLMPostProcessor
from pipeline.llm.runner import (
    OllamaLLMExtractionPipeline,
    _configured_ollama_model,
    _system_prompt,
    _user_prompt,
)
from pipeline.llm.schema import build_llm_response_schema
from pipeline.models import (
    ArticleDocument,
    Entity,
    EvidenceSpan,
    Fact,
    PipelineInput,
    SentenceFragment,
)
from pipeline.utils import generate_entity_id, generate_fact_id


def make_config() -> PipelineConfig:
    return PipelineConfig(
        models=ModelConfig(
            spacy_model="pl_core_news_lg",
            sentence_transformer_model="sentence-transformers/test",
            stanza_coref_model_path="models/coref.pt",
        ),
        keywords=["prezes", "dotacja", "żona"],
        party_aliases={
            "Razem": "Razem",
            "PO": "Platforma Obywatelska",
            "Platforma Obywatelska": "Platforma Obywatelska",
            "PSL": "Polskie Stronnictwo Ludowe",
            "Polskie Stronnictwo Ludowe": "Polskie Stronnictwo Ludowe",
        },
        institution_aliases={},
        patterns=PatternConfig(
            appointment_verbs=[],
            dismissal_verbs=[],
            board_terms=[],
            party_markers=[],
            kinship_terms=[],
            state_company_markers=["spółka"],
            qualification_markers=[],
        ),
        score_weights=ScoreConfig(
            political_tie=0.25,
            family_tie=0.35,
            board_position=0.2,
            state_company=0.15,
            qualification_gap=0.2,
            dismissal_signal=0.1,
        ),
        registry=RegistryConfig(similarity_threshold=0.92),
        llm=LLMConfig(model="gemma4:latest", context_size=4096, max_output_tokens=512),
    )


def make_document() -> ArticleDocument:
    text = (
        "Jan Kowalski został prezesem miejskiej spółki Alfa. "
        "Jego żona Anna Kowalska dostała dotację 100 tys. zł."
    )
    return ArticleDocument(
        document_id="doc-1",
        source_url=None,
        raw_html="<html></html>",
        title="Test",
        publication_date="2026-04-27",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text="Jan Kowalski został prezesem miejskiej spółki Alfa.",
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=52,
            ),
            SentenceFragment(
                text="Jego żona Anna Kowalska dostała dotację 100 tys. zł.",
                paragraph_index=0,
                sentence_index=1,
                start_char=53,
                end_char=len(text),
            ),
        ],
    )


def make_postprocessing_document() -> ArticleDocument:
    text = (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola "
        "Bielskiego otrzymała 100 tysięcy złotych z urzędu marszałkowskiego za "
        "promowanie imprezy. "
        "Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na sprawę. "
        "Marszałkiem województwa od 25 lat jest Adam Struzik z Polskiego "
        "Stronnictwa Ludowego. "
        "Zapowiedziała też, że Razem złoży do urzędu marszałkowskiego zapytanie "
        "o wszystkie umowy."
    )
    first = (
        "Fundacja założona przez dyrektora warszawskiego pogotowia ratunkowego Karola "
        "Bielskiego otrzymała 100 tysięcy złotych z urzędu marszałkowskiego za "
        "promowanie imprezy."
    )
    second = "Marcelina Zawisza, posłanka partii Razem, zwróciła uwagę na sprawę."
    third = "Marszałkiem województwa od 25 lat jest Adam Struzik z Polskiego Stronnictwa Ludowego."
    fourth = (
        "Zapowiedziała też, że Razem złoży do urzędu marszałkowskiego zapytanie o wszystkie umowy."
    )
    second_start = len(first) + 1
    third_start = second_start + len(second) + 1
    fourth_start = third_start + len(third) + 1
    return ArticleDocument(
        document_id="doc-post",
        source_url=None,
        raw_html="<html></html>",
        title="Test",
        publication_date="2026-04-27",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=first,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(first),
            ),
            SentenceFragment(
                text=second,
                paragraph_index=0,
                sentence_index=1,
                start_char=second_start,
                end_char=second_start + len(second),
            ),
            SentenceFragment(
                text=third,
                paragraph_index=0,
                sentence_index=2,
                start_char=third_start,
                end_char=third_start + len(third),
            ),
            SentenceFragment(
                text=fourth,
                paragraph_index=0,
                sentence_index=3,
                start_char=fourth_start,
                end_char=fourth_start + len(fourth),
            ),
        ],
    )


def make_appointment_postprocessing_document() -> ArticleDocument:
    text = (
        "Jarosław Słoma od 25 lutego zajął zupełnie nową, świeżo utworzoną funkcję "
        "zastępcy prezesa Przedsiębiorstwa Wodociągów i Kanalizacji. "
        "To Jarosław Słoma - działacz PO w regionie, a po ostatnich wyborach "
        "samorządowych również radny wojewódzki."
    )
    first = (
        "Jarosław Słoma od 25 lutego zajął zupełnie nową, świeżo utworzoną funkcję "
        "zastępcy prezesa Przedsiębiorstwa Wodociągów i Kanalizacji."
    )
    second = (
        "To Jarosław Słoma - działacz PO w regionie, a po ostatnich wyborach "
        "samorządowych również radny wojewódzki."
    )
    second_start = len(first) + 1
    return ArticleDocument(
        document_id="doc-appointment",
        source_url=None,
        raw_html="<html></html>",
        title="Appointment test",
        publication_date="2026-04-27",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=first,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(first),
            ),
            SentenceFragment(
                text=second,
                paragraph_index=0,
                sentence_index=1,
                start_char=second_start,
                end_char=second_start + len(second),
            ),
        ],
    )


def test_llm_schema_excludes_hallucination_prone_fields() -> None:
    schema = build_llm_response_schema()
    serialized = json.dumps(schema)

    assert "char_start" not in serialized
    assert "char_end" not in serialized
    assert "sentence_id" not in serialized
    assert "paragraph_id" not in serialized
    assert "fact_id" not in serialized
    assert "entity_id" not in serialized
    assert "execution_times" not in serialized
    assert "relevance_score" not in serialized
    assert "relevance_reasons" not in serialized
    assert "aliases" not in serialized
    assert "mentions" not in serialized
    assert "confidence" not in serialized
    assert "relationship_type" not in serialized
    assert "kinship_detail" not in serialized
    assert "period" not in serialized
    assert '"additionalProperties": false' in serialized


def test_llm_adapter_emits_grounded_entities_and_facts() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "jan kowalski",
            },
            {
                "key": "org_1",
                "entity_type": EntityType.ORGANIZATION.value,
                "canonical_name": "Alfa",
            },
        ],
        "facts": [
            {
                "fact_type": FactType.APPOINTMENT.value,
                "subject_key": "person_1",
                "object_key": "org_1",
                "value_text": "prezes",
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            }
        ],
    }

    candidate_set = candidates_from_payload(payload)
    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.relevance is not None
    assert result.relevance.is_relevant is True
    assert result.relevance.score == 1.0
    assert [entity.canonical_name for entity in result.entities] == ["Jan Kowalski", "Alfa"]
    assert len(result.facts) == 1
    assert result.facts[0].source_extractor == "llm_ollama"
    assert result.facts[0].subject_entity_id == result.entities[0].entity_id
    assert result.facts[0].object_entity_id == result.entities[1].entity_id
    assert result.facts[0].evidence.start_char == 0
    assert result.facts[0].role == "prezes"
    assert result.facts[0].confidence == 0.8


def test_llm_adapter_drops_unknown_entity_references() -> None:
    document = make_document()
    candidate_set = candidates_from_payload(
        {
            "is_relevant": True,
            "entities": [
                {
                    "key": "person_1",
                    "entity_type": EntityType.PERSON.value,
                    "canonical_name": "Jan Kowalski",
                }
            ],
            "facts": [
                {
                    "fact_type": FactType.APPOINTMENT.value,
                    "subject_key": "person_1",
                    "object_key": "missing_org",
                    "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
                }
            ],
        }
    )

    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.facts == []


def test_llm_adapter_drops_nonexistent_evidence_quote() -> None:
    document = make_document()
    candidate_set = candidates_from_payload(
        {
            "is_relevant": True,
            "entities": [
                {
                    "key": "person_1",
                    "entity_type": EntityType.PERSON.value,
                    "canonical_name": "Jan Kowalski",
                }
            ],
            "facts": [
                {
                    "fact_type": FactType.PARTY_MEMBERSHIP.value,
                    "subject_key": "person_1",
                    "object_key": None,
                    "evidence_quote": "Tego zdania nie ma w artykule.",
                }
            ],
        }
    )

    result = LLMExtractionAdapter().apply(document, [candidate_set])

    assert result.facts == []


def test_llm_adapter_deduplicates_facts() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "Jan Kowalski",
            }
        ],
        "facts": [
            {
                "fact_type": FactType.PARTY_MEMBERSHIP.value,
                "subject_key": "person_1",
                "object_key": None,
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            },
            {
                "fact_type": FactType.PARTY_MEMBERSHIP.value,
                "subject_key": "person_1",
                "object_key": None,
                "evidence_quote": "Jan Kowalski został prezesem miejskiej spółki Alfa.",
            },
        ],
    }

    result = LLMExtractionAdapter().apply(document, [candidates_from_payload(payload)])

    assert len(result.facts) == 1


def test_candidates_from_payload_rejects_invalid_enum_without_try_except_flow() -> None:
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": "Alien",
                "canonical_name": "Jan Kowalski",
            }
        ],
        "facts": [],
    }

    with pytest.raises(ValueError, match="Unknown LLM entity type"):
        candidates_from_payload(payload)


def test_engine_rules_is_default_when_selecting_pipeline(monkeypatch) -> None:
    config = make_config()
    args = argparse.Namespace(
        engine="rules",
        llm_model=None,
        llm_host=None,
        llm_model_path=None,
        llm_context_size=None,
        llm_gpu_layers=None,
        llm_max_output_tokens=None,
        llm_chat_format=None,
        llm_temperature=None,
    )
    calls: list[PipelineConfig] = []

    def fake_build_pipeline(selected_config: PipelineConfig):
        calls.append(selected_config)
        return object()

    monkeypatch.setattr("pipeline.cli.build_pipeline", fake_build_pipeline)

    selected = select_pipeline(args, config)

    assert selected is not None
    assert calls == [config]


def test_engine_llm_builds_single_reused_runner(tmp_path) -> None:
    class FakeClient:
        def create_chat_completion(
            self,
            *,
            messages: list[dict[str, str]],
            response_format,
            temperature: float,
            max_tokens: int,
        ):
            assert messages
            assert response_format["type"] == "json_object"
            return {"message": {"content": '{"is_relevant": false, "entities": [], "facts": []}'}}

    config = make_config()
    runner = OllamaLLMExtractionPipeline(config, client_factory=lambda _: FakeClient())
    html_a = tmp_path / "a.html"
    html_b = tmp_path / "b.html"
    html_a.write_text(
        '<html><head><title>A</title><meta name="description" '
        'content="Krótki tekst artykułu o sprawach publicznych."></head></html>',
        encoding="utf-8",
    )
    html_b.write_text(
        '<html><head><title>B</title><meta name="description" '
        'content="Drugi tekst artykułu o sprawach publicznych."></head></html>',
        encoding="utf-8",
    )

    first = runner.run(PipelineInput(raw_html=html_a.read_text(encoding="utf-8"), document_id="a"))
    second = runner.run(PipelineInput(raw_html=html_b.read_text(encoding="utf-8"), document_id="b"))

    assert first.document_id == "a"
    assert second.document_id == "b"
    assert runner.client is runner.client


def test_llm_chunking_accounts_for_prompt_overhead() -> None:
    class FakeClient:
        def create_chat_completion(
            self,
            *,
            messages: list[dict[str, str]],
            response_format,
            temperature: float,
            max_tokens: int,
        ):
            return {"message": {"content": '{"is_relevant": false, "entities": [], "facts": []}'}}

    config = make_config()
    config.llm.context_size = 1200
    config.llm.max_output_tokens = 256
    runner = OllamaLLMExtractionPipeline(config, client_factory=lambda _: FakeClient())
    paragraph = " ".join(["To jest dłuższy akapit o nominacjach i spółkach publicznych."] * 12)

    chunks = runner._chunks_for_document(f"{paragraph}\n{paragraph}")

    assert len(chunks) >= 2


def test_llm_runner_recursively_splits_invalid_chunk_responses(tmp_path) -> None:
    class FakeClient:
        def create_chat_completion(
            self,
            *,
            messages: list[dict[str, str]],
            response_format,
            temperature: float,
            max_tokens: int,
        ):
            user_message = messages[-1]["content"]
            if "Akapit pierwszy." in user_message and "Akapit drugi." in user_message:
                return {"message": {"content": ""}}
            return {"message": {"content": '{"is_relevant": false, "entities": [], "facts": []}'}}

    config = make_config()
    runner = OllamaLLMExtractionPipeline(config, client_factory=lambda _: FakeClient())

    candidate_sets = runner._extract_chunk_recursive("Akapit pierwszy.\nAkapit drugi.")

    assert len(candidate_sets) == 2


def test_llm_adapter_maps_value_text_to_amount_for_public_money_fact() -> None:
    document = make_document()
    payload = {
        "is_relevant": True,
        "entities": [
            {
                "key": "person_1",
                "entity_type": EntityType.PERSON.value,
                "canonical_name": "Anna Kowalska",
            }
        ],
        "facts": [
            {
                "fact_type": FactType.COMPENSATION.value,
                "subject_key": "person_1",
                "object_key": None,
                "value_text": "100 tys. zł",
                "evidence_quote": "Jego żona Anna Kowalska dostała dotację 100 tys. zł.",
            }
        ],
    }

    result = LLMExtractionAdapter().apply(document, [candidates_from_payload(payload)])

    assert len(result.facts) == 1
    assert result.facts[0].amount_text == "100 tys. zł"
    assert result.facts[0].value_text == "100 tys. zł"
    assert result.facts[0].role is None


def test_configured_ollama_model_prefers_explicit_model() -> None:
    config = make_config()
    config.llm.model_path = "legacy-model"

    assert _configured_ollama_model(config) == "gemma4:latest"


def test_configured_ollama_model_falls_back_to_legacy_model_path() -> None:
    config = make_config()
    config.llm.model = ""
    config.llm.model_path = "legacy-model"

    assert _configured_ollama_model(config) == "legacy-model"


def test_configured_ollama_model_requires_model() -> None:
    config = make_config()
    config.llm.model = ""
    config.llm.model_path = None

    with pytest.raises(ValueError, match="llm.model"):
        _configured_ollama_model(config)


def test_llm_prompts_include_grounded_examples() -> None:
    system_prompt = _system_prompt()
    user_prompt = _user_prompt("Tekst testowy.")

    assert "Priorytetem jest odzyskanie jawnie opisanych głównych faktów" in system_prompt
    assert "preferuj APPOINTMENT albo DISMISSAL" in system_prompt
    assert "Nie oznaczaj jako APPOINTMENT historycznego założenia" in system_prompt
    assert "Nie zamieniaj zwykłych biograficznych zdań CV" in system_prompt
    assert "emituj tylko główną nominację" in system_prompt
    assert "preferuj niepuste wydobycie" in user_prompt
    assert "PRZYKŁADY OCZEKIWANEGO WYJŚCIA" in user_prompt
    assert '"fact_type": "APPOINTMENT"' in user_prompt
    assert '"fact_type": "DISMISSAL"' in user_prompt
    assert '"fact_type": "PUBLIC_CONTRACT"' in user_prompt
    assert '"fact_type": "PERSONAL_OR_POLITICAL_TIE"' in user_prompt
    assert "Mirosław Milewski" in user_prompt
    assert "Artur Biernat ostatnio był dyrektorem" in user_prompt
    assert "Nowym prezesem został dotychczasowy dyrektor" in user_prompt


def test_llm_postprocessor_grounds_entities_and_splits_party_office_facts() -> None:
    config = make_config()
    document = make_postprocessing_document()
    first = document.sentences[0]
    second = document.sentences[1]
    third = document.sentences[2]
    fourth = document.sentences[3]

    karol = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Karol Bielski"),
        entity_type=EntityType.PERSON,
        canonical_name="Karol Bielski",
        normalized_name="karol bielski",
    )
    adam = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Adam Struzik"),
        entity_type=EntityType.PERSON,
        canonical_name="Adam Struzik",
        normalized_name="adam struzik",
    )
    marcelina = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Marcelina Zawisza"),
        entity_type=EntityType.PERSON,
        canonical_name="Marcelina Zawisza",
        normalized_name="marcelina zawisza",
    )
    urzad = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Urząd Marszałkowski"),
        entity_type=EntityType.PUBLIC_INSTITUTION,
        canonical_name="Urząd Marszałkowski",
        normalized_name="urząd marszałkowski",
        evidence=[
            EvidenceSpan(
                text="urzędu marszałkowskiego",
                sentence_index=0,
                paragraph_index=0,
                start_char=first.start_char + first.text.index("urzędu marszałkowskiego"),
                end_char=first.start_char
                + first.text.index("urzędu marszałkowskiego")
                + len("urzędu marszałkowskiego"),
            )
        ],
    )
    fundacja = Entity(
        entity_id=generate_entity_id(
            "llm_entity",
            "doc-post",
            "Fundacja Dyrektora Warszawskiego Pogotowia",
        ),
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Fundacja Dyrektora Warszawskiego Pogotowia",
        normalized_name="fundacja dyrektora warszawskiego pogotowia",
    )
    razem = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Razem"),
        entity_type=EntityType.POLITICAL_PARTY,
        canonical_name="Razem",
        normalized_name="razem",
    )
    psl = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-post", "Polskie Stronnictwo Ludowe"),
        entity_type=EntityType.POLITICAL_PARTY,
        canonical_name="Polskie Stronnictwo Ludowe",
        normalized_name="polskie stronnictwo ludowe",
    )
    document.entities = [karol, adam, marcelina, urzad, fundacja, razem, psl]
    document.facts = [
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-post", "public_contract"),
            fact_type=FactType.PUBLIC_CONTRACT,
            subject_entity_id=fundacja.entity_id,
            object_entity_id=urzad.entity_id,
            value_text="100 tysięcy złotych za promowanie imprezy",
            value_normalized="100 tysięcy złotych za promowanie imprezy",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=first.text,
                sentence_index=0,
                paragraph_index=0,
                start_char=first.start_char,
                end_char=first.end_char,
            ),
            amount_text="100 tysięcy złotych za promowanie imprezy",
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-post", "office-marcelina"),
            fact_type=FactType.POLITICAL_OFFICE,
            subject_entity_id=marcelina.entity_id,
            object_entity_id=razem.entity_id,
            value_text="posłanka partii Razem",
            value_normalized="posłanka partii razem",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=second.text,
                sentence_index=1,
                paragraph_index=0,
                start_char=second.start_char,
                end_char=second.end_char,
            ),
            role="posłanka partii Razem",
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-post", "office-adam"),
            fact_type=FactType.ROLE_HELD,
            subject_entity_id=adam.entity_id,
            object_entity_id=psl.entity_id,
            value_text="Marszałek województwa od 25 lat",
            value_normalized="marszałek województwa od 25 lat",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=third.text,
                sentence_index=2,
                paragraph_index=0,
                start_char=third.start_char,
                end_char=third.end_char,
            ),
            role="Marszałek województwa od 25 lat",
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-post", "bogus-office"),
            fact_type=FactType.POLITICAL_OFFICE,
            subject_entity_id=marcelina.entity_id,
            object_entity_id=urzad.entity_id,
            value_text="złoży do urzędu marszałkowskiego zapytanie o wszystkie umowy",
            value_normalized="złoży do urzędu marszałkowskiego zapytanie o wszystkie umowy",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=fourth.text,
                sentence_index=3,
                paragraph_index=0,
                start_char=fourth.start_char,
                end_char=fourth.end_char,
            ),
            role="złoży do urzędu marszałkowskiego zapytanie o wszystkie umowy",
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
    ]

    result = LLMPostProcessor(config).apply(document)
    entity_by_name = {entity.canonical_name: entity for entity in result.entities}

    assert "Fundacja Karola Bielskiego" in entity_by_name
    assert entity_by_name["Fundacja Karola Bielskiego"].evidence

    office_facts = [fact for fact in result.facts if fact.fact_type == FactType.POLITICAL_OFFICE]
    party_facts = [fact for fact in result.facts if fact.fact_type == FactType.PARTY_MEMBERSHIP]

    assert any(
        fact.subject_entity_id == marcelina.entity_id and fact.role == "poseł"
        for fact in office_facts
    )
    assert any(
        fact.subject_entity_id == adam.entity_id and fact.role == "marszałek województwa"
        for fact in office_facts
    )
    assert any(
        fact.subject_entity_id == marcelina.entity_id and fact.value_text == "Razem"
        for fact in party_facts
    )
    assert any(
        fact.subject_entity_id == adam.entity_id and fact.value_text == "Polskie Stronnictwo Ludowe"
        for fact in party_facts
    )
    assert not any(
        fact.role == "złoży do urzędu marszałkowskiego zapytanie o wszystkie umowy"
        for fact in result.facts
    )


def test_llm_postprocessor_recovers_appointment_from_role_evidence() -> None:
    config = make_config()
    document = make_appointment_postprocessing_document()
    first = document.sentences[0]

    sloma = Entity(
        entity_id=generate_entity_id("llm_entity", "doc-appointment", "Jarosław Słoma", "Person"),
        entity_type=EntityType.PERSON,
        canonical_name="Jarosław Słoma",
        normalized_name="jarosław słoma",
        aliases=["Jarosław Słoma"],
        evidence=[],
    )
    platforma = Entity(
        entity_id=generate_entity_id(
            "llm_entity", "doc-appointment", "Platforma Obywatelska", "PoliticalParty"
        ),
        entity_type=EntityType.POLITICAL_PARTY,
        canonical_name="Platforma Obywatelska",
        normalized_name="platforma obywatelska",
        aliases=["Platforma Obywatelska"],
        evidence=[],
    )
    document.entities = [sloma, platforma]
    document.facts = [
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-appointment", "role-sloma"),
            fact_type=FactType.ROLE_HELD,
            subject_entity_id=sloma.entity_id,
            object_entity_id=None,
            value_text="prezes",
            value_normalized="prezes",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=first.text,
                sentence_index=0,
                paragraph_index=0,
                start_char=first.start_char,
                end_char=first.end_char,
            ),
            role="prezes",
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
        Fact(
            fact_id=generate_fact_id("llm_fact", "doc-appointment", "party-sloma"),
            fact_type=FactType.PARTY_MEMBERSHIP,
            subject_entity_id=sloma.entity_id,
            object_entity_id=platforma.entity_id,
            value_text="PO",
            value_normalized="po",
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=0.8,
            evidence=EvidenceSpan(
                text=document.sentences[1].text,
                sentence_index=1,
                paragraph_index=0,
                start_char=document.sentences[1].start_char,
                end_char=document.sentences[1].end_char,
            ),
            extraction_signal="schema_grounded_evidence",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_ollama",
            score_reason="llm_schema_validated",
        ),
    ]

    result = LLMPostProcessor(config).apply(document)

    appointment_facts = [fact for fact in result.facts if fact.fact_type == FactType.APPOINTMENT]
    assert any(
        fact.subject_entity_id == sloma.entity_id and fact.role == "wiceprezes"
        for fact in appointment_facts
    )
    assert not any(
        fact.fact_type == FactType.ROLE_HELD and fact.subject_entity_id == sloma.entity_id
        for fact in result.facts
    )
    assert any(
        entity.canonical_name == "Przedsiębiorstwa Wodociągów i Kanalizacji"
        and entity.entity_type == EntityType.ORGANIZATION
        and entity.evidence
        for entity in result.entities
    )
    assert any(
        fact.fact_type == FactType.PARTY_MEMBERSHIP and fact.value_text == "Platforma Obywatelska"
        for fact in result.facts
    )
