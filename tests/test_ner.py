from pipeline.config import PipelineConfig
from pipeline.domain_types import DocumentID, EntityType
from pipeline.models import ArticleDocument
from pipeline.ner import SpacyPolishNERExtractor
from pipeline.segmentation import ParagraphSentenceSegmenter


class FakeEnt:
    def __init__(self, text: str, start_char: int, end_char: int) -> None:
        self.text = text
        self.start_char = start_char
        self.end_char = end_char


def test_person_name_normalization_uses_lemmas() -> None:
    config = PipelineConfig.from_file("config.yaml")
    segmenter = ParagraphSentenceSegmenter(config)
    extractor = SpacyPolishNERExtractor(config)
    document = ArticleDocument(
        document_id=DocumentID("doc-1"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date=None,
        cleaned_text="Hanna Gronkiewicz-Waltz spotkała Hanny Gronkiewicz-Waltz.",
        paragraphs=["Hanna Gronkiewicz-Waltz spotkała Hanny Gronkiewicz-Waltz."],
    )

    document = segmenter.run(document)
    document = extractor.run(document)

    people = [entity for entity in document.entities if entity.entity_type == "Person"]

    assert len(people) == 1
    assert people[0].canonical_name == "Hanna Gronkiewicz-Waltz"


def test_business_context_person_span_is_retyped_as_organization() -> None:
    text = "Firma Wnuk Consulting podpisała umowę. Właściciel Wnuk Consulting odmówił."

    assert SpacyPolishNERExtractor._person_span_looks_like_org(
        FakeEnt("Wnuk Consulting", 6, 21),
        text,
    )
    assert SpacyPolishNERExtractor._person_span_looks_like_org(
        FakeEnt("Wnuk Consulting", 55, 70),
        text,
    )


def test_location_like_spacy_labels_map_to_location_entity_type() -> None:
    assert SpacyPolishNERExtractor._map_label("geogName") == EntityType.LOCATION
    assert SpacyPolishNERExtractor._map_label("placeName") == EntityType.LOCATION
    assert SpacyPolishNERExtractor._map_label("GPE") == EntityType.LOCATION
    assert SpacyPolishNERExtractor._map_label("LOC") == EntityType.LOCATION
