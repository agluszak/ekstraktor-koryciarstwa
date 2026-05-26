from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, ReferenceMention, Sentence, Token
from pipeline_v2.retrieval import SentenceEntityRetriever
from pipeline_v2.types import (
    DependencyRelation,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    MediumPossessorSignal,
    NegativePossessorSignal,
    NominalKinshipSignal,
    ReferenceKind,
    RelationshipDetail,
    Signal,
    StrongPossessorSignal,
    SyntaxPossessorSignal,
    WeakPossessorSignal,
)


@dataclass(frozen=True, slots=True)
class PossessorCandidate:
    entity_id: EntityCandidateId
    signals: tuple[Signal, ...]


class NominalKinshipCandidateStage:
    producer_id = ProducerId("nominal_kinship_candidate_stage_v2")

    _family_details_by_lemma = {
        "brat": RelationshipDetail.SIBLING,
        "córka": RelationshipDetail.CHILD,
        "dziewczyna": RelationshipDetail.SPOUSE,
        "kuzyn": RelationshipDetail.FAMILY,
        "kuzynka": RelationshipDetail.FAMILY,
        "matka": RelationshipDetail.PARENT,
        "mąż": RelationshipDetail.SPOUSE,
        "narzeczona": RelationshipDetail.SPOUSE,
        "narzeczony": RelationshipDetail.SPOUSE,
        "ojciec": RelationshipDetail.PARENT,
        "partner": RelationshipDetail.SPOUSE,
        "partnerka": RelationshipDetail.SPOUSE,
        "siostra": RelationshipDetail.SIBLING,
        "syn": RelationshipDetail.CHILD,
        "teść": RelationshipDetail.FAMILY,
        "teściowa": RelationshipDetail.FAMILY,
        "żona": RelationshipDetail.SPOUSE,
    }

    _possessive_pronouns = frozenset({"jego", "jej", "ich", "swój"})

    def name(self) -> str:
        return "nominal_kinship_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        retriever = SentenceEntityRetriever(document.store)
        for sentence in document.store.sentences.values():
            for token_id in sentence.token_ids:
                token = document.store.tokens[token_id]
                for analysis in token.morph:
                    if analysis.lemma in self._family_details_by_lemma:
                        self._process_kinship_token(
                            document,
                            sentence,
                            token_id,
                            analysis.lemma,
                            retriever,
                        )
                        break
        return document

    def _process_kinship_token(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        token_id: TokenId,
        lemma: str,
        retriever: SentenceEntityRetriever,
    ) -> None:
        token = document.store.tokens[token_id]

        signals: list[Signal] = [NominalKinshipSignal(lemma=lemma)]

        possessor = self._find_possessor_via_syntax(document, sentence, token_id, retriever)

        if possessor is None:
            possessor = self._find_possessor_via_pronoun(document, sentence, token_id, retriever)

        if possessor is None:
            possessor = self._find_possessor_via_adjacent_entity(
                document, sentence, token, retriever
            )

        if possessor is None:
            return
        possessor_id = possessor.entity_id
        signals.extend(possessor.signals)

        referent_id = self._find_referent(document, sentence, token, possessor_id, retriever)
        if referent_id is None:
            referent_id = self._find_discourse_referent(
                document,
                sentence,
                token,
                possessor_id,
                retriever,
            )

        relationship_detail = self._family_details_by_lemma[lemma]

        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=sentence.text,
            span=sentence.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)

        if referent_id is None:
            # Create a proxy entity for the unnamed family member!
            possessor = document.store.entity_candidates[possessor_id]
            possessor_name = possessor.canonical_hint or str(possessor_id)
            canonical_hint = f"{lemma} of {possessor_name}"

            # We can create a reference mention for the kinship token
            reference_id = document.store.next_reference_id()
            document.store.add_reference(
                ReferenceMention(
                    id=reference_id,
                    text=token.text,
                    kind=ReferenceKind.PROXY_FAMILY_PHRASE,
                    evidence_id=evidence.id,
                    sentence_id=sentence.id,
                    token_ids=(token.id,),
                    head_lemma=lemma,
                    relationship_detail=relationship_detail,
                )
            )

            referent_id = document.store.add_entity_candidate(
                EntityCandidate(
                    id=document.store.next_proxy_candidate_id(),
                    kind=EntityKind.PERSON,
                    mention_ids=(),
                    reference_ids=(reference_id,),
                    canonical_hint=canonical_hint,
                    grounding=GroundingKind.PROXY,
                    source=self.producer_id,
                )
            )

        event = EventCandidate(
            id=document.store.next_event_candidate_id(),
            kind=FactKind.KINSHIP_TIE,
            trigger_evidence_id=evidence.id,
            evidence_ids=(evidence.id,),
            source=self.producer_id,
            signals=tuple(signals),
        )
        document.store.add_event_candidate(event)
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.SUBJECT,
                filler=EntityFiller(referent_id),
                evidence_ids=(evidence.id,),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.OBJECT,
                filler=EntityFiller(possessor_id),
                evidence_ids=(evidence.id,),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.RELATIONSHIP_DETAIL,
                filler=TextFiller(relationship_detail.value),
                evidence_ids=(evidence.id,),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.CONTEXT,
                filler=TextFiller(lemma),
                evidence_ids=(evidence.id,),
            )
        )

    def _find_possessor_via_syntax(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kinship_token_id: TokenId,
        retriever: SentenceEntityRetriever,
    ) -> PossessorCandidate | None:
        arcs = document.store.dependency_arcs_by_sentence_id.get(sentence.id, [])
        for arc in arcs:
            if arc.head_token_id == kinship_token_id and arc.relation == DependencyRelation.NMOD:
                dependent_token = document.store.tokens.get(arc.dependent_token_id)
                if not dependent_token:
                    continue
                people = tuple(
                    e
                    for e in retriever.entities_for_sentence(sentence)
                    if e.kind == EntityKind.PERSON
                    and document.store.entity_candidates[e.id].grounding == GroundingKind.OBSERVED
                    and not self._is_organization_homograph_person(document, e.id)
                )
                for p in people:
                    if (
                        p.start_char <= dependent_token.span.start_char
                        and p.end_char >= dependent_token.span.end_char
                    ):
                        strength = self._morphological_possessor_signal(document, p.id)
                        return PossessorCandidate(
                            p.id,
                            (
                                SyntaxPossessorSignal(),
                                strength if strength is not None else MediumPossessorSignal(),
                            ),
                        )
        return None

    def _find_possessor_via_pronoun(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kinship_token_id: TokenId,
        retriever: SentenceEntityRetriever,
    ) -> PossessorCandidate | None:
        token_index = sentence.token_ids.index(kinship_token_id)
        start_idx = max(0, token_index - 3)
        has_pronoun = False
        for idx in range(start_idx, token_index):
            t = document.store.tokens[sentence.token_ids[idx]]
            if any(a.lemma in self._possessive_pronouns for a in t.morph):
                has_pronoun = True
                break

        if not has_pronoun:
            return None

        people = tuple(
            e
            for e in retriever.entities_for_sentence_window(sentence, before=3, after=0)
            if e.kind == EntityKind.PERSON
            and document.store.entity_candidates[e.id].grounding == GroundingKind.OBSERVED
            and not self._is_organization_homograph_person(document, e.id)
        )
        kinship_token = document.store.tokens[kinship_token_id]
        preceding = [p for p in people if p.end_char <= kinship_token.span.start_char]
        if preceding:
            return PossessorCandidate(
                max(preceding, key=lambda p: p.end_char).id,
                (StrongPossessorSignal(),),
            )
        return None

    def _find_possessor_via_adjacent_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kinship_token: Token,
        retriever: SentenceEntityRetriever,
    ) -> PossessorCandidate | None:
        people = tuple(
            e
            for e in retriever.entities_for_sentence(sentence)
            if e.kind == EntityKind.PERSON
            and document.store.entity_candidates[e.id].grounding == GroundingKind.OBSERVED
            and not self._is_organization_homograph_person(document, e.id)
        )
        following = [p for p in people if p.start_char >= kinship_token.span.end_char]
        if not following:
            return None
        nearest = min(following, key=lambda p: p.start_char)
        if nearest.start_char - kinship_token.span.end_char < 50:
            signal = self._morphological_possessor_signal(document, nearest.id)
            if signal is None:
                signal = WeakPossessorSignal()
            return PossessorCandidate(nearest.id, (signal,))
        return None

    def _morphological_possessor_signal(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> Signal | None:
        candidate = document.store.entity_candidates.get(entity_id)
        if candidate is None or not candidate.mention_ids:
            return None
        mention = document.store.mentions.get(candidate.mention_ids[0])
        if mention is None or not mention.token_ids:
            return None
        tokens = [document.store.tokens[token_id] for token_id in mention.token_ids]
        head_token = tokens[-1]
        cases = {analysis.case for analysis in head_token.morph if analysis.case is not None}
        if "gen" in cases:
            return StrongPossessorSignal()
        if cases and "nom" in cases:
            return NegativePossessorSignal()
        return WeakPossessorSignal()

    def _find_referent(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kinship_token: Token,
        possessor_id: EntityCandidateId,
        retriever: SentenceEntityRetriever,
    ) -> EntityCandidateId | None:
        people = tuple(
            e
            for e in retriever.entities_for_sentence_window(sentence, before=1, after=1)
            if e.kind == EntityKind.PERSON
            and document.store.entity_candidates[e.id].grounding == GroundingKind.OBSERVED
            and e.id != possessor_id
            and not self._is_organization_homograph_person(document, e.id)
        )
        if not people:
            return None

        valid_people = []
        for p in people:
            if p.start_char >= kinship_token.span.end_char:
                dist = p.start_char - kinship_token.span.end_char
            else:
                dist = kinship_token.span.start_char - p.end_char
            if dist <= 40:
                valid_people.append((p, dist))

        if not valid_people:
            return None

        return min(valid_people, key=lambda item: item[1])[0].id

    def _find_discourse_referent(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kinship_token: Token,
        possessor_id: EntityCandidateId,
        retriever: SentenceEntityRetriever,
    ) -> EntityCandidateId | None:
        # "Prywatnie jest żoną X" usually predicates the kinship noun of the
        # current discourse subject introduced in the immediately preceding text.
        if "być" not in {
            analysis.lemma
            for token_id in sentence.token_ids
            for analysis in document.store.tokens[token_id].morph
        }:
            return None
        people = tuple(
            e
            for e in retriever.entities_for_sentence_window(sentence, before=3, after=0)
            if e.kind == EntityKind.PERSON
            and e.id != possessor_id
            and document.store.entity_candidates[e.id].grounding == GroundingKind.OBSERVED
            and not self._is_organization_homograph_person(document, e.id)
        )
        preceding = [p for p in people if p.end_char <= kinship_token.span.start_char]
        if not preceding:
            return None
        return max(preceding, key=lambda person: person.end_char).id

    def _is_organization_homograph_person(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates.get(entity_id)
        if candidate is None or candidate.kind is not EntityKind.PERSON:
            return False
        person_head_lemmas = frozenset(
            mention.head_lemma
            for mention in document.store.candidate_mentions(entity_id)
            if mention.head_lemma is not None
        )
        if not person_head_lemmas:
            return False
        for organization in document.store.candidates_by_kind(EntityKind.ORGANIZATION):
            organization_head_lemmas = frozenset(
                mention.head_lemma
                for mention in document.store.candidate_mentions(organization.id)
                if mention.head_lemma is not None
            )
            if person_head_lemmas & organization_head_lemmas:
                return True
        return False
