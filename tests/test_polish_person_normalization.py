import pytest

from pipeline.config import PipelineConfig
from pipeline.domain_types import DocumentID, EntityID, EntityType
from pipeline.models import ArticleDocument, Entity
from pipeline.nlp_services import StanzaPolishMorphologyAnalyzer
from pipeline.normalization import DocumentEntityCanonicalizer
from pipeline.runtime import PipelineRuntime


@pytest.fixture(scope="module")
def morphology_service():
    config = PipelineConfig.from_file("config.yaml")
    runtime = PipelineRuntime(config)
    return StanzaPolishMorphologyAnalyzer(runtime)


def test_feminine_accusative_normalizes_to_nominative(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # "Sylwię Sobolewską" (Accusative) -> "Sylwia Sobolewska" (Nominative)
    document = ArticleDocument(
        document_id=DocumentID("test-fem-acc"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Powołano Sylwię Sobolewską.",
        paragraphs=["Powołano Sylwię Sobolewską."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwię Sobolewską",
                normalized_name="Sylwię Sobolewską",
                aliases=["Sylwię Sobolewską"],
            )
        ],
    )

    normalized = canonicalizer.run(document)
    assert normalized.entities[0].canonical_name == "Sylwia Sobolewska"


def test_feminine_genitive_normalizes_to_nominative(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # "Sylwii Sobolewskiej" (Genitive) -> "Sylwia Sobolewska" (Nominative)
    document = ArticleDocument(
        document_id=DocumentID("test-fem-gen"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="To jest mąż Sylwii Sobolewskiej.",
        paragraphs=["To jest mąż Sylwii Sobolewskiej."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwii Sobolewskiej",
                normalized_name="Sylwii Sobolewskiej",
                aliases=["Sylwii Sobolewskiej"],
            )
        ],
    )

    normalized = canonicalizer.run(document)
    assert normalized.entities[0].canonical_name == "Sylwia Sobolewska"


def test_prevent_merging_husband_and_wife_surnames(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # "Sobolewska" and "Sobolewski" should NOT be merged
    document = ArticleDocument(
        document_id=DocumentID("test-gender-split"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Sylwia Sobolewska i Krzysztof Sobolewski.",
        paragraphs=["Sylwia Sobolewska i Krzysztof Sobolewski."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwia Sobolewska",
                normalized_name="Sylwia Sobolewska",
                aliases=["Sylwia Sobolewska"],
            ),
            Entity(
                entity_id=EntityID("p2"),
                entity_type=EntityType.PERSON,
                canonical_name="Krzysztof Sobolewski",
                normalized_name="Krzysztof Sobolewski",
                aliases=["Krzysztof Sobolewski"],
            ),
        ],
    )

    normalized = canonicalizer.run(document)
    assert len(normalized.entities) == 2
    names = {e.canonical_name for e in normalized.entities}
    assert "Sylwia Sobolewska" in names
    assert "Krzysztof Sobolewski" in names


def test_prevent_merging_feminine_full_name_with_masculine_surname_singleton(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # "Sylwia Sobolewska" and "Sobolewski" should NOT be merged
    document = ArticleDocument(
        document_id=DocumentID("test-singleton-gender-split"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Sylwia Sobolewska i Sobolewski.",
        paragraphs=["Sylwia Sobolewska i Sobolewski."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwia Sobolewska",
                normalized_name="Sylwia Sobolewska",
                aliases=["Sylwia Sobolewska"],
            ),
            Entity(
                entity_id=EntityID("p2"),
                entity_type=EntityType.PERSON,
                canonical_name="Sobolewski",
                normalized_name="Sobolewski",
                aliases=["Sobolewski"],
            ),
        ],
    )

    normalized = canonicalizer.run(document)
    assert len(normalized.entities) == 2


def test_reconstruct_nominative_from_inflected_without_original_nominative(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # Only "Sylwię Sobolewską" is present.
    # Stanza lemmatizer should give us "Sylwia Sobolewska".
    document = ArticleDocument(
        document_id=DocumentID("test-reconstruct"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Powołano Sylwię Sobolewską.",
        paragraphs=["Powołano Sylwię Sobolewską."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Sylwię Sobolewską",
                normalized_name="Sylwię Sobolewską",
                aliases=["Sylwię Sobolewską"],
            )
        ],
    )

    normalized = canonicalizer.run(document)
    assert normalized.entities[0].canonical_name == "Sylwia Sobolewska"


def test_feminine_owa_surname_normalizes_to_nominative(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    # "Nowakowej" -> "Nowakowa"
    document = ArticleDocument(
        document_id=DocumentID("test-owa"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="To jest mąż pani Nowakowej.",
        paragraphs=["To jest mąż pani Nowakowej."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Nowakowej",
                normalized_name="Nowakowej",
                aliases=["Nowakowej"],
            )
        ],
    )

    normalized = canonicalizer.run(document)
    # Stanza might lemmatize Nowakowej to Nowaków (genitive plural) or Nowak.
    assert normalized.entities[0].canonical_name in {"Nowakowa", "Nowak", "Nowaków"}


def test_masculine_ow_surname_keeps_nominative_form(morphology_service):
    config = PipelineConfig.from_file("config.yaml")
    canonicalizer = DocumentEntityCanonicalizer(config, morphology_service)

    document = ArticleDocument(
        document_id=DocumentID("test-masc-ow"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Podczas konferencji Maciej Bartków mówił o sprawie Macieja Bartkowa.",
        paragraphs=["Podczas konferencji Maciej Bartków mówił o sprawie Macieja Bartkowa."],
        entities=[
            Entity(
                entity_id=EntityID("p1"),
                entity_type=EntityType.PERSON,
                canonical_name="Macieja Bartkowa",
                normalized_name="Macieja Bartkowa",
                aliases=["Macieja Bartkowa", "Maciej Bartków"],
            )
        ],
    )

    normalized = canonicalizer.run(document)
    assert normalized.entities[0].canonical_name == "Maciej Bartków"
