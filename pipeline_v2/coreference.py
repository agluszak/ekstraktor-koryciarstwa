from __future__ import annotations

from typing import Protocol

from pipeline_v2.candidates import ReferenceResolutionProposal
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, ProducerId, SentenceId
from pipeline_v2.nlp import (
    CoreferenceSpanLink,
    EvidenceSpan,
    MentionFactory,
    MorphAnalysis,
    MorphologyAdapter,
    ReferenceMention,
    Token,
)
from pipeline_v2.types import (
    CoreferenceProviderLinkSignal,
    EntityKind,
    NearbyPersonCandidateSignal,
    ReferenceKind,
    RelationshipDetail,
    ThirdPersonPronounSignal,
)


class CoreferenceProvider(Protocol):
    def links(self, text: str) -> tuple[CoreferenceSpanLink, ...]: ...


class CoreferenceReferenceStage:
    producer_id = ProducerId("coreference_reference_stage_v2")

    _family_details_by_lemma = {
        "brat": RelationshipDetail.SIBLING,
        "córka": RelationshipDetail.CHILD,
        "dziewczyna": RelationshipDetail.SPOUSE,
        "kuzyn": RelationshipDetail.FAMILY,
        "kuzynka": RelationshipDetail.FAMILY,
        "matka": RelationshipDetail.PARENT,
        "mąż": RelationshipDetail.SPOUSE,
        "ojciec": RelationshipDetail.PARENT,
        "partner": RelationshipDetail.SPOUSE,
        "partnerka": RelationshipDetail.SPOUSE,
        "siostra": RelationshipDetail.SIBLING,
        "syn": RelationshipDetail.CHILD,
        "teść": RelationshipDetail.FAMILY,
        "teściowa": RelationshipDetail.FAMILY,
        "żona": RelationshipDetail.SPOUSE,
    }

    def __init__(
        self,
        *,
        provider: CoreferenceProvider,
        morphology: MorphologyAdapter,
    ) -> None:
        self.provider = provider
        self.mention_factory = MentionFactory(morphology)

    def name(self) -> str:
        return "coreference_reference_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for link in self.provider.links(document.cleaned_text):
            sentence_id = document.store.sentence_id_for_offset(link.reference_span.start_char)
            if sentence_id is None:
                continue
            evidence = EvidenceSpan(
                id=document.store.next_evidence_id(),
                text=link.reference_text,
                span=link.reference_span,
                sentence_id=sentence_id,
                paragraph_index=document.store.sentences[sentence_id].paragraph_index,
                source=self.producer_id,
            )
            document.store.add_evidence(evidence)
            reference_id = document.store.next_reference_id()
            head_lemma = self.mention_factory.head_lemma(link.reference_text)

            token_ids = document.store.token_ids_for_span(
                sentence_id=sentence_id,
                span=evidence,
            )

            ref_kind = link.reference_kind
            relationship_detail = link.relationship_detail

            family_detail = None
            for tid in token_ids:
                token = document.store.tokens[tid]
                for analysis in token.morph:
                    if analysis.lemma in self._family_details_by_lemma:
                        family_detail = self._family_details_by_lemma[analysis.lemma]
                        break
                if family_detail is not None:
                    break

            if family_detail is not None:
                ref_kind = ReferenceKind.PROXY_FAMILY_PHRASE
                relationship_detail = family_detail

            document.store.add_reference(
                ReferenceMention(
                    id=reference_id,
                    text=link.reference_text,
                    kind=ref_kind,
                    evidence_id=evidence.id,
                    sentence_id=sentence_id,
                    token_ids=token_ids,
                    head_lemma=head_lemma,
                    relationship_detail=relationship_detail,
                )
            )
            antecedent_evidence = EvidenceSpan(
                id=EvidenceId("antecedent-lookup"),
                text=link.antecedent_text,
                span=link.antecedent_span,
            )
            for candidate_id in document.store.candidate_ids_with_evidence_overlapping_span(
                antecedent_evidence
            ):
                document.reference_resolution_proposals.append(
                    ReferenceResolutionProposal(
                        reference_id=reference_id,
                        candidate_entity_id=candidate_id,
                        evidence_ids=(evidence.id,),
                        retrieval_signals=(CoreferenceProviderLinkSignal(),),
                    )
                )
        return document


class LightReferenceStage:
    """Cheap pronoun reference producer based on Morfeusz token analyses.

    This stage does not perform coreference. It emits typed reference mentions
    for third-person pronouns and proposes nearby person candidates as possible
    referents, leaving the final assessment to scorers.
    """

    producer_id = ProducerId("light_reference_stage_v2")

    def __init__(self) -> None:
        self.reference_lemmas = frozenset({"on"})

    def name(self) -> str:
        return "light_reference_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            for token_id in sentence.token_ids:
                token = document.store.tokens[token_id]
                if not self._is_third_person_pronoun(token.morph):
                    continue
                evidence = EvidenceSpan(
                    id=document.store.next_evidence_id(),
                    text=token.text,
                    span=token.span,
                    sentence_id=sentence.id,
                    paragraph_index=sentence.paragraph_index,
                    source=self.producer_id,
                )
                document.store.add_evidence(evidence)
                reference_id = document.store.next_reference_id()
                document.store.add_reference(
                    ReferenceMention(
                        id=reference_id,
                        text=token.text,
                        kind=self._reference_kind(token),
                        evidence_id=evidence.id,
                        sentence_id=sentence.id,
                        token_ids=(token.id,),
                        head_lemma=token.preferred_lemma(),
                    )
                )
                for candidate_id in self._nearby_person_candidates(document, sentence.id):
                    document.reference_resolution_proposals.append(
                        ReferenceResolutionProposal(
                            reference_id=reference_id,
                            candidate_entity_id=candidate_id,
                            evidence_ids=(evidence.id,),
                            retrieval_signals=(
                                ThirdPersonPronounSignal(),
                                NearbyPersonCandidateSignal(),
                            ),
                        )
                    )
        return document

    def _is_third_person_pronoun(self, analyses: tuple[MorphAnalysis, ...]) -> bool:
        return any(
            analysis.pos == "ppron3" and analysis.lemma in self.reference_lemmas
            for analysis in analyses
        )

    def _reference_kind(self, token: Token) -> ReferenceKind:
        lower_text = token.text.casefold()
        if lower_text in {"jego", "jej", "ich"}:
            return ReferenceKind.POSSESSIVE_PRONOUN
        return ReferenceKind.PRONOUN

    def _nearby_person_candidates(
        self,
        document: ArticleDocument,
        sentence_id: SentenceId,
    ) -> tuple[EntityCandidateId, ...]:
        sentence = document.store.sentences[sentence_id]
        candidate_ids: list[EntityCandidateId] = []
        for candidate in document.store.candidates_by_kind(EntityKind.PERSON):
            for evidence in document.store.evidence_for_entity(candidate.id):
                if evidence.paragraph_index != sentence.paragraph_index:
                    continue
                if evidence.sentence_id is None:
                    continue
                candidate_sentence = document.store.sentences[evidence.sentence_id]
                if 0 <= sentence.sentence_index - candidate_sentence.sentence_index <= 1:
                    candidate_ids.append(candidate.id)
                    break
        return tuple(dict.fromkeys(candidate_ids))
