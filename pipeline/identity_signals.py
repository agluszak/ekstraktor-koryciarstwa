from __future__ import annotations

from dataclasses import dataclass

from pipeline.cluster_reads import (
    aliases_for_cluster as read_aliases_for_cluster,
)
from pipeline.cluster_reads import (
    canonical_name_for_cluster as read_canonical_name_for_cluster,
)
from pipeline.cluster_reads import (
    entity_for_cluster as read_entity_for_cluster,
)
from pipeline.cluster_reads import (
    entity_type_for_cluster as read_entity_type_for_cluster,
)
from pipeline.document_graph import derived_clusters
from pipeline.domain_lexicons import (
    ATTRIBUTION_SPEECH_LEMMAS,
    KINSHIP_BY_LEMMA,
    PUBLIC_SUBJECT_ROLE_LEMMAS,
)
from pipeline.domain_types import EntityID, EntityType, KinshipDetail
from pipeline.models import ArticleDocument, Entity, EntityCluster, ParsedWord, SentenceFragment
from pipeline.utils import normalize_entity_name

POSSESSIVE_LEMMAS = {"mój", "swój"}
HONORIFIC_LEMMAS = {"pani"}


@dataclass(slots=True)
class FamilyMention:
    sentence_index: int
    paragraph_index: int
    kinship_detail: KinshipDetail
    surface: str
    start_char: int
    end_char: int
    anchor_surface: str | None = None
    is_possessive: bool = False


@dataclass(slots=True)
class HonorificMention:
    sentence_index: int
    paragraph_index: int
    surface: str
    surname: str
    start_char: int
    end_char: int


def collect_family_mentions(
    sentence: SentenceFragment,
    words: list[ParsedWord],
) -> list[FamilyMention]:
    mentions: list[FamilyMention] = []
    for index, word in enumerate(words):
        kinship_detail = family_kinship_detail(word)
        if kinship_detail is None:
            continue
        possessive_word = possessive_modifier(words, word, index)
        if possessive_word is not None:
            start = sentence.start_char + min(possessive_word.start, word.start)
            end = sentence.start_char + max(possessive_word.end, word.end)
            surface = surface_for_span(sentence, start, end, [possessive_word, word])
            if not surface:
                continue
            mentions.append(
                FamilyMention(
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    kinship_detail=kinship_detail,
                    surface=surface,
                    start_char=start,
                    end_char=end,
                    is_possessive=True,
                )
            )
            continue

        anchor = anchor_words(words, index)
        if not anchor:
            if not has_local_public_role_subject(words, word):
                continue
            start = sentence.start_char + word.start
            end = sentence.start_char + word.end
            surface = surface_for_span(sentence, start, end, [word])
            if not surface:
                continue
            mentions.append(
                FamilyMention(
                    sentence_index=sentence.sentence_index,
                    paragraph_index=sentence.paragraph_index,
                    kinship_detail=kinship_detail,
                    surface=surface,
                    start_char=start,
                    end_char=end,
                    is_possessive=True,
                )
            )
            continue

        start = sentence.start_char + word.start
        end = sentence.start_char + anchor[-1].end
        anchor_surface = surface_from_words(sentence, anchor)
        surface = surface_for_span(sentence, start, end, [word, *anchor])
        if not surface:
            continue
        mentions.append(
            FamilyMention(
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                kinship_detail=kinship_detail,
                surface=surface,
                start_char=start,
                end_char=end,
                anchor_surface=anchor_surface,
            )
        )
    return mentions


def collect_honorific_mentions(
    sentence: SentenceFragment,
    words: list[ParsedWord],
) -> list[HonorificMention]:
    mentions: list[HonorificMention] = []
    for index, word in enumerate(words[:-1]):
        if word.lemma.casefold() not in HONORIFIC_LEMMAS:
            continue
        surname_word = words[index + 1]
        if surname_word.upos not in {"PROPN", "NOUN"}:
            continue
        if not surname_word.text[:1].isupper():
            continue
        start = sentence.start_char + word.start
        end = sentence.start_char + surname_word.end
        surface = surface_for_span(sentence, start, end, [word, surname_word])
        if not surface:
            continue
        mentions.append(
            HonorificMention(
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                surface=surface,
                surname=surname_word.text,
                start_char=start,
                end_char=end,
            )
        )
    return mentions


