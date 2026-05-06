from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import PipelineConfig
from pipeline.domain_registry import DomainRegistry, build_default_domain_registry
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityType,
    FactID,
    FactType,
    TimeScope,
)
from pipeline.extraction_context import ExtractionContext
from pipeline.fact_extractor import PolishFactExtractor
from pipeline.frames import PolishFrameExtractor
from pipeline.models import (
    ArticleDocument,
    Entity,
    EvidenceSpan,
    Fact,
    Mention,
    SentenceFragment,
)


def _fact(document: ArticleDocument, suffix: str) -> Fact:
    return Fact(
        fact_id=FactID(f"fact-{suffix}"),
        fact_type=FactType.POLITICAL_OFFICE,
        subject_entity_id=EntityID("person-1"),
        object_entity_id=None,
        value_text=suffix,
        value_normalized=suffix,
        time_scope=TimeScope.UNKNOWN,
        event_date=None,
        confidence=0.5,
        evidence=EvidenceSpan(
            text=document.sentences[0].text,
            sentence_index=0,
            paragraph_index=0,
            start_char=0,
            end_char=len(document.sentences[0].text),
        ),
    )


def _document() -> ArticleDocument:
    text = "Jan Kowalski działał w partii."
    return ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        title="",
        publication_date=None,
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=text,
                paragraph_index=0,
                sentence_index=0,
                start_char=0,
                end_char=len(text),
            )
        ],
        entities=[
            Entity(
                entity_id=EntityID("person-1"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
            )
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="jan kowalski",
                mention_type=EntityType.PERSON,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=12,
                entity_id=EntityID("person-1"),
            )
        ],
    )


@dataclass(slots=True)
class DummyFrameDomain:
    def name(self) -> str:
        return "dummy_frame"

    def run(self, document: ArticleDocument, context: ExtractionContext) -> ArticleDocument:
        document.title = f"{context.document.document_id}:framed"
        return document


class DummyDocumentFactDomain:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        assert context.entity_by_id(EntityID("person-1")) is not None
        return [_fact(document, "document")]


def test_custom_registry_domains_run_without_runner_changes() -> None:
    config = PipelineConfig.from_file("config.yaml")
    registry = DomainRegistry(
        frame_extractors=(DummyFrameDomain(),),
        document_fact_builders=(DummyDocumentFactDomain(),),
    )
    document = _document()

    framed = PolishFrameExtractor(config, registry=registry).run(document)
    extracted = PolishFactExtractor(config, registry=registry).run(framed)

    assert extracted.title == "doc:framed"
    assert [fact.value_text for fact in extracted.facts] == ["document"]


def test_default_registry_order_matches_existing_domain_order() -> None:
    config = PipelineConfig.from_file("config.yaml")
    registry = build_default_domain_registry(config)

    assert [extractor.name() for extractor in registry.frame_extractors] == [
        "polish_governance_frame_extractor",
        "polish_compensation_frame_extractor",
        "polish_funding_frame_extractor",
        "polish_public_contract_frame_extractor",
        "polish_public_employment_frame_extractor",
        "polish_anti_corruption_referral_frame_extractor",
        "polish_anti_corruption_abuse_frame_extractor",
    ]
    assert [type(builder).__name__ for builder in registry.document_fact_builders] == [
        "GovernanceFactBuilder",
        "CompensationFactBuilder",
        "FundingFactBuilder",
        "PublicContractFactBuilder",
        "PublicEmploymentFactBuilder",
        "AntiCorruptionReferralFactBuilder",
        "AntiCorruptionInvestigationFactBuilder",
        "PublicProcurementAbuseFactBuilder",
        "PoliticalProfileFactExtractor",
        "TieFactExtractor",
        "CrossSentencePartyFactBuilder",
        "KinshipTieBuilder",
    ]
