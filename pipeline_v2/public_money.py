from __future__ import annotations

import re

from pipeline_v2.binding_emission import EntityBindingGroup, emit_entity_binding_groups
from pipeline_v2.candidates import (
    EntityCandidate,
)
from pipeline_v2.catalogues import POLITICAL_PARTY_NAMES
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter, EmittedEvent
from pipeline_v2.event_frames import EventFrameBuilder, FrameArgument, FrameArgumentRole
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
    ContractDocumentSignal,
    ContractorSignal,
    ControllerContextSignal,
    DirectPrepositionalAttachmentSignal,
    EntityKind,
    EventRole,
    FactKind,
    FunderSignal,
    FundingLemmaSignal,
    GrantTransactionSignal,
    GroundingKind,
    LocalObjectSignal,
    LocalPhraseFunderSignal,
    LocalPhraseRecipientSignal,
    LocalSubjectSignal,
    MentionKind,
    MicroAmountSignal,
    MoneyAmountSignal,
    PartyOrganizationSignal,
    PublicContractLemmaSignal,
    RecipientSignal,
    ServiceTransactionSignal,
    Signal,
    WeakSyntacticBindingSignal,
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
            "dostarczyć",
            "kupić",
        }
    )
    _service_transaction_lemmas = frozenset(
        {"reklama", "promocja", "obsługa", "usługa", "zlecenie"}
    )
    _contract_document_lemmas = frozenset({"umowa", "kontrakt", "faktura", "zamówienie"})
    _grant_transaction_lemmas = frozenset({"dotacja", "dofinansowanie", "grant"})
    _compensation_lemmas = frozenset(
        {
            "wynagrodzenie",
            "pensja",
            "zarobek",
            "zarobić",
            "zarabiać",
            "dostawać",
            "odprawa",
            "premia",
            "pobrać",
        }
    )
    _currency_lemmas = frozenset({"złoty", "pln"})
    _amount_scale_lemmas = frozenset({"tysiąc", "milion", "miliard"})
    _amount_modifier_lemmas = frozenset(
        {
            "blisko",
            "kilka",
            "kilkanaście",
            "kilkadziesiąt",
            "mniej",
            "niemal",
            "około",
            "ponad",
            "prawie",
        }
    )

    def name(self) -> str:
        return "public_money_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            amount_texts = self._amount_texts(document, sentence)
            if amount_texts:
                kinds = self._candidate_kinds(document, sentence)
                if kinds:
                    evidence = EvidenceSpan.from_sentence(
                        evidence_id=document.store.next_evidence_id(),
                        sentence=sentence,
                        source=self.producer_id,
                    )
                    document.store.add_evidence(evidence)
                    emitter = DomainEventEmitter(document, self.producer_id)
                    for kind, signals in kinds:
                        party_options = self._select_parties(
                            document,
                            sentence,
                            kind,
                        )

                        event_signals: list[Signal] = [
                            MoneyAmountSignal(amount=amount_texts[0]),
                            *signals,
                        ]

                        if kind in {
                            FactKind.COMPENSATION,
                            FactKind.PUBLIC_CONTRACT,
                            FactKind.FUNDING,
                        }:
                            micro = self._micro_amount_signal(amount_texts[0])
                            if micro is not None:
                                event_signals.append(micro)
                        event = emitter.event(
                            kind=kind,
                            trigger_evidence_id=evidence.id,
                            evidence_ids=(evidence.id,),
                            signals=tuple(event_signals),
                        )
                        self._add_amount_binding(
                            emitter,
                            event,
                            amount_texts[0],
                            evidence.id,
                        )
                        for (
                            source_entity_id,
                            source_signals,
                            target_entity_id,
                            target_signals,
                        ) in party_options:
                            self._add_party_bindings(
                                emitter=emitter,
                                event=event,
                                kind=kind,
                                source_entity_id=source_entity_id,
                                source_signals=source_signals,
                                target_entity_id=target_entity_id,
                                target_signals=target_signals,
                                evidence_id=evidence.id,
                            )
            self._add_new_money_candidates(document, sentence, amount_texts)
        return document

    def _add_amount_binding(
        self,
        emitter: DomainEventEmitter,
        event: EmittedEvent,
        amount_text: str,
        evidence_id: EvidenceId,
    ) -> None:
        emitter.bind_text(
            event=event,
            role=EventRole.AMOUNT,
            value=amount_text,
            evidence_ids=(evidence_id,),
        )

    def _add_party_bindings(
        self,
        *,
        emitter: DomainEventEmitter,
        event: EmittedEvent,
        kind: FactKind,
        source_entity_id: EntityCandidateId | None,
        source_signals: tuple[Signal, ...],
        target_entity_id: EntityCandidateId | None,
        target_signals: tuple[Signal, ...],
        evidence_id: EvidenceId,
    ) -> None:
        source_role = (
            EventRole.COUNTERPARTY if kind is FactKind.PUBLIC_CONTRACT else EventRole.FUNDER
        )
        target_role = (
            EventRole.CONTRACTOR if kind is FactKind.PUBLIC_CONTRACT else EventRole.RECIPIENT
        )
        groups = tuple(
            group
            for group in (
                (
                    EntityBindingGroup(
                        role=source_role,
                        bindings=((source_entity_id, source_signals),),
                    )
                    if source_entity_id is not None
                    else None
                ),
                (
                    EntityBindingGroup(
                        role=target_role,
                        bindings=((target_entity_id, target_signals),),
                    )
                    if target_entity_id is not None
                    else None
                ),
            )
            if group is not None
        )
        emit_entity_binding_groups(
            emitter=emitter,
            event=event,
            evidence_id=evidence_id,
            groups=groups,
        )

    _scale_pattern = re.compile(r"tys\.?|tysi[eę]cy|mln|milion", re.IGNORECASE)
    _numeric_pattern = re.compile(r"[\d\s\xa0]+(?:[,.]\d+)?")

    def _micro_amount_signal(self, amount_text: str) -> MicroAmountSignal | None:
        from pipeline_v2.types import MicroAmountSignal

        m = self._numeric_pattern.search(amount_text)
        if not m:
            return None
        raw_val = m.group(0).replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            val = float(raw_val)
        except ValueError:
            return None
        scale = 1.0
        s_match = self._scale_pattern.search(amount_text)
        if s_match:
            s_word = s_match.group(0).lower()
            if s_word.startswith("tys"):
                scale = 1000.0
            elif s_word.startswith("mln") or s_word.startswith("mil"):
                scale = 1000000.0
        final_val = val * scale
        if final_val < 5000.0:
            return MicroAmountSignal(amount=amount_text)
        return None

    def _amount_texts(self, document: ArticleDocument, sentence: Sentence) -> tuple[str, ...]:
        numeric_amounts = tuple(self._amount_pattern.findall(sentence.text))
        if numeric_amounts:
            return numeric_amounts
        textual_amount = self._textual_amount_text(document, sentence)
        if textual_amount is None:
            return ()
        return (textual_amount,)

    def _textual_amount_text(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> str | None:
        tokens = [document.store.tokens[token_id] for token_id in sentence.token_ids]
        for currency_index, token in enumerate(tokens):
            lemmas = {analysis.lemma for analysis in token.morph}
            if not (lemmas & self._currency_lemmas):
                continue
            start_index = currency_index - 1
            while start_index >= 0 and self._is_textual_amount_token(tokens[start_index]):
                start_index -= 1
            start_index += 1
            if start_index == currency_index:
                continue
            start_char = tokens[start_index].span.start_char
            end_char = token.span.end_char
            return document.cleaned_text[start_char:end_char].strip()
        return None

    def _is_textual_amount_token(self, token) -> bool:
        token_text = token.text.casefold()
        lemmas = {analysis.lemma for analysis in token.morph}
        poses = {analysis.pos for analysis in token.morph}
        if any(char.isdigit() for char in token_text):
            return True
        if poses & {"num"}:
            return True
        if lemmas & self._amount_scale_lemmas:
            return True
        if lemmas & self._amount_modifier_lemmas:
            return True
        return False

    def _has_service_exchange_preposition(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> bool:
        """Detect 'za [gerund]' — payment in exchange for a service."""
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        for i, token in enumerate(tokens):
            if not any(a.lemma == "za" for a in token.morph):
                continue
            for j in range(i + 1, min(i + 4, len(tokens))):
                if any(a.pos == "ger" for a in tokens[j].morph):
                    return True
        return False

    def _candidate_kinds(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[FactKind, tuple[Signal, ...]], ...]:
        lemmas = self._sentence_lemmas(document, sentence)
        has_funding = bool(self._funding_lemmas & lemmas)
        has_service_lexical = bool(self._service_transaction_lemmas & lemmas)
        has_service_gerund = has_funding and self._has_service_exchange_preposition(
            document, sentence
        )
        has_service_shape = has_service_lexical or has_service_gerund
        has_contract_document = bool(self._contract_document_lemmas & lemmas)
        has_grant_shape = bool(self._grant_transaction_lemmas & lemmas)
        has_contract = bool(self._contract_lemmas & lemmas) or has_service_shape
        has_compensation = bool(self._compensation_lemmas & lemmas)
        kinds = []
        if has_funding and not has_service_gerund:
            signals: list[Signal] = [
                FundingLemmaSignal(lemma=self._matched_detail(lemmas, self._funding_lemmas))
            ]
            if has_grant_shape:
                signals.append(GrantTransactionSignal())
            if has_service_lexical:
                signals.append(ServiceTransactionSignal())
            kinds.append(
                (
                    FactKind.FUNDING,
                    tuple(signals),
                )
            )
        if has_contract:
            contract_vocab = self._contract_lemmas | self._service_transaction_lemmas
            if has_funding and not (contract_vocab & lemmas):
                contract_vocab = contract_vocab | self._funding_lemmas
            signals = [
                PublicContractLemmaSignal(lemma=self._matched_detail(lemmas, contract_vocab))
            ]
            if has_service_shape:
                signals.append(ServiceTransactionSignal())
            if has_contract_document:
                signals.append(ContractDocumentSignal())
            if has_grant_shape:
                signals.append(GrantTransactionSignal())
            kinds.append(
                (
                    FactKind.PUBLIC_CONTRACT,
                    tuple(signals),
                )
            )
        if has_compensation:
            kinds.append(
                (
                    FactKind.COMPENSATION,
                    (
                        CompensationLemmaSignal(
                            lemma=self._matched_detail(lemmas, self._compensation_lemmas)
                        ),
                    ),
                )
            )
        return tuple(kinds)

    def _sentence_lemmas(self, document: ArticleDocument, sentence: Sentence) -> frozenset[str]:
        lemmas = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _matched_detail(self, lemmas: frozenset[str], vocabulary: frozenset[str]) -> str:
        return next(iter(sorted(lemmas & vocabulary)))

    def _preposition_before_entity(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_start_char: int,
    ) -> str | None:
        tokens = [document.store.tokens[tid] for tid in sentence.token_ids]
        ent_token_idx = None
        for idx, token in enumerate(tokens):
            if token.span.start_char >= entity_start_char:
                ent_token_idx = idx
                break

        if ent_token_idx is None or ent_token_idx == 0:
            return None

        preceding_tokens = tokens[max(0, ent_token_idx - 3) : ent_token_idx]
        for tok in reversed(preceding_tokens):
            lemma = (tok.preferred_lemma() or tok.text).casefold()
            if lemma in {"z", "od", "dla"}:
                return lemma
        return None

    def _build_signals_for_role(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entity_id: EntityCandidateId | None,
        entity_start_char: int | None,
        base_signals: tuple[Signal, ...],
        is_source_role: bool,
    ) -> tuple[Signal, ...]:
        if entity_id is None:
            return ()
        signals = list(base_signals)

        # Preposition check: "z/od" before an entity marks a funding source
        # or contract counterparty; "dla" marks a recipient/contractor target.
        # Entities in subject position (no preceding source/target prep) get a
        # positive boost when placed in the source role.
        if entity_start_char is not None:
            preceding_preposition = self._preposition_before_entity(
                document, sentence, entity_start_char
            )
            if is_source_role and preceding_preposition in {"z", "od"}:
                signals.append(DirectPrepositionalAttachmentSignal())
            elif not is_source_role and preceding_preposition == "dla":
                signals.append(DirectPrepositionalAttachmentSignal())
            elif (
                not is_source_role
                and preceding_preposition == "z"
                and self._has_contractor_signal(base_signals)
            ):
                signals.append(DirectPrepositionalAttachmentSignal())

        # Party-like organization check
        if self._is_party_like_organization(document, entity_id):
            signals.append(PartyOrganizationSignal())

        # Media-outlet entities are now suppressed in funding/contract/compensation
        # roles via the EntityContext↔RoleFiller constraint factor in inference;
        # the producer no longer emits a per-binding reporting-source signal.

        return tuple(signals)

    def _has_contractor_signal(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case ContractorSignal():
                    return True
                case _:
                    continue
        return False

    def _select_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kind: FactKind,
    ) -> tuple[
        tuple[
            EntityCandidateId | None,
            tuple[Signal, ...],
            EntityCandidateId | None,
            tuple[Signal, ...],
        ],
        ...,
    ]:
        retriever = SentenceEntityRetriever(document.store)
        entities = retriever.entities_for_sentence(sentence)
        if kind == FactKind.COMPENSATION:
            return self._select_compensation_parties(document, sentence, retriever, entities)
        organizations = tuple(
            entity for entity in entities if entity.kind == EntityKind.ORGANIZATION
        )
        people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)
        if kind == FactKind.PUBLIC_CONTRACT:
            return self._select_contract_parties(
                document,
                sentence,
                organizations,
                people,
                lemmas=self._sentence_lemmas(document, sentence),
            )
        if kind == FactKind.FUNDING:
            return self._select_funding_parties(
                document,
                sentence,
                organizations,
                lemmas=self._sentence_lemmas(document, sentence),
            )
        return ((None, (), None, ()),)

    def _select_contract_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        organizations: tuple[SentenceEntity, ...],
        people: tuple[SentenceEntity, ...],
        *,
        lemmas: frozenset[str] | None = None,
    ) -> tuple[
        tuple[
            EntityCandidateId | None,
            tuple[Signal, ...],
            EntityCandidateId | None,
            tuple[Signal, ...],
        ],
        ...,
    ]:
        combinations = []
        for counterparty in organizations:
            counterparty_sigs = self._build_signals_for_role(
                document,
                sentence,
                counterparty.id,
                counterparty.start_char,
                (ContractCounterpartySignal(),),
                is_source_role=True,
            )
            combinations.append((counterparty.id, counterparty_sigs, None, ()))
            for contractor in organizations:
                if contractor.id == counterparty.id:
                    continue
                contractor_base: tuple[Signal, ...] = (ContractorSignal(),)
                if self._preposition_before_entity(document, sentence, contractor.start_char) in {
                    "od",
                    "z",
                }:
                    contractor_base = (
                        ContractorSignal(),
                        DirectPrepositionalAttachmentSignal(),
                    )
                contractor_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    contractor.id,
                    contractor.start_char,
                    contractor_base,
                    is_source_role=False,
                )
                combinations.append(
                    (counterparty.id, counterparty_sigs, contractor.id, contractor_sigs)
                )
            for person, person_base in self._person_contract_recipients(document, sentence, people):
                person_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    person.id,
                    person.start_char,
                    person_base,
                    is_source_role=False,
                )
                combinations.append((counterparty.id, counterparty_sigs, person.id, person_sigs))
        if not organizations:
            for person, person_base in self._person_contract_recipients(document, sentence, people):
                target_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    person.id,
                    person.start_char,
                    person_base,
                    is_source_role=False,
                )
                combinations.append((None, (), person.id, target_sigs))
        if lemmas is not None and not organizations:
            inferred_counterparty_id = self._infer_source_organization(document, sentence)
            inferred_contractor_id = self._infer_recipient_organization(
                document, sentence, lemmas=lemmas
            )
            if inferred_counterparty_id is not None or inferred_contractor_id is not None:
                counterparty_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    inferred_counterparty_id,
                    None,
                    (LocalPhraseFunderSignal(),) if inferred_counterparty_id is not None else (),
                    is_source_role=True,
                )
                contractor_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    inferred_contractor_id,
                    None,
                    (LocalPhraseRecipientSignal(),) if inferred_contractor_id is not None else (),
                    is_source_role=False,
                )
                combinations.append(
                    (
                        inferred_counterparty_id,
                        counterparty_sigs,
                        inferred_contractor_id,
                        contractor_sigs,
                    )
                )
        return tuple(combinations) if combinations else ((None, (), None, ()),)

    def _person_contract_recipients(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        people: tuple[SentenceEntity, ...],
    ) -> tuple[tuple[SentenceEntity, tuple[Signal, ...]], ...]:
        recipients: list[tuple[SentenceEntity, tuple[Signal, ...]]] = []
        for person in people:
            signals = self._person_contract_binding_signals(document, sentence, person)
            recipients.append((person, signals))
        return tuple(recipients)

    def _person_contract_binding_signals(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        person: SentenceEntity,
    ) -> tuple[Signal, ...]:
        signals: list[Signal] = [ContractorSignal()]
        token_ids = sentence.token_ids
        if self._preposition_before_entity(document, sentence, person.start_char) == "dla":
            signals.append(DirectPrepositionalAttachmentSignal())
            return tuple(signals)

        recipient_action_index = self._first_token_index_with_lemmas(
            document,
            token_ids,
            self._recipient_action_lemmas,
        )
        if recipient_action_index is not None:
            action_token = document.store.tokens[token_ids[recipient_action_index]]
            if person.start_char <= action_token.span.start_char and self._entity_has_case(
                document,
                person.id,
                "nom",
            ):
                signals.append(DirectPrepositionalAttachmentSignal())
                return tuple(signals)

        contract_index = self._first_token_index_with_lemmas(
            document,
            token_ids,
            self._contract_lemmas,
        )
        if contract_index is not None:
            contract_token = document.store.tokens[token_ids[contract_index]]
            if abs(person.start_char - contract_token.span.start_char) <= 80:
                signals.append(DirectPrepositionalAttachmentSignal())
        return tuple(signals)

    def _entity_has_case(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
        expected_case: str,
    ) -> bool:
        for mention in document.store.candidate_mentions(entity_id):
            mention_has_case = True
            for token in document.store.tokens_for_mention(mention.id):
                if not any(analysis.case == expected_case for analysis in token.morph):
                    mention_has_case = False
                    break
            if mention_has_case:
                return True
        return False

    def _select_funding_parties(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        organizations: tuple[SentenceEntity, ...],
        *,
        lemmas: frozenset[str],
    ) -> tuple[
        tuple[
            EntityCandidateId | None,
            tuple[Signal, ...],
            EntityCandidateId | None,
            tuple[Signal, ...],
        ],
        ...,
    ]:
        combinations = []
        if len(organizations) >= 2:
            for org0 in organizations:
                for org1 in organizations:
                    if org0.id == org1.id:
                        continue
                    source_sigs = self._build_signals_for_role(
                        document,
                        sentence,
                        org0.id,
                        org0.start_char,
                        (FunderSignal(),),
                        is_source_role=True,
                    )
                    target_sigs = self._build_signals_for_role(
                        document,
                        sentence,
                        org1.id,
                        org1.start_char,
                        (RecipientSignal(),),
                        is_source_role=False,
                    )
                    combinations.append((org0.id, source_sigs, org1.id, target_sigs))
        elif len(organizations) == 1:
            org = organizations[0]
            if lemmas & self._recipient_action_lemmas:
                target_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    org.id,
                    org.start_char,
                    (RecipientSignal(),),
                    is_source_role=False,
                )
                combinations.append((None, (), org.id, target_sigs))
            else:
                source_sigs = self._build_signals_for_role(
                    document,
                    sentence,
                    org.id,
                    org.start_char,
                    (FunderSignal(),),
                    is_source_role=True,
                )
                combinations.append((org.id, source_sigs, None, ()))

        inferred_funder_id = self._infer_source_organization(document, sentence)
        inferred_recipient_id = self._infer_recipient_organization(
            document,
            sentence,
            lemmas=lemmas,
        )
        if inferred_funder_id is not None or inferred_recipient_id is not None:
            source_sigs = self._build_signals_for_role(
                document,
                sentence,
                inferred_funder_id,
                None,
                (LocalPhraseFunderSignal(),) if inferred_funder_id is not None else (),
                is_source_role=True,
            )
            target_sigs = self._build_signals_for_role(
                document,
                sentence,
                inferred_recipient_id,
                None,
                (LocalPhraseRecipientSignal(),) if inferred_recipient_id is not None else (),
                is_source_role=False,
            )
            combinations.append(
                (inferred_funder_id, source_sigs, inferred_recipient_id, target_sigs)
            )

        return tuple(combinations) if combinations else ((None, (), None, ()),)

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
        prep_index = self._first_token_index_with_lemmas(
            document,
            token_ids,
            self._source_preposition_lemmas,
        )
        if prep_index is None:
            return None
        head_index = self._first_token_index_with_lemmas(
            document,
            token_ids[prep_index + 1 :],
            self._organization_head_lemmas,
        )
        if head_index is None:
            return None
        head_index_in_sentence = prep_index + 1 + head_index
        end_index = head_index_in_sentence + 1
        while end_index < len(token_ids):
            tok = document.store.tokens[token_ids[end_index]]
            tok_lemmas = {analysis.lemma for analysis in tok.morph}
            if tok_lemmas & self._phrase_stop_lemmas:
                break
            end_index += 1
        return self._materialize_local_organization(
            document,
            sentence,
            start_index=head_index_in_sentence,
            end_index=end_index,
        )

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
        tokens = [document.store.tokens[tid] for tid in token_ids]
        start_char = tokens[0].span.start_char
        end_char = tokens[-1].span.end_char
        text = document.cleaned_text[start_char:end_char]
        for candidate_id, candidate in document.store.entity_candidates.items():
            if candidate.grounding != GroundingKind.INFERRED:
                continue
            for mention_id in candidate.mention_ids:
                mention = document.store.mentions.get(mention_id)
                mention_evidence = (
                    document.store.evidence.get(mention.evidence_id)
                    if mention is not None
                    else None
                )
                if (
                    mention_evidence is not None
                    and mention_evidence.span.start_char == start_char
                    and mention_evidence.span.end_char == end_char
                ):
                    return candidate_id
        evidence_id = document.store.next_evidence_id()
        evidence = EvidenceSpan(
            id=evidence_id,
            text=text,
            span=Span(start_char, end_char),
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        mention = Mention(
            id=mention_id,
            text=text,
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=sentence.id,
            token_ids=token_ids,
            head_lemma=self._head_lemma(tokens[0]),
        )
        document.store.add_mention(mention)
        candidate_id = document.store.next_entity_candidate_id()
        candidate = EntityCandidate(
            id=candidate_id,
            kind=EntityKind.ORGANIZATION,
            grounding=GroundingKind.INFERRED,
            canonical_hint=text,
            mention_ids=(mention_id,),
            source=self.producer_id,
        )
        document.store.add_entity_candidate(candidate)
        return candidate_id

    def _first_token_index_with_lemmas(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
        vocabulary: frozenset[str],
    ) -> int | None:
        for idx, token_id in enumerate(token_ids):
            token = document.store.tokens[token_id]
            token_lemmas = {analysis.lemma for analysis in token.morph}
            if token_lemmas & vocabulary:
                return idx
        return None

    def _head_lemma(self, token) -> str | None:
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
    ) -> tuple[
        tuple[
            EntityCandidateId | None,
            tuple[Signal, ...],
            EntityCandidateId | None,
            tuple[Signal, ...],
        ],
        ...,
    ]:
        """Emit plausible compensation source/recipient binding alternatives."""
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

        combinations = []
        selected_organizations = organizations if organizations else (None,)
        selected_people = people if people else (None,)
        for org in selected_organizations:
            for person in selected_people:
                source_base = (source_signal,) if org is not None else ()
                target_base = (target_signal,) if person is not None else ()
                if (
                    org is not None
                    and source_signal == WindowOrganizationSignal()
                    and self._is_controller_context(document, org.id)
                ):
                    source_base = source_base + (
                        ControllerContextSignal(
                            reason="window organization appears as controller/supervisor"
                        ),
                    )

                source_id = org.id if org else None
                source_start = org.start_char if org else None
                target_id = person.id if person else None
                target_start = person.start_char if person else None

                source_sigs = self._build_signals_for_role(
                    document, sentence, source_id, source_start, source_base, is_source_role=True
                )
                target_sigs = self._build_signals_for_role(
                    document, sentence, target_id, target_start, target_base, is_source_role=False
                )
                combinations.append((source_id, source_sigs, target_id, target_sigs))
        return tuple(combinations)

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
        party_names = POLITICAL_PARTY_NAMES
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

    def _add_new_money_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        amount_texts: tuple[str, ...],
    ) -> None:
        lemmas = self._sentence_lemmas(document, sentence)
        frame_builder = EventFrameBuilder(document.store)

        # 1. ASSET_DECLARATION
        asset_lemmas = frozenset(
            {"oświadczenie", "majątkowe", "majątek", "zadeklarować", "odnotować"}
        )
        if (lemmas & asset_lemmas) and amount_texts:
            frame = frame_builder.first_frame_for_lemmas(sentence, asset_lemmas)
            if frame is not None:
                people = frame.entities(EntityKind.PERSON)
                if people:
                    emitter, event, evidence_id = self._add_sentence_event(
                        document,
                        sentence,
                        FactKind.ASSET_DECLARATION,
                        signals=(MoneyAmountSignal(amount=amount_texts[0]),),
                    )
                    self._add_amount_binding(emitter, event, amount_texts[0], evidence_id)
                    for person in people:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.PERSON,
                            entity_id=person.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=(LocalSubjectSignal(),),
                        )
                    for other in frame.entities(
                        frozenset(
                            {
                                EntityKind.ORGANIZATION,
                                EntityKind.POLITICAL_PARTY,
                                EntityKind.ROLE,
                                EntityKind.LOCATION,
                            }
                        )
                    ):
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.CONTEXT,
                            entity_id=other.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=(),
                        )

        # 2. PARTY_DONATION
        donation_lemmas = frozenset(
            {"wpłata", "wpłacić", "darowizna", "przelew", "przelać", "donacja"}
        )
        if (lemmas & donation_lemmas) and amount_texts:
            frame = frame_builder.first_frame_for_lemmas(sentence, donation_lemmas)
            if frame is not None:
                funders = frame.entities(
                    EntityKind.PERSON,
                    before_trigger=True,
                    roles=frozenset({FrameArgumentRole.SUBJECT, FrameArgumentRole.OTHER}),
                )
                recipients = frame.entities(EntityKind.POLITICAL_PARTY, before_trigger=False)
                if funders or recipients:
                    emitter, event, evidence_id = self._add_sentence_event(
                        document,
                        sentence,
                        FactKind.PARTY_DONATION,
                        signals=(MoneyAmountSignal(amount=amount_texts[0]),),
                    )
                    self._add_amount_binding(emitter, event, amount_texts[0], evidence_id)
                    for funder in funders:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.FUNDER,
                            entity_id=funder.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=self._frame_argument_signals(
                                base=FunderSignal(),
                                argument=funder,
                                preferred_roles=frozenset({FrameArgumentRole.SUBJECT}),
                            ),
                        )
                    for recipient in recipients:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.RECIPIENT,
                            entity_id=recipient.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=(RecipientSignal(), DirectPrepositionalAttachmentSignal()),
                        )

        # 3. CORPORATE_OWNERSHIP
        ownership_lemmas = frozenset(
            {
                "udział",
                "akcja",
                "udziałowiec",
                "akcjonariusz",
                "właściciel",
                "posiadać",
                "udziały",
                "akcje",
                "wspólnik",
            }
        )
        if lemmas & ownership_lemmas:
            frame = frame_builder.first_frame_for_lemmas(sentence, ownership_lemmas)
            if frame is not None:
                subjects = frame.entities(
                    frozenset({EntityKind.PERSON, EntityKind.ORGANIZATION}),
                    before_trigger=True,
                ) or frame.entities(
                    frozenset({EntityKind.PERSON, EntityKind.ORGANIZATION}),
                    roles=frozenset({FrameArgumentRole.SUBJECT}),
                )
                objects = frame.entities(
                    EntityKind.ORGANIZATION,
                    before_trigger=False,
                    prepositions=frozenset({"w", "we"}),
                ) or frame.entities(EntityKind.ORGANIZATION, before_trigger=False)
                if subjects or objects:
                    emitter, event, evidence_id = self._add_sentence_event(
                        document,
                        sentence,
                        FactKind.CORPORATE_OWNERSHIP,
                        signals=(),
                    )
                    if amount_texts:
                        self._add_amount_binding(emitter, event, amount_texts[0], evidence_id)
                    subject_ids = {subject.entity.id for subject in subjects}
                    for subject in subjects:
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.SUBJECT,
                            entity_id=subject.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=self._frame_argument_signals(
                                base=LocalSubjectSignal(),
                                argument=subject,
                                preferred_roles=frozenset({FrameArgumentRole.SUBJECT}),
                            ),
                        )
                    for obj in objects:
                        if obj.entity.id in subject_ids:
                            continue
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.OBJECT,
                            entity_id=obj.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=(LocalObjectSignal(), DirectPrepositionalAttachmentSignal()),
                        )
                    for role in frame.entities(EntityKind.ROLE):
                        emitter.bind_entity(
                            event=event,
                            role=EventRole.ROLE,
                            entity_id=role.entity.id,
                            evidence_ids=(evidence_id,),
                            signals=(),
                        )

    def _frame_argument_signals(
        self,
        *,
        base: Signal,
        argument: FrameArgument,
        preferred_roles: frozenset[FrameArgumentRole],
    ) -> tuple[Signal, ...]:
        if argument.role in preferred_roles or argument.role is FrameArgumentRole.OTHER:
            return (base,)
        return (
            base,
            WeakSyntacticBindingSignal(reason=f"frame argument role is {argument.role.value}"),
        )

    def _add_sentence_event(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        kind: FactKind,
        *,
        signals: tuple[Signal, ...],
    ) -> tuple[DomainEventEmitter, EmittedEvent, EvidenceId]:
        evidence = EvidenceSpan.from_sentence(
            evidence_id=document.store.next_evidence_id(),
            sentence=sentence,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        emitter = DomainEventEmitter(document, self.producer_id)
        event = emitter.event(
            kind=kind,
            trigger_evidence_id=evidence.id,
            evidence_ids=(evidence.id,),
            signals=signals,
        )
        return emitter, event, evidence.id