def family_kinship_detail(word: ParsedWord) -> KinshipDetail | None:
    lemma = normalize_entity_name(word.lemma).casefold()
    text = normalize_entity_name(word.text).casefold()
    return KINSHIP_BY_LEMMA.get(lemma) or KINSHIP_BY_LEMMA.get(text)


def possessive_modifier(
    words: list[ParsedWord],
    kinship_word: ParsedWord,
    kinship_index: int,
) -> ParsedWord | None:
    candidates = [
        word
        for word in words
        if word.head == kinship_word.index
        and word.lemma.casefold() in POSSESSIVE_LEMMAS
        and word.deprel.startswith("det")
    ]
    if candidates:
        return candidates[0]
    if kinship_index > 0 and words[kinship_index - 1].lemma.casefold() in POSSESSIVE_LEMMAS:
        return words[kinship_index - 1]
    return None


def anchor_words(words: list[ParsedWord], kinship_index: int) -> list[ParsedWord]:
    after = words[kinship_index + 1 : kinship_index + 5]
    if (
        len(after) >= 2
        and after[0].lemma.casefold() == "pan"
        and after[1].lemma.casefold() == "przewodniczący"
    ):
        return after[:2]
    if len(after) >= 3 and after[0].lemma.casefold() in {
        "wójt",
        "wojt",
        "wojewoda",
        "starosta",
        "marszałek",
        "sekretarz",
    }:
        role_anchor: list[ParsedWord] = []
        for word in after[1:]:
            if word.upos != "PROPN":
                break
            role_anchor.append(word)
        if role_anchor:
            return role_anchor
        return after[:1]
    proper: list[ParsedWord] = []
    for word in after:
        if word.upos != "PROPN":
            break
        proper.append(word)
    return proper


def has_local_public_role_subject(
    words: list[ParsedWord],
    kinship_word: ParsedWord,
) -> bool:
    by_index = {word.index: word for word in words}
    governing_indices = {kinship_word.head}
    head = by_index.get(kinship_word.head)
    if head is not None and kinship_word.deprel == "conj":
        governing_indices.add(head.head)
    for word in words:
        if word.index == kinship_word.index:
            continue
        if not word.deprel.startswith("nsubj"):
            continue
        if word.head not in governing_indices:
            continue
        if word.lemma.casefold() in PUBLIC_SUBJECT_ROLE_LEMMAS:
            return True
    return False


def surface_from_words(sentence: SentenceFragment, words: list[ParsedWord]) -> str:
    if not words:
        return ""
    return surface_for_span(
        sentence,
        sentence.start_char + words[0].start,
        sentence.start_char + words[-1].end,
        words,
    )


def sentence_slice(sentence: SentenceFragment, start_char: int, end_char: int) -> str:
    local_start = max(0, start_char - sentence.start_char)
    local_end = max(local_start, end_char - sentence.start_char)
    return sentence.text[local_start:local_end]


def surface_for_span(
    sentence: SentenceFragment,
    start_char: int,
    end_char: int,
    words: list[ParsedWord],
) -> str:
    surface = sentence_slice(sentence, start_char, end_char)
    if surface.strip():
        return surface
    return " ".join(word.text for word in words if word.text).strip()


def resolve_anchor(
    document: ArticleDocument,
    sentence_index: int,
    anchor_surface: str | None,
) -> EntityCluster | None:
    entities_by_id = _entities_by_id(document)
    return _resolve_anchor(document, sentence_index, anchor_surface, entities_by_id)


