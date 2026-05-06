from pipeline.domain_types import (
    ClauseID,
    ClusterID,
    DocumentID,
    EntityID,
    EntityType,
    KinshipDetail,
)
from pipeline.identity_signals import (
    collect_family_mentions,
    collect_honorific_mentions,
    resolve_possessive_anchor,
)
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    Entity,
    ResolvedEntity,
    EvidenceSpan,
    ParsedWord,
    SentenceFragment,
)


def _word(
    index: int,
    text: str,
    lemma: str,
    upos: str,
    head: int,
    deprel: str,
    start: int,
) -> ParsedWord:
    return ParsedWord(
        index=index,
        text=text,
        lemma=lemma,
        upos=upos,
        head=head,
        deprel=deprel,
        start=start,
        end=start + len(text),
    )


def _document(sentences: list[str], parsed: dict[int, list[ParsedWord]]) -> ArticleDocument:
    offsets: list[int] = []
    cursor = 0
    for sentence in sentences:
        offsets.append(cursor)
        cursor += len(sentence) + 1
    text = " ".join(sentences)
    return ArticleDocument(
        document_id=DocumentID("identity-signals-doc"),
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-25",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=sentence,
                paragraph_index=0,
                sentence_index=index,
                start_char=offsets[index],
                end_char=offsets[index] + len(sentence),
            )
            for index, sentence in enumerate(sentences)
        ],
        parsed_sentences=parsed,
        clause_units=[
            ClauseUnit(
                clause_id=ClauseID(f"clause-{index}"),
                text=sentence,
                trigger_head_text="",
                trigger_head_lemma="",
                sentence_index=index,
                paragraph_index=0,
                start_char=offsets[index],
                end_char=offsets[index] + len(sentence),
            )
            for index, sentence in enumerate(sentences)
        ],
    )


def _person_cluster(
    entity_id: str,
    name: str,
    *,
    sentence_index: int,
    paragraph_index: int,
    start_char: int,
) -> tuple[Entity, ResolvedEntity]:
    evidence = EvidenceSpan(
        text=name,
        sentence_index=sentence_index,
        paragraph_index=paragraph_index,
        start_char=start_char,
        end_char=start_char + len(name),
    )
    entity = Entity(
        entity_id=EntityID(entity_id),
        entity_type=EntityType.PERSON,
        canonical_name=name,
        normalized_name=name,
        evidence=[evidence],
    )
    cluster = ResolvedEntity(
        entity_id=EntityID(f"cluster-{entity_id}"),
        entity_type=EntityType.PERSON,
        canonical_name=name,
        normalized_name=name,
        mentions=[
            ClusterMention(
                text=name,
                entity_type=EntityType.PERSON,
                sentence_index=sentence_index,
                paragraph_index=paragraph_index,
                start_char=start_char,
                end_char=start_char + len(name),
                entity_id=EntityID(entity_id),
            )
        ],
    )
    return entity, cluster


def test_collect_family_mentions_marks_public_role_subject_as_possessive_anchor() -> None:
    sentence = SentenceFragment(
        text="Wojewoda zatrudnił żonę.",
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len("Wojewoda zatrudnił żonę."),
    )
    words = [
        _word(1, "Wojewoda", "wojewoda", "NOUN", 2, "nsubj", 0),
        _word(2, "zatrudnił", "zatrudnić", "VERB", 0, "root", 9),
        _word(3, "żonę", "żona", "NOUN", 2, "obj", 19),
    ]

    mentions = collect_family_mentions(sentence, words)

    assert len(mentions) == 1
    assert mentions[0].kinship_detail == KinshipDetail.SPOUSE
    assert mentions[0].is_possessive is True
    assert mentions[0].anchor_surface is None


def test_collect_honorific_mentions_extracts_pani_plus_surname() -> None:
    sentence = SentenceFragment(
        text="Pani Kowalska pracuje w urzędzie.",
        paragraph_index=0,
        sentence_index=0,
        start_char=0,
        end_char=len("Pani Kowalska pracuje w urzędzie."),
    )
    words = [
        _word(1, "Pani", "pani", "NOUN", 2, "flat", 0),
        _word(2, "Kowalska", "Kowalska", "PROPN", 3, "nsubj", 5),
        _word(3, "pracuje", "pracować", "VERB", 0, "root", 14),
    ]

    mentions = collect_honorific_mentions(sentence, words)

    assert len(mentions) == 1
    assert mentions[0].surface == "Pani Kowalska"
    assert mentions[0].surname == "Kowalska"


def test_resolve_possessive_anchor_uses_split_quote_speaker_context() -> None:
    sentences = ['"Moja żona pracuje w urzędzie."', "mówi Jan Kowalski."]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Moja", "mój", "DET", 2, "det", 1),
                _word(2, "żona", "żona", "NOUN", 3, "nsubj", 6),
                _word(3, "pracuje", "pracować", "VERB", 0, "root", 11),
            ],
            1: [
                _word(1, "mówi", "mówić", "VERB", 0, "root", 0),
                _word(2, "Jan", "Jan", "PROPN", 1, "nsubj", 5),
                _word(3, "Kowalski", "Kowalski", "PROPN", 2, "flat", 9),
            ],
        },
    )
    entity, cluster = _person_cluster(
        "person-jan",
        "Jan Kowalski",
        sentence_index=1,
        paragraph_index=0,
        start_char=len(sentences[0]) + 1 + 5,
    )
    doc.entities.append(entity)
    doc.resolved_entities.append(cluster)

    anchor = resolve_possessive_anchor(doc, 0)

    assert anchor is not None
    assert anchor.entity_id == cluster.entity_id
