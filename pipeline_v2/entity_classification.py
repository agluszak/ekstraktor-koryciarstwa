from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, ProducerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import EntityKind, EntityTag

_GENERIC_OWNER_HINTS = frozenset(
    {
        "map",
        "mf",
        "mon",
        "ministerstwo aktywów państwowych",
        "ministerstwo finansów",
        "ministerstwo obrony narodowej",
        "skarb państwa",
        "skarb państwa rp",
    }
)
_MEDIA_HINTS = frozenset(
    {
        "dziennik",
        "onet",
        "pap",
        "polsat",
        "radio zet",
        "tvn",
        "tvn24",
        "tvn warszawa",
        "wirtualna polska",
        "wp",
    }
)
_PUBLIC_INSTITUTION_LEMMAS = frozenset(
    {
        "agencja",
        "cba",
        "izba",
        "ministerstwo",
        "nik",
        "prokuratura",
        "urząd",
    }
)
_MEDIA_LEMMAS = frozenset(
    {
        "dziennik",
        "gazeta",
        "onet",
        "pap",
        "polsat",
        "portal",
        "radio",
        "telewizja",
        "tvn",
        "tvn24",
        "tygodnik",
        "wp",
    }
)


class EntityClassificationStage:
    producer_id = ProducerId("entity_classification_stage_v2")

    def name(self) -> str:
        return str(self.producer_id)

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for candidate in document.store.entity_candidates.values():
            tags = infer_entity_tags(document.store, candidate)
            if tags:
                document.store.add_entity_tags(candidate.id, tags)
        return document


def entity_has_tag(
    store: ExtractionStore,
    entity_id: EntityCandidateId,
    tag: EntityTag,
) -> bool:
    return tag in entity_tags(store, entity_id)


def entity_tags(
    store: ExtractionStore,
    entity_id: EntityCandidateId,
) -> frozenset[EntityTag]:
    cached = store.entity_tags.get(entity_id)
    if cached is not None:
        return cached
    candidate = store.entity_candidates.get(entity_id)
    if candidate is None:
        return frozenset()
    tags = infer_entity_tags(store, candidate)
    if tags:
        store.add_entity_tags(entity_id, tags)
    return tags


def infer_entity_tags(
    store: ExtractionStore,
    candidate: EntityCandidate,
) -> frozenset[EntityTag]:
    if candidate.kind is not EntityKind.ORGANIZATION:
        return frozenset()
    normalized_hint = _normalize_hint(candidate.canonical_hint)
    lemmas = _candidate_lemmas(store, candidate)
    tags: set[EntityTag] = set()
    if normalized_hint in _GENERIC_OWNER_HINTS or "ministerstwo" in lemmas or "skarb" in lemmas:
        tags.add(EntityTag.GENERIC_OWNER)
    if EntityTag.GENERIC_OWNER in tags or lemmas & _PUBLIC_INSTITUTION_LEMMAS:
        tags.add(EntityTag.PUBLIC_INSTITUTION)
    if normalized_hint in _MEDIA_HINTS or lemmas & _MEDIA_LEMMAS:
        tags.add(EntityTag.MEDIA_OUTLET)
    if (
        normalized_hint in {"rn", "rada nadzorcza", "zarząd"}
        or "zarząd" in lemmas
        or {"rada", "nadzorczy"} <= lemmas
    ):
        tags.add(EntityTag.GOVERNING_BODY)
    return frozenset(tags)


def _candidate_lemmas(
    store: ExtractionStore,
    candidate: EntityCandidate,
) -> frozenset[str]:
    lemmas: set[str] = set()
    for mention_id in candidate.mention_ids:
        mention = store.mentions.get(mention_id)
        if mention is not None and mention.head_lemma is not None:
            lemmas.add(mention.head_lemma.casefold())
        for token in store.tokens_for_mention(mention_id):
            lemma = token.preferred_lemma() or token.text
            lemmas.add(lemma.casefold())
    return frozenset(lemmas)


def _normalize_hint(hint: str | None) -> str:
    if hint is None:
        return ""
    return " ".join(hint.casefold().replace(".", " ").split())