def _resolve_anchor(
    document: ArticleDocument,
    sentence_index: int,
    anchor_surface: str | None,
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    if anchor_surface is None:
        return None
    normalized = normalize_entity_name(anchor_surface)
    normalized_lower = normalized.casefold()
    role_anchors = [marker for marker in PUBLIC_SUBJECT_ROLE_LEMMAS if marker in normalized_lower]
    if role_anchors:
        return person_cluster_with_role_context(
            document,
            sentence_index,
            role_anchors,
            entities_by_id,
        )
    if "przewodnicz" in normalized_lower:
        return nearest_person_cluster(
            document,
            sentence_index,
            before=3,
            after=0,
            entities_by_id=entities_by_id,
        )
    candidates = [
        cluster
        for cluster in derived_clusters(document)
        if _cluster_entity_type(document, cluster, entities_by_id) == EntityType.PERSON
        and not _cluster_is_proxy_person(document, cluster, entities_by_id)
        and (
            _cluster_canonical_name(document, cluster, entities_by_id) == normalized
            or normalized in _cluster_aliases(document, cluster, entities_by_id)
            or surnames_compatible(
                _cluster_canonical_name(document, cluster, entities_by_id),
                normalized,
            )
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda cluster: cluster_sentence_distance(cluster, sentence_index))


def resolve_possessive_anchor(
    document: ArticleDocument,
    sentence_index: int,
) -> EntityCluster | None:
    entities_by_id = _entities_by_id(document)
    return speaker_cluster(document, sentence_index, entities_by_id) or subject_person_cluster(
        document,
        sentence_index,
        entities_by_id,
    )


def subject_person_cluster(
    document: ArticleDocument,
    sentence_index: int,
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    parsed = document.parsed_sentences.get(sentence_index, [])
    subject_words = [word for word in parsed if word.deprel.startswith("nsubj")]
    if not subject_words:
        return None
    sentence = next(
        (item for item in document.sentences if item.sentence_index == sentence_index), None
    )
    if sentence is None:
        return None
    for cluster in derived_clusters(document):
        if _cluster_entity_type(document, cluster, entities_by_id) != EntityType.PERSON or (
            _cluster_is_proxy_person(document, cluster, entities_by_id)
        ):
            continue
        for mention in cluster.mentions:
            if mention.sentence_index != sentence_index:
                continue
            for word in subject_words:
                abs_start = sentence.start_char + word.start
                if mention.start_char <= abs_start < mention.end_char:
                    return cluster
    public_role_subjects = [
        word.lemma.casefold()
        for word in subject_words
        if word.lemma.casefold() in PUBLIC_SUBJECT_ROLE_LEMMAS
    ]
    if public_role_subjects:
        role_context_cluster = person_cluster_with_role_context(
            document,
            sentence_index,
            public_role_subjects,
            entities_by_id,
        )
        if role_context_cluster is not None:
            return role_context_cluster
        return nearest_person_cluster(
            document,
            sentence_index,
            before=3,
            after=0,
            entities_by_id=entities_by_id,
        )
    return None


def person_cluster_with_role_context(
    document: ArticleDocument,
    sentence_index: int,
    role_lemmas: list[str],
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    sentences = {sentence.sentence_index: sentence for sentence in document.sentences}
    candidates: list[tuple[int, int, EntityCluster]] = []
    role_markers = tuple(role_lemmas)
    for cluster in derived_clusters(document):
        if _cluster_entity_type(document, cluster, entities_by_id) != EntityType.PERSON or (
            _cluster_is_proxy_person(document, cluster, entities_by_id)
        ):
            continue
        for mention in cluster.mentions:
            if not sentence_index - 3 <= mention.sentence_index <= sentence_index:
                continue
            sentence = sentences.get(mention.sentence_index)
            if sentence is None:
                continue
            local_start = max(0, mention.start_char - sentence.start_char)
            local_end = max(local_start, mention.end_char - sentence.start_char)
            window = sentence.text[max(0, local_start - 80) : local_end + 32].casefold()
            if not any(marker in window for marker in role_markers):
                continue
            candidates.append(
                (
                    abs(sentence_index - mention.sentence_index),
                    mention.start_char,
                    cluster,
                )
            )
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], -item[1]))[2]


def speaker_cluster(
    document: ArticleDocument,
    sentence_index: int,
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    cluster = speaker_cluster_raw(document, sentence_index, entities_by_id)
    if cluster is not None:
        return cluster

    sentence = next(
        (item for item in document.sentences if item.sentence_index == sentence_index), None
    )
    if sentence and (
        sentence.text.strip().startswith("–")
        or sentence.text.strip().startswith("—")
        or sentence.text.strip().startswith('"')
    ):
        next_index = sentence_index + 1
        next_sentence = next(
            (item for item in document.sentences if item.sentence_index == next_index),
            None,
        )
        if next_sentence and next_sentence.paragraph_index == sentence.paragraph_index:
            return speaker_cluster_raw(document, next_index, entities_by_id)

    return None


def speaker_cluster_raw(
    document: ArticleDocument,
    sentence_index: int,
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    parsed = document.parsed_sentences.get(sentence_index, [])
    speech_heads = {
        word.index for word in parsed if word.lemma.casefold() in ATTRIBUTION_SPEECH_LEMMAS
    }
    if not speech_heads:
        return None
    sentence = next(
        (item for item in document.sentences if item.sentence_index == sentence_index), None
    )
    if sentence is None:
        return None
    speaker_words = [
        word for word in parsed if word.head in speech_heads and word.deprel.startswith("nsubj")
    ]
    for cluster in derived_clusters(document):
        if _cluster_entity_type(document, cluster, entities_by_id) != EntityType.PERSON or (
            _cluster_is_proxy_person(document, cluster, entities_by_id)
        ):
            continue
        for mention in cluster.mentions:
            if mention.sentence_index != sentence_index:
                continue
            for word in speaker_words:
                abs_start = sentence.start_char + word.start
                if mention.start_char <= abs_start < mention.end_char:
                    return cluster
    return None


def nearest_person_cluster(
    document: ArticleDocument,
    sentence_index: int,
    *,
    before: int,
    after: int,
    entities_by_id: dict[EntityID, Entity],
) -> EntityCluster | None:
    candidates = [
        cluster
        for cluster in derived_clusters(document)
        if _cluster_entity_type(document, cluster, entities_by_id) == EntityType.PERSON
        and not _cluster_is_proxy_person(document, cluster, entities_by_id)
        and any(
            sentence_index - before <= mention.sentence_index <= sentence_index + after
            for mention in cluster.mentions
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda cluster: cluster_sentence_distance(cluster, sentence_index))


def cluster_sentence_distance(cluster: EntityCluster, sentence_index: int) -> tuple[int, int]:
    distances = [
        (abs(mention.sentence_index - sentence_index), mention.start_char)
        for mention in cluster.mentions
    ]
    return min(distances, default=(9999, 9999))


def surname(name: str) -> str:
    tokens = normalize_entity_name(name).split()
    if not tokens:
        return ""
    return tokens[-1]


def surnames_compatible(left_name: str, right_name: str) -> bool:
    return surname_tokens_compatible(surname(left_name), surname(right_name))


def surname_tokens_compatible(left: str, right: str) -> bool:
    left_key = left.rstrip(".").casefold()
    right_key = right.rstrip(".").casefold()
    if left_key == right_key:
        return True
    for suffix in ("iego", "ego", "ej", "ą", "a"):
        if left_key.endswith(suffix):
            left_key = left_key[: -len(suffix)]
            break
    for suffix in ("iego", "ego", "ej", "ą", "a"):
        if right_key.endswith(suffix):
            right_key = right_key[: -len(suffix)]
            break
    return (
        len(left_key) >= 4
        and len(right_key) >= 4
        and (left_key.startswith(right_key) or right_key.startswith(left_key))
    )


def _entities_by_id(document: ArticleDocument) -> dict[EntityID, Entity]:
    return {entity.entity_id: entity for entity in document.entities}


def _entity_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> Entity | None:
    return read_entity_for_cluster(cluster, entities_by_id)


def _cluster_entity_type(
    document: ArticleDocument,
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> EntityType:
    _ = document
    return read_entity_type_for_cluster(cluster, entities_by_id)


def _cluster_canonical_name(
    document: ArticleDocument,
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> str:
    _ = document
    return read_canonical_name_for_cluster(cluster, entities_by_id)


def _cluster_aliases(
    document: ArticleDocument,
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> list[str]:
    _ = document
    return read_aliases_for_cluster(cluster, entities_by_id)


def _cluster_is_proxy_person(
    document: ArticleDocument,
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> bool:
    _ = document
    entity = read_entity_for_cluster(cluster, entities_by_id)
    return entity.is_proxy_person if entity is not None else False
