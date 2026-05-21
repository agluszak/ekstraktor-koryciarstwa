from __future__ import annotations

import re

from pipeline_v2.candidates import EntityCandidate, MoneyTransferFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import (
    EntityCandidateId,
    EvidenceId,
    ProducerId,
    TokenId,
)
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    CompensationLemmaSignal,
    CompensationRecipientSignal,
    CompensationSourceSignal,
    ContractCounterpartySignal,
    ContractorSignal,
    ControllerContextSignal,
    EntityKind,
    FactKind,
    FunderSignal,
    FundingLemmaSignal,
    GroundingKind,
    LocalPhraseFunderSignal,
    LocalPhraseRecipientSignal,
    MentionKind,
    MicroAmountSignal,
    MoneyAmountSignal,
    PartyOrganizationSignal,
    PublicContractLemmaSignal,
    RecipientSignal,
    Signal,
    WindowOrganizationSignal,
    WindowPersonSignal,
)


class PublicMoneyCandidateStage:
    producer_id = ProducerId("public_money_candidate_stage_v2")

    _amount_pattern = re.compile(
        r"\b\d+(?:[\s\xa0]\d+)*(?:[,.]\d+)?(?:\s*(?:tys\.?|tysi[eę]cy|mln|milion(?:y|ów)?))?\s*"
        r"(?:zł|złotych|pln)\b",
        re.IGNORECASE,
    )

    _funding_lemmas = frozenset(
        {
            "dotacja",
            "dofinansowanie",
            "grant",
            "przyznać",
            "otrzymać",
            "przekazać",
            "wypłacić",
        }
    )
    _recipient_action_lemmas = frozenset({"otrzymać", "dostać", "uzyskać"})
    _organization_head_lemmas = frozenset(
        {
            "fundacja",
            "fundusz",
            "instytucja",
            "pogotowie",
            "spółka",
            "stowarzyszenie",
            "szpital",
            "urząd",
        }
    )
    _source_preposition_lemmas = frozenset({"od", "z"})
    _phrase_stop_lemmas = frozenset({"a", "ale", "i", "na", "po", "przez", "w", "za"})
    _contract_lemmas = frozenset(
        {
            "umowa",
            "kontrakt",
            "zamówienie",
            "przetarg",
            "podpisać",
            "zlecić",
        }
    )
    _compensation_lemmas = frozenset(
        {
            "wynagrodzenie",
            "pensja",
            "zarobek",
            "zarabiać",
            "odprawa",
            "premia",
            "pobrać",
        }
    )

    def name(self) -> str:
        return "public_money_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            amount_texts = self._amount_texts(sentence)
            if not amount_texts:
                continue
            kinds = self._candidate_kinds(document, sentence)
            if not kinds:
                continue
            evidence = EvidenceSpan(
                id=document.store.next_evidence_id(),
                text=sentence.text,
                span=sentence.span,
                sentence_id=sentence.id,
                paragraph_index=sentence.paragraph_index,
                source=self.producer_id,
            )
            document.store.add_evidence(evidence)
            for kind, signals in kinds:
                for source_entity_id, target_entity_id, role_signals in self._select_parties(
                    document,
                    sentence,
                    kind,
                ):
                    extra_signals: list[Signal] = []
                    if kind == FactKind.COMPENSATION:
                        micro = self._micro_amount_signal(amount_texts[0])
                        if micro is not None:
                            extra_signals.append(micro)
                    document.store.add_fact_candidate(
                        MoneyTransferFactCandidate(
                            id=document.store.next_fact_candidate_id(),
                            kind=kind,
                            source_entity_id=source_entity_id,
                            target_entity_id=target_entity_id,
                            amount_text=amount_texts[0],
                            evidence_ids=(evidence.id,),
                            source=self.producer_id,
                            signals=(
                                MoneyAmountSignal(amount=amount_texts[0]),
                                *signals,
                                *role_signals,
                                *extra_signals,
                            ),
                        )
                    )
        return document

    _scale_pattern = re.compile(r"tys\.?|tysi[eę]cy|mln|milion", re.IGNORECASE)
    _numeric_pattern = re.compile(r"[\d\s\xa0]+(?:[,.]\d+)?")

    def _micro_amount_signal(self, amount_text: str) -> MicroAmountSignal | None:
        """Return a MicroAmountSignal when the amount is below 100 PLN and has no scale word.

        This covers citizen-cost statistics like "1,88 zł" that should not be
        treated as executive compensation.  Candidate emission is intentionally
        left unchanged; penalisation is the scorer's job.
        """
        if self._scale_pattern.search(amount_text):
            return None
        m = self._numeric_pattern.match(amount_text.strip())
        if m is None:
            return None
        raw = m.group(0).replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            return None
        if value < 100.0:
            return MicroAmountSignal(amount=amount_text.strip())
        return None

    def _amount_texts(self, sentence: Sentence) -> tuple[str, ...]:
        return tuple(match.group(0) for match in self._amount_pattern.finditer(sentence.text))

    def _candidate_kinds(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[FactKind, tuple[Signal, ...]], ...]:
        lemmas = self._sentence_lemmas(document, sentence)
        candidates: list[tuple[FactKind, tuple[Signal, ...]]] = []
        if lemmas & self._funding_lemmas:
            candidates.append(
                (
                    FactKind.FUNDING,
                    (
                        FundingLemmaSignal(
                            lemma=self._matched_detail(lemmas, self._funding_lemmas),
                        ),
                    ),
                )
            )
        if lemmas & self._contract_lemmas:
            candidates.append(
                (
                    FactKind.PUBLIC_CONTRACT,
                    (
                        PublicContractLemmaSignal(
                            lemma=self._matched_detail(lemmas, self._contract_lemmas),
                        ),
                    ),
                )
            )
        if lemmas & self._compensation_lemmas:
            candidates.append(
                (
                    FactKind.COMPENSATION,
                    (
                        CompensationLemmaSignal(
                            lemma=self._matched_detail(lemmas, self._compensation_lemmas),
                        ),
                    ),
                )
            )
        return tuple(candidates)

    def _sentence_lemmas(self, document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _matched_detail(self, lemmas: frozenset[str], vocabulary: frozenset[str]) -> str:
        return next(iter(sorted(lemmas & vocabulary)))

    def _select_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kind: FactKind,
    ) -> tuple[tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]], ...]:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        if kind == FactKind.COMPENSATION:
            return self._select_compensation_parties(document, sentence, retriever, entities)
        organizations = tuple(
            entity for entity in entities if entity.kind == EntityKind.ORGANIZATION
        )
        if kind == FactKind.PUBLIC_CONTRACT:
            res = self._select_contract_parties(organizations)
            return (res,) if res[2] else ((None, None, ()),)
        if kind == FactKind.FUNDING:
            res = self._select_funding_parties(
                document,
                sentence,
                organizations,
                lemmas=self._sentence_lemmas(document, sentence),
            )
            return (res,) if res[2] else ((None, None, ()),)
        return ((None, None, ()),)

    def _select_contract_parties(
        self,
        organizations: tuple[SentenceEntity, ...],
    ) -> tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]]:
        if len(organizations) >= 2:
            return (
                organizations[0].id,
                organizations[1].id,
                (
                    ContractCounterpartySignal(),
                    ContractorSignal(),
                ),
            )
        if len(organizations) == 1:
            return (
                organizations[0].id,
                None,
                (ContractCounterpartySignal(),),
            )
        return None, None, ()

    def _select_funding_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        organizations: tuple[SentenceEntity, ...],
        *,
        lemmas: frozenset[str],
    ) -> tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]]:
        if len(organizations) >= 2:
            return (
                organizations[0].id,
                organizations[1].id,
                (
                    FunderSignal(),
                    RecipientSignal(),
                ),
            )
        if len(organizations) == 1 and lemmas & self._recipient_action_lemmas:
            return (
                None,
                organizations[0].id,
                (RecipientSignal(),),
            )
        inferred_funder_id = self._infer_source_organization(document, sentence)
        inferred_recipient_id = self._infer_recipient_organization(
            document,
            sentence,
            lemmas=lemmas,
        )
        signals: list[Signal] = []
        if inferred_funder_id is not None:
            signals.append(LocalPhraseFunderSignal())
        if inferred_recipient_id is not None:
            signals.append(LocalPhraseRecipientSignal())
        if inferred_funder_id is not None or inferred_recipient_id is not None:
            return inferred_funder_id, inferred_recipient_id, tuple(signals)
        if len(organizations) == 1:
            return (
                organizations[0].id,
                None,
                (FunderSignal(),),
            )
        return None, None, ()

    def _infer_recipient_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        *,
        lemmas: frozenset[str],
    ) -> EntityCandidateId | None:
        if not (lemmas & self._recipient_action_lemmas):
            return None
        token_ids = sentence.token_ids
        verb_index = self._first_token_index_with_lemmas(
            document,
            token_ids,
            self._recipient_action_lemmas,
        )
        if verb_index is None:
            return None
        head_index = self._first_token_index_with_lemmas(
            document,
            token_ids[:verb_index],
            self._organization_head_lemmas,
        )
        if head_index is None:
            return None
        return self._materialize_local_organization(
            document,
            sentence,
            start_index=head_index,
            end_index=verb_index,
        )

    def _infer_source_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> EntityCandidateId | None:
        token_ids = sentence.token_ids
        for index, token_id in enumerate(token_ids):
            token = document.store.tokens[token_id]
            if not any(
                analysis.lemma in self._source_preposition_lemmas for analysis in token.morph
            ):
                continue
            if index + 1 >= len(token_ids):
                continue
            next_token = document.store.tokens[token_ids[index + 1]]
            if not any(
                analysis.lemma in self._organization_head_lemmas for analysis in next_token.morph
            ):
                continue
            end_index = len(token_ids)
            for stop_index in range(index + 2, len(token_ids)):
                stop_token = document.store.tokens[token_ids[stop_index]]
                if stop_token.text in {",", ".", ";", ":"}:
                    end_index = stop_index
                    break
                if any(analysis.lemma in self._phrase_stop_lemmas for analysis in stop_token.morph):
                    end_index = stop_index
                    break
            return self._materialize_local_organization(
                document,
                sentence,
                start_index=index + 1,
                end_index=end_index,
            )
        return None

    def _materialize_local_organization(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        *,
        start_index: int,
        end_index: int,
    ) -> EntityCandidateId | None:
        token_ids = sentence.token_ids[start_index:end_index]
        if not token_ids:
            return None
        span = Span(
            start_char=document.store.tokens[token_ids[0]].span.start_char,
            end_char=document.store.tokens[token_ids[-1]].span.end_char,
        )
        probe = EvidenceSpan(
            id=EvidenceId("probe"),
            text=document.cleaned_text[span.start_char : span.end_char],
            span=span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        for candidate_id in document.store.candidate_ids_with_evidence_overlapping_span(probe):
            candidate = document.store.entity_candidates[candidate_id]
            if candidate.kind == EntityKind.ORGANIZATION:
                return candidate_id
        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=document.cleaned_text[span.start_char : span.end_char],
            span=span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        mention = Mention(
            id=mention_id,
            text=evidence.text,
            kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
            evidence_id=evidence.id,
            sentence_id=sentence.id,
            token_ids=token_ids,
            head_lemma=self._head_lemma(document, token_ids),
        )
        document.store.add_mention(mention)
        return document.store.add_entity_candidate(
            EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=EntityKind.ORGANIZATION,
                mention_ids=(mention_id,),
                canonical_hint=evidence.text,
                grounding=GroundingKind.INFERRED,
                source=self.producer_id,
            )
        )

    def _first_token_index_with_lemmas(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
        lemmas: frozenset[str],
    ) -> int | None:
        for index, token_id in enumerate(token_ids):
            token = document.store.tokens[token_id]
            if any(analysis.lemma in lemmas for analysis in token.morph):
                return index
        return None

    def _head_lemma(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
    ) -> str | None:
        if not token_ids:
            return None
        token = document.store.tokens[token_ids[0]]
        for analysis in token.morph:
            if analysis.pos == "subst":
                return analysis.lemma
        return token.morph[0].lemma if token.morph else None

    def _select_compensation_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        retriever: SentenceEntityRetriever,
        entities: tuple[SentenceEntity, ...],
    ) -> tuple[tuple[EntityCandidateId | None, EntityCandidateId | None, tuple[Signal, ...]], ...]:
        """Select plausible compensation source/recipient bindings.

        This intentionally avoids a full person × organization product. It keeps
        one recipient candidate and emits source alternatives only when the
        source itself is ambiguous.
        """
        organizations = tuple(
            entity for entity in entities if entity.kind == EntityKind.ORGANIZATION
        )
        people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)

        source_signal: Signal
        target_signal: Signal
        if not organizations:
            window = retriever.entities_for_sentence_window(sentence, before=1, after=0)
            organizations = tuple(
                entity for entity in window if entity.kind == EntityKind.ORGANIZATION
            )
            source_signal = WindowOrganizationSignal()
        else:
            source_signal = CompensationSourceSignal()

        if not people:
            window = retriever.entities_for_sentence_window(sentence, before=1, after=0)
            people = tuple(entity for entity in window if entity.kind == EntityKind.PERSON)
            target_signal = WindowPersonSignal()
        else:
            target_signal = CompensationRecipientSignal()

        person = self._nearest_entity(people, sentence.span.start_char)
        combinations = []
        selected_organizations = organizations if organizations else (None,)
        for org in selected_organizations:
            signals: list[Signal] = []
            if org is not None:
                signals.append(source_signal)
                if self._is_party_like_organization(document, org.id):
                    signals.append(PartyOrganizationSignal())
                if source_signal == WindowOrganizationSignal() and self._is_controller_context(
                    document,
                    org.id,
                ):
                    signals.append(
                        ControllerContextSignal(
                            reason="window organization appears as controller/supervisor"
                        )
                    )
            if person is not None:
                signals.append(target_signal)
            combinations.append(
                (org.id if org else None, person.id if person else None, tuple(signals))
            )
        return tuple(combinations) if combinations else ((None, None, ()),)

    @staticmethod
    def _nearest_entity(
        entities: tuple[SentenceEntity, ...],
        anchor_char: int,
    ) -> SentenceEntity | None:
        if not entities:
            return None
        return min(entities, key=lambda entity: abs(entity.start_char - anchor_char))

    def _is_controller_context(
        self,
        document: ArticleDocument,
        candidate_id: EntityCandidateId,
    ) -> bool:
        candidate = document.store.entity_candidates[candidate_id]
        canonical_hint = (candidate.canonical_hint or "").casefold()
        if any(
            word in canonical_hint
            for word in ("ministerstwo", "ministerstwu", "resort", "urząd nadzorujący")
        ):
            return True
        return False

    def _is_party_like_organization(
        self, document: ArticleDocument, candidate_id: EntityCandidateId
    ) -> bool:
        party_names = GovernanceCandidateStage._party_like_organization_names
        candidate = document.store.entity_candidates[candidate_id]
        canonical_hint = (candidate.canonical_hint or "").casefold()

        # 1. Exact match in the set of party-like organization names
        if canonical_hint in party_names:
            return True

        # 2. Check whole-word overlap with known party-like organization names.
        hint_words = set(canonical_hint.split())
        for party_name in party_names:
            party_words = set(party_name.split())
            intersect = hint_words & party_words
            intersect = {w for w in intersect if len(w) > 2 and w not in {"dla", "oraz", "pod"}}
            if intersect:
                return True

        # 3. Check if it overlaps with any political party candidate in the document
        organization_evidence = tuple(document.store.evidence_for_entity(candidate_id))
        for party_candidate in document.store.candidates_by_kind(EntityKind.POLITICAL_PARTY):
            for party_evidence in document.store.evidence_for_entity(party_candidate.id):
                for organization_span in organization_evidence:
                    if organization_span.sentence_id != party_evidence.sentence_id:
                        continue
                    if organization_span.span.end_char <= party_evidence.span.start_char:
                        continue
                    if party_evidence.span.end_char <= organization_span.span.start_char:
                        continue
                    return True

        return False
