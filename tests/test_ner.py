from pipeline.config import PipelineConfig
from pipeline.models import ArticleDocument
from pipeline.ner import SpacyPolishNERExtractor
from pipeline.segmentation import ParagraphSentenceSegmenter


def test_person_name_normalization_uses_lemmas() -> None:
    config = PipelineConfig.from_file("config.yaml")
    segmenter = ParagraphSentenceSegmenter(config)
    extractor = SpacyPolishNERExtractor(config)
    document = ArticleDocument(
        document_id="doc-1",
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
