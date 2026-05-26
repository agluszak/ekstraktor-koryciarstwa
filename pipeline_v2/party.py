from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.event_frames import EventFrameBuilder, FrameArgumentRole
from pipeline_v2.ids import (
    EntityCandidateId,
    ProducerId,
    TokenId,
)
from pipeline_v2.nlp import EvidenceSpan, MentionFactory, MorphologyAdapter, Sentence, Span
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    CandidacyContextSignal,
    DirectPrepositionalAttachmentSignal,
    EmbeddedInOrganizationNameSignal,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    MentionKind,
    PartyAliasMatchSignal,
    PartyMembershipStatus,
    PartyMembershipStatusSignal,
    PartyProfileLemmaSignal,
    Signal,
)


@dataclass(frozen=True, slots=True)
class PartyAlias:
    alias: str
    canonical_name: str
    case_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class LemmaPartyAlias:
    alias: PartyAlias
    lemma_sequence: tuple[str, ...]


class PartyCandidateStage:
    producer_id = ProducerId("party_candidate_stage_v2")

    _aliases = tuple(
        sorted(
            (
                PartyAlias("PiS", "Prawo i Sprawiedliwość", case_sensitive=True),
                PartyAlias("Prawo i Sprawiedliwość", "Prawo i Sprawiedliwość"),
                PartyAlias("PO", "Platforma Obywatelska", case_sensitive=True),
                PartyAlias("Platforma Obywatelska", "Platforma Obywatelska"),
                PartyAlias("KO", "Koalicja Obywatelska", case_sensitive=True),
                PartyAlias("Koalicja Obywatelska", "Koalicja Obywatelska"),
                PartyAlias("PSL", "Polskie Stronnictwo Ludowe", case_sensitive=True),
                PartyAlias("Polskie Stronnictwo Ludowe", "Polskie Stronnictwo Ludowe"),
                PartyAlias("Lewica", "Lewica"),
                PartyAlias("Lewicy", "Lewica"),
                PartyAlias("Nowa Lewica", "Nowa Lewica"),
                PartyAlias("Polska 2050", "Polska 2050"),
                PartyAlias("Razem", "Razem"),
                PartyAlias("SLD", "Sojusz Lewicy Demokratycznej", case_sensitive=True),
                PartyAlias("Sojusz Lewicy Demokratycznej", "Sojusz Lewicy Demokratycznej"),
                PartyAlias("TD", "Trzecia Droga", case_sensitive=True),
                PartyAlias("Trzecia Droga", "Trzecia Droga"),
            ),
            key=lambda item: len(item.alias),
            reverse=True,
        )
    )
    _profile_lemmas = frozenset(
        {
            "działacz",
            "polityk",
            "lider",
            "członek",
            "radny",
            "poseł",
            "posłanka",
            "szef",
            "przewodniczący",
            "wódz",
            "kierownik",
            "sekretarz",
            "współzałożyciel",
        }
    )
    _support_lemmas = frozenset(
        {
            "kandydat",
            "kandydatka",
            "kandydować",
            "popierać",
            "rekomendacja",
            "rekomendować",
            "wspierać",
        }
    )
    _organization_continuation_lemmas = frozenset(
        {
            "fundacja",
            "stowarzyszenie",
            "spółka",
            "instytut",
        }
    )

    def __init__(self, morphology: MorphologyAdapter) -> None:
        self.morphology = morphology
        self.mention_factory = MentionFactory(morphology)
        self.lemma_aliases = self._lemma_aliases()

    def name(self) -> str:
        return "party_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            for match in self._party_matches(document, sentence):
                party_id = self._add_party_candidate(document, sentence, match)
                self._add_relation_candidates(document, sentence, party_id, match)
            self._add_candidacy_candidates(document, sentence)
        return document

    def _party_matches(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[PartyAliasMatch, ...]:
        matches: list[PartyAliasMatch] = []
        for alias in self._surface_aliases():
            flags = 0 if alias.case_sensitive else re.IGNORECASE
            pattern = re.compile(rf"(?<!\w){re.escape(alias.alias)}(?!\w)", flags)
            for match in pattern.finditer(sentence.text):
                start_char = sentence.span.start_char + match.start()
                end_char = sentence.span.start_char + match.end()
                is_embedded = self._is_embedded_in_organization_name(document, sentence, end_char)
                matches.append(
                    PartyAliasMatch(
                        alias=alias,
                        span=Span(start_char, end_char),
                        text=document.cleaned_text[start_char:end_char],
                        is_embedded=is_embedded,
                    )
                )
        for alias in self.lemma_aliases:
            matches.extend(self._lemma_alias_matches(document, sentence, alias))
        return tuple(self._deduplicate_matches(matches))

    def _add_party_candidate(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        match: "PartyAliasMatch",
    ) -> EntityCandidateId:
        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=match.text,
            span=match.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)
        mention_id = document.store.next_mention_id()
        document.store.add_mention(
            self.mention_factory.build_mention(
                mention_id=mention_id,
                text=match.text,
                kind=MentionKind.NER,
                evidence_id=evidence.id,
                sentence_id=sentence.id,
                token_ids=document.store.token_ids_for_span(
                    sentence_id=sentence.id,
                    span=evidence,
                ),
            )
        )
        return document.store.add_entity_candidate(
            EntityCandidate(
                id=document.store.next_entity_candidate_id(),
                kind=EntityKind.POLITICAL_PARTY,
                mention_ids=(mention_id,),
                canonical_hint=match.alias.canonical_name,
                grounding=GroundingKind.OBSERVED,
                source=self.producer_id,
            )
        )

    def _add_relation_candidates(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        party_id: EntityCandidateId,
        match: "PartyAliasMatch",
    ) -> None:
        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=sentence.text,
            span=sentence.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        entities = SentenceEntityRetriever(document.store).entities_for_sentence(sentence)
        person = self._direct_affiliation_person(document, sentence, entities, match)
        if person is not None:
            document.store.add_evidence(evidence)
            status = (
                PartyMembershipStatus.FORMER
                if self._has_former_context(
                    document=document,
                    sentence=sentence,
                    person=person,
                    match=match,
                )
                else PartyMembershipStatus.UNKNOWN
            )
            event = EventCandidate(
                id=document.store.next_event_candidate_id(),
                kind=FactKind.PARTY_MEMBERSHIP,
                trigger_evidence_id=evidence.id,
                evidence_ids=(evidence.id,),
                source=self.producer_id,
                signals=(
                    *self._party_membership_signals(document, sentence, match),
                    PartyMembershipStatusSignal(status=status),
                ),
            )
            document.store.add_event_candidate(event)
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.SUBJECT,
                    filler=EntityFiller(person.id),
                    evidence_ids=(evidence.id,),
                )
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.OBJECT,
                    filler=EntityFiller(party_id),
                    evidence_ids=(evidence.id,),
                )
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.STATUS,
                    filler=TextFiller(status.value),
                    evidence_ids=(evidence.id,),
                    signals=(PartyMembershipStatusSignal(status=status),),
                )
            )
            return

        if self._has_support_context(document, sentence, match):
            people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)
            supported = self._nearest_person(people, match.span.start_char)
            if supported is None:
                return

            signals: list[Signal] = [PartyAliasMatchSignal(), CandidacyContextSignal()]
            if match.is_embedded:
                signals.append(EmbeddedInOrganizationNameSignal())

            document.store.add_evidence(evidence)
            event = EventCandidate(
                id=document.store.next_event_candidate_id(),
                kind=FactKind.POLITICAL_SUPPORT,
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
                    filler=EntityFiller(party_id),
                    evidence_ids=(evidence.id,),
                )
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.OBJECT,
                    filler=EntityFiller(supported.id),
                    evidence_ids=(evidence.id,),
                )
            )

    def _direct_affiliation_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        entities: tuple[SentenceEntity, ...],
        match: "PartyAliasMatch",
    ) -> SentenceEntity | None:
        people = tuple(entity for entity in entities if entity.kind == EntityKind.PERSON)
        if self._has_support_context(document, sentence, match):
            return None
        previous_person = self._nearest_previous_person(people, match.span.start_char)
        if previous_person is not None:
            token_ids = self._tokens_between(
                document,
                sentence,
                previous_person.end_char,
                match.span.start_char,
            )
            if len(token_ids) <= 3:
                between = document.cleaned_text[previous_person.end_char : match.span.start_char]
                if re.search(r"\bz\s*$", between.casefold()):
                    return previous_person
        if self._has_profile_context(document, sentence, match):
            p = self._attached_profile_person(document, sentence, people, match)
            if p is not None:
                return p
        following_person = self._nearest_following_person(people, match.span.end_char)
        if following_person is not None:
            token_ids = self._tokens_between(
                document,
                sentence,
                match.span.end_char,
                following_person.start_char,
            )
            if len(token_ids) <= 3 and not any(
                document.store.tokens[token_id].text in {",", ".", ";", ":"}
                for token_id in token_ids
            ):
                return following_person
        return None

    def _attached_profile_person(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        people: tuple[SentenceEntity, ...],
        match: "PartyAliasMatch",
    ) -> SentenceEntity | None:
        following_people = tuple(
            entity for entity in people if entity.start_char >= match.span.end_char
        )
        if following_people:
            person = min(following_people, key=lambda entity: entity.start_char)
            token_ids = self._tokens_between(
                document,
                sentence,
                match.span.end_char,
                person.start_char,
            )
            if len(token_ids) > 5:
                return None
            if any(
                document.store.tokens[token_id].text in {",", ".", ";", ":"}
                for token_id in token_ids
            ):
                return None
            if any(
                document.store.tokens[token_id].text.casefold() in {"i", "oraz"}
                for token_id in token_ids
            ):
                return None
            return person
        if not following_people:
            previous_person = self._nearest_previous_person(people, match.span.start_char)
            if previous_person is None:
                return None
            token_ids = self._tokens_between(
                document,
                sentence,
                previous_person.end_char,
                match.span.start_char,
            )
            if not token_ids:
                return None
            if not any(document.store.tokens[token_id].text == "," for token_id in token_ids):
                return None
            return previous_person
        return None

    def _party_membership_signals(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        match: "PartyAliasMatch",
    ) -> tuple[Signal, ...]:
        signals: list[Signal] = [PartyAliasMatchSignal()]
        if self._has_profile_context(document, sentence, match):
            signals.append(PartyProfileLemmaSignal(lemma=match.alias.alias))
        else:
            signals.append(DirectPrepositionalAttachmentSignal())

        if match.is_embedded:
            signals.append(EmbeddedInOrganizationNameSignal())

        return tuple(signals)

    def _has_profile_context(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        match: "PartyAliasMatch",
    ) -> bool:
        token_ids = self._nearby_token_ids(
            document,
            sentence,
            match.span.start_char,
            before=3,
            after=5,
        )
        return self._tokens_contain_lemmas(document, token_ids, self._profile_lemmas)

    def _has_support_context(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        match: "PartyAliasMatch",
    ) -> bool:
        token_ids = self._nearby_token_ids(
            document,
            sentence,
            match.span.start_char,
            before=3,
            after=3,
        )
        return self._tokens_contain_lemmas(document, token_ids, self._support_lemmas)

    def _is_embedded_in_organization_name(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        end_char: int,
    ) -> bool:
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            if token.span.start_char <= end_char:
                continue
            return any(
                analysis.lemma in self._organization_continuation_lemmas for analysis in token.morph
            )
        return False

    def _nearby_token_ids(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        char_position: int,
        *,
        before: int,
        after: int,
    ) -> tuple[TokenId, ...]:
        token_ids = sentence.token_ids
        match_indexes = [
            index
            for index, token_id in enumerate(token_ids)
            if document.store.tokens[token_id].span.start_char
            <= char_position
            < document.store.tokens[token_id].span.end_char
        ]
        if not match_indexes:
            return ()
        index = match_indexes[0]
        return token_ids[max(0, index - before) : index + after + 1]

    def _tokens_contain_lemmas(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
        lemmas: frozenset[str],
    ) -> bool:
        for token_id in token_ids:
            token = document.store.tokens[token_id]
            if any(analysis.lemma in lemmas for analysis in token.morph):
                return True
        return False

    def _tokens_between(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        start_char: int,
        end_char: int,
    ) -> tuple[TokenId, ...]:
        return tuple(
            token_id
            for token_id in sentence.token_ids
            if start_char <= document.store.tokens[token_id].span.start_char < end_char
        )

    def _has_following_person(
        self,
        entities: tuple[SentenceEntity, ...],
        match: "PartyAliasMatch",
    ) -> bool:
        return any(
            entity.kind == EntityKind.PERSON and entity.start_char >= match.span.end_char
            for entity in entities
        )

    def _nearest_person(
        self,
        people: tuple[SentenceEntity, ...],
        char_position: int,
    ) -> SentenceEntity | None:
        if not people:
            return None
        return min(people, key=lambda entity: abs(entity.start_char - char_position))

    def _nearest_previous_person(
        self,
        people: tuple[SentenceEntity, ...],
        char_position: int,
    ) -> SentenceEntity | None:
        previous = tuple(entity for entity in people if entity.start_char < char_position)
        if not previous:
            return None
        return max(previous, key=lambda entity: entity.start_char)

    def _nearest_following_person(
        self,
        people: tuple[SentenceEntity, ...],
        char_position: int,
    ) -> SentenceEntity | None:
        following = tuple(entity for entity in people if entity.start_char >= char_position)
        if not following:
            return None
        return min(following, key=lambda entity: entity.start_char)

    def _deduplicate_matches(
        self,
        matches: list["PartyAliasMatch"],
    ) -> tuple["PartyAliasMatch", ...]:
        by_span: dict[tuple[int, int], PartyAliasMatch] = {}
        for match in matches:
            key = (match.span.start_char, match.span.end_char)
            if key not in by_span:
                by_span[key] = match
        return tuple(sorted(by_span.values(), key=lambda item: item.span.start_char))

    def _surface_aliases(self) -> tuple[PartyAlias, ...]:
        return tuple(alias for alias in self._aliases if " " not in alias.alias)

    def _lemma_aliases(self) -> tuple[LemmaPartyAlias, ...]:
        aliases: list[LemmaPartyAlias] = []
        for alias in self._aliases:
            if " " not in alias.alias:
                continue
            lemmas: list[str] = []
            for token in self.morphology.analyze_text(alias.alias):
                lemma = self._preferred_token_lemma(token.analyses)
                if lemma is not None:
                    lemmas.append(lemma)
            lemma_sequence = tuple(lemmas)
            if lemma_sequence:
                aliases.append(LemmaPartyAlias(alias=alias, lemma_sequence=lemma_sequence))
        return tuple(aliases)

    def _lemma_alias_matches(
        self,
        document: ArticleDocument,
        sentence: Sentence,
        alias: LemmaPartyAlias,
    ) -> tuple["PartyAliasMatch", ...]:
        token_ids = sentence.token_ids
        if len(token_ids) < len(alias.lemma_sequence):
            return ()
        matches: list[PartyAliasMatch] = []
        for start_index in range(len(token_ids) - len(alias.lemma_sequence) + 1):
            window = token_ids[start_index : start_index + len(alias.lemma_sequence)]
            window_lemmas = tuple(
                self._preferred_token_lemma(document.store.tokens[token_id].morph)
                for token_id in window
            )
            if window_lemmas != alias.lemma_sequence:
                continue
            start_char = document.store.tokens[window[0]].span.start_char
            end_char = document.store.tokens[window[-1]].span.end_char
            is_embedded = self._is_embedded_in_organization_name(document, sentence, end_char)
            matches.append(
                PartyAliasMatch(
                    alias=alias.alias,
                    span=Span(start_char, end_char),
                    text=document.cleaned_text[start_char:end_char],
                    is_embedded=is_embedded,
                )
            )
        return tuple(matches)

    @staticmethod
    def _preferred_token_lemma(analyses: tuple[object, ...]) -> str | None:
        for analysis in analyses:
            lemma = getattr(analysis, "lemma", None)
            pos = getattr(analysis, "pos", None)
            if pos == "subst" and lemma is not None:
                return lemma
        if analyses:
            return getattr(analyses[0], "lemma", None)
        return None

    def _has_former_context(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        person: SentenceEntity,
        match: "PartyAliasMatch",
    ) -> bool:
        former_lemmas = frozenset({"były", "dawny", "wcześniej", "niegdyś", "ex-"})
        start_char = max(
            sentence.span.start_char,
            min(person.start_char, match.span.start_char) - 30,
        )
        end_char = max(person.end_char, match.span.end_char)
        token_ids = self._token_ids_in_span(
            document=document,
            sentence=sentence,
            start_char=start_char,
            end_char=end_char,
        )
        if self._tokens_contain_lemmas(document, token_ids, former_lemmas):
            return True
        for token_id in token_ids:
            token = document.store.tokens[token_id]
            token_text_lower = token.text.lower()
            if token_text_lower in {"był", "była", "było", "byli", "były"}:
                return True
            for analysis in token.morph:
                if analysis.lemma == "być" and analysis.tag and "praet" in analysis.tag:
                    return True
        return False

    def _token_ids_in_span(
        self,
        *,
        document: ArticleDocument,
        sentence: Sentence,
        start_char: int,
        end_char: int,
    ) -> tuple[TokenId, ...]:
        return tuple(
            token_id
            for token_id in sentence.token_ids
            if start_char <= document.store.tokens[token_id].span.start_char < end_char
        )

    def _add_candidacy_candidates(self, document: ArticleDocument, sentence: Sentence) -> None:
        trigger_lemmas = frozenset({"kandydat", "kandydatka", "kandydować", "startować"})
        frame = EventFrameBuilder(document.store).first_frame_for_lemmas(sentence, trigger_lemmas)
        if frame is None:
            return

        person = frame.nearest(
            EntityKind.PERSON,
            roles=frozenset(
                {
                    FrameArgumentRole.SUBJECT,
                    FrameArgumentRole.APPOSITION,
                    FrameArgumentRole.OTHER,
                }
            ),
        )
        if person is None:
            return

        evidence = EvidenceSpan(
            id=document.store.next_evidence_id(),
            text=sentence.text,
            span=sentence.span,
            sentence_id=sentence.id,
            paragraph_index=sentence.paragraph_index,
            source=self.producer_id,
        )
        document.store.add_evidence(evidence)

        event = EventCandidate(
            id=document.store.next_event_candidate_id(),
            kind=FactKind.ELECTION_CANDIDACY,
            trigger_evidence_id=evidence.id,
            evidence_ids=(evidence.id,),
            source=self.producer_id,
            signals=(CandidacyContextSignal(),),
        )
        document.store.add_event_candidate(event)

        person_signal = PartyProfileLemmaSignal(
            lemma=frame.trigger.preferred_lemma() or frame.trigger.text
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=EventRole.PERSON,
                filler=EntityFiller(person.entity.id),
                evidence_ids=(evidence.id,),
                signals=(person_signal,),
            )
        )
        for role in frame.entities(EntityKind.ROLE):
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.ROLE,
                    filler=EntityFiller(role.entity.id),
                    evidence_ids=(evidence.id,),
                )
            )
        for organization in frame.entities(
            frozenset({EntityKind.ORGANIZATION, EntityKind.POLITICAL_PARTY}),
            before_trigger=False,
            prepositions=frozenset({"z", "do", "w", "na"}),
        ):
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.ORGANIZATION,
                    filler=EntityFiller(organization.entity.id),
                    evidence_ids=(evidence.id,),
                    signals=(DirectPrepositionalAttachmentSignal(),),
                )
            )


@dataclass(frozen=True, slots=True)
class PartyAliasMatch:
    alias: PartyAlias
    span: Span
    text: str
    is_embedded: bool = False
