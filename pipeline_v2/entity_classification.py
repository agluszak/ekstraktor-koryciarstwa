from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate, EntityContextProposal
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, MentionId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    CanonicalHintMatchSignal,
    EntityKind,
    EntityTag,
    GoverningBodyLemmaSignal,
    MediaOutletLemmaSignal,
    MinistryLemmaSignal,
    PublicInstitutionLemmaSignal,
    Signal,
    TreasuryLemmaSignal,
)

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
_GOVERNING_BODY_HINTS = frozenset({"rn", "rada nadzorcza", "zarząd"})
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


class LexicalEntityContextStage:
    """Emit `EntityContextProposal` records for organization entities based on
    lemma and canonical-hint cues.  Posteriors are computed by the inference
    stage; this stage only proposes."""

    name_ = "lexical_entity_context_stage_v2"

    def name(self) -> str:
        return self.name_

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for candidate in document.store.entity_candidates.values():
            document.entity_context_proposals.extend(
                entity_context_proposals_for(document.store, candidate)
            )
        return document


def entity_context_proposals_for(
    store: ExtractionStore,
    candidate: EntityCandidate,
) -> tuple[EntityContextProposal, ...]:
    if candidate.kind is not EntityKind.ORGANIZATION:
        return ()

    triggers_by_tag: dict[EntityTag, list[tuple[EvidenceId, Signal]]] = {}
    normalized_hint = _normalize_hint(candidate.canonical_hint)
    first_evidence_id = _first_mention_evidence_id(store, candidate)

    if first_evidence_id is not None:
        hint_signal = CanonicalHintMatchSignal(hint=normalized_hint)
        if normalized_hint in _GENERIC_OWNER_HINTS:
            triggers_by_tag.setdefault(EntityTag.GENERIC_OWNER, []).append(
                (first_evidence_id, hint_signal)
            )
        if normalized_hint in _MEDIA_HINTS:
            triggers_by_tag.setdefault(EntityTag.MEDIA_OUTLET, []).append(
                (first_evidence_id, hint_signal)
            )
        if normalized_hint in _GOVERNING_BODY_HINTS:
            triggers_by_tag.setdefault(EntityTag.GOVERNING_BODY, []).append(
                (first_evidence_id, hint_signal)
            )

    for mention in store.candidate_mentions(candidate.id):
        mention_lemmas = _mention_lemmas(store, mention.id, mention.head_lemma)
        evidence_id = mention.evidence_id

        if "ministerstwo" in mention_lemmas:
            triggers_by_tag.setdefault(EntityTag.GENERIC_OWNER, []).append(
                (evidence_id, MinistryLemmaSignal(lemma="ministerstwo"))
            )
        if "skarb" in mention_lemmas:
            triggers_by_tag.setdefault(EntityTag.GENERIC_OWNER, []).append(
                (evidence_id, TreasuryLemmaSignal(lemma="skarb"))
            )
        for lemma in sorted(mention_lemmas & _PUBLIC_INSTITUTION_LEMMAS):
            triggers_by_tag.setdefault(EntityTag.PUBLIC_INSTITUTION, []).append(
                (evidence_id, PublicInstitutionLemmaSignal(lemma=lemma))
            )
        for lemma in sorted(mention_lemmas & _MEDIA_LEMMAS):
            triggers_by_tag.setdefault(EntityTag.MEDIA_OUTLET, []).append(
                (evidence_id, MediaOutletLemmaSignal(lemma=lemma))
            )
        if "zarząd" in mention_lemmas:
            triggers_by_tag.setdefault(EntityTag.GOVERNING_BODY, []).append(
                (evidence_id, GoverningBodyLemmaSignal(lemma="zarząd"))
            )
        if {"rada", "nadzorczy"} <= mention_lemmas:
            triggers_by_tag.setdefault(EntityTag.GOVERNING_BODY, []).append(
                (evidence_id, GoverningBodyLemmaSignal(lemma="rada nadzorcza"))
            )

    # GENERIC_OWNER implies PUBLIC_INSTITUTION: re-use the same evidence and signals
    # (a ministry or treasury entity is by construction a public institution).
    if (
        EntityTag.GENERIC_OWNER in triggers_by_tag
        and EntityTag.PUBLIC_INSTITUTION not in triggers_by_tag
    ):
        triggers_by_tag[EntityTag.PUBLIC_INSTITUTION] = list(
            triggers_by_tag[EntityTag.GENERIC_OWNER]
        )

    proposals: list[EntityContextProposal] = []
    for tag in sorted(triggers_by_tag.keys(), key=lambda item: item.value):
        triggers = triggers_by_tag[tag]
        evidence_ids = tuple(dict.fromkeys(evidence for evidence, _ in triggers))
        signals = tuple(dict.fromkeys(signal for _, signal in triggers))
        proposals.append(
            EntityContextProposal(
                entity_id=candidate.id,
                context_kind=tag,
                evidence_ids=evidence_ids,
                retrieval_signals=signals,
            )
        )
    return tuple(proposals)


def entity_has_context_claim(
    store: ExtractionStore,
    entity_id: EntityCandidateId,
    tag: EntityTag,
) -> bool:
    """True if a post-inference `EntityContextClaim` for this (entity, tag)
    exists in the store.  Use this in code that runs after the inference stage
    (materialization, output, tests)."""
    for claim in store.entity_context_claims_for_entity(entity_id):
        if claim.context_kind is tag:
            return True
    return False


def entity_has_lexical_context_proposal(
    document: ArticleDocument,
    entity_id: EntityCandidateId,
    tag: EntityTag,
) -> bool:
    """True if a lexical `EntityContextProposal` for this (entity, tag) was
    emitted by `LexicalEntityContextStage`.  Use this in code that runs at
    producer time (before inference), where claims do not yet exist."""
    for proposal in document.entity_context_proposals:
        if proposal.entity_id == entity_id and proposal.context_kind is tag:
            return True
    return False


def _first_mention_evidence_id(
    store: ExtractionStore,
    candidate: EntityCandidate,
) -> EvidenceId | None:
    for mention_id in candidate.mention_ids:
        mention = store.mentions.get(mention_id)
        if mention is not None:
            return mention.evidence_id
    return None


def _mention_lemmas(
    store: ExtractionStore,
    mention_id: MentionId,
    head_lemma: str | None,
) -> frozenset[str]:
    lemmas: set[str] = set()
    if head_lemma is not None:
        lemmas.add(head_lemma.casefold())
    for token in store.tokens_for_mention(mention_id):
        lemma = token.preferred_lemma() or token.text
        lemmas.add(lemma.casefold())
    return frozenset(lemmas)


def _normalize_hint(hint: str | None) -> str:
    if hint is None:
        return ""
    return " ".join(hint.casefold().replace(".", " ").split())
