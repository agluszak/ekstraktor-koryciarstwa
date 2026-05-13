from __future__ import annotations

from pipeline.document_graph import merge_entities
from pipeline.domain_types import EntityID
from pipeline.models import ArticleDocument, Entity, EvidenceSpan
from pipeline.utils import unique_preserve_order


def _evidence_key(
    evidence: EvidenceSpan,
) -> tuple[str, int | None, int | None, int | None, int | None]:
    return (
        evidence.text,
        evidence.sentence_index,
        evidence.paragraph_index,
        evidence.start_char,
        evidence.end_char,
    )


class EntityGraphRemapper:
    @staticmethod
    def merge_entity(target: Entity, source: Entity) -> None:
        target.aliases = unique_preserve_order(
            [*target.aliases, target.canonical_name, source.canonical_name, *source.aliases]
        )
        seen_evidence = {_evidence_key(evidence) for evidence in target.evidence}
        for evidence in source.evidence:
            evidence_key = _evidence_key(evidence)
            if evidence_key in seen_evidence:
                continue
            target.evidence.append(evidence)
            seen_evidence.add(evidence_key)
        target.mention_ids = list(dict.fromkeys([*target.mention_ids, *source.mention_ids]))
        target.lemmas = unique_preserve_order([*target.lemmas, *source.lemmas])
        target.registry_id = (
            target.registry_id if target.registry_id is not None else source.registry_id
        )
        target.organization_kind = (
            target.organization_kind
            if target.organization_kind is not None
            else source.organization_kind
        )
        target.is_proxy_person = target.is_proxy_person or source.is_proxy_person
        target.is_honorific_person_ref = (
            target.is_honorific_person_ref or source.is_honorific_person_ref
        )
        target.proxy_kind = (
            target.proxy_kind if target.proxy_kind is not None else source.proxy_kind
        )
        target.kinship_detail = (
            target.kinship_detail if target.kinship_detail is not None else source.kinship_detail
        )
        target.proxy_anchor_entity_id = (
            target.proxy_anchor_entity_id
            if target.proxy_anchor_entity_id is not None
            else source.proxy_anchor_entity_id
        )
        target.role_kind = target.role_kind if target.role_kind is not None else source.role_kind
        target.role_modifier = (
            target.role_modifier if target.role_modifier is not None else source.role_modifier
        )

    @staticmethod
    def apply_remap(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
        merge_entities(document, remap, merge_fn=EntityGraphRemapper.merge_entity)
