from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pipeline.domain_types import ClauseID, ClusterID, EntityType
from pipeline.grammar_signals import (
    infer_time_scope_with_temporal_context,
)
from pipeline.models import ArticleDocument, ClauseUnit, ParsedWord, ResolvedEntity
from pipeline.nlp_rules import COMPENSATION_PATTERN, FUNDING_HINTS

if TYPE_CHECKING:
    from pipeline.extraction_context import ExtractionContext


class DependencyArgumentRole(StrEnum):
    SUBJECT = "subject"
    PASSIVE_SUBJECT = "passive_subject"
    OBJECT = "object"
    INDIRECT_OBJECT = "indirect_object"
    OBLIQUE = "oblique"
    ROLE = "role"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class DependencyArgument:
    role: DependencyArgumentRole
    token_index: int
    token_text: str
    token_lemma: str
    deprel: str
    cluster_id: ClusterID | None = None
    entity_type: EntityType | None = None


@dataclass(frozen=True, slots=True)
class DependencyMoneySpan:
    text: str
    normalized_text: str
    start_char: int
    end_char: int
    attached_role: DependencyArgumentRole | None = None


@dataclass(frozen=True, slots=True)
class TriggerArgumentFrame:
    clause_id: ClauseID
    trigger_token_index: int
    trigger_text: str
    trigger_lemma: str
    trigger_aspect: str | None
    time_scope_hint: str
    arguments: tuple[DependencyArgument, ...] = ()
    money_spans: tuple[DependencyMoneySpan, ...] = ()
    reporting_transfer: bool = False
    money_transfer_evidence: bool = False

    def clusters_for_role(
        self,
        context: ExtractionContext,
        role: DependencyArgumentRole,
        entity_types: set[EntityType] | None = None,
    ) -> list[ResolvedEntity]:
        clusters: list[ResolvedEntity] = []
        seen: set[ClusterID] = set()
        for argument in self.arguments:
            if argument.role != role or argument.cluster_id is None:
                continue
            if entity_types is not None and argument.entity_type not in entity_types:
                continue
            cluster = context.cluster_by_id(argument.cluster_id)
            if cluster is None or cluster.entity_id in seen:
                continue
            seen.add(cluster.entity_id)
            clusters.append(cluster)
        return clusters

    def first_cluster(
        self,
        context: ExtractionContext,
        roles: Iterable[DependencyArgumentRole],
        entity_types: set[EntityType],
    ) -> ResolvedEntity | None:
        for role in roles:
            clusters = self.clusters_for_role(context, role, entity_types)
            if clusters:
                return clusters[0]
        return None


class DependencyFrameBuilder:
    _REPORTING_RECIPIENT_LEMMAS = frozenset({"redakcja", "dziennikarz", "nam", "mi"})
    _REPORTING_OBJECT_LEMMAS = frozenset({"informacja", "komunikat", "stanowisko", "odpowiedź"})
    _FUNDING_NOUN_LEMMAS = frozenset({"dotacja", "dofinansowanie", "pieniądz", "środki"})

    def build(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
    ) -> dict[ClauseID, TriggerArgumentFrame]:
        frames: dict[ClauseID, TriggerArgumentFrame] = {}
        for clause in document.clause_units:
            parsed_words = document.parsed_sentences.get(clause.sentence_index, [])
            trigger = self._trigger_word(clause, parsed_words)
            if trigger is None:
                continue
            arguments = tuple(self._arguments_for_clause(clause, parsed_words, trigger, context))
            money_spans = tuple(self._money_spans(clause, parsed_words, trigger))
            reporting_transfer = self._is_reporting_transfer(trigger, arguments, parsed_words)
            money_transfer_evidence = self._has_money_transfer_evidence(
                trigger,
                arguments,
                parsed_words,
                money_spans,
            )
            frames[clause.clause_id] = TriggerArgumentFrame(
                clause_id=clause.clause_id,
                trigger_token_index=trigger.index,
                trigger_text=trigger.text,
                trigger_lemma=trigger.lemma,
                trigger_aspect=trigger.feats.get("Aspect"),
                time_scope_hint=infer_time_scope_with_temporal_context(
                    clause.text,
                    parsed_words,
                    temporal_expressions=document.temporal_expressions,
                    sentence_index=clause.sentence_index,
                    publication_date=document.publication_date,
                ).value,
                arguments=arguments,
                money_spans=money_spans,
                reporting_transfer=reporting_transfer,
                money_transfer_evidence=money_transfer_evidence,
            )
        return frames

    @staticmethod
    def _trigger_word(clause: ClauseUnit, parsed_words: list[ParsedWord]) -> ParsedWord | None:
        if not parsed_words:
            return None
        lemma = clause.trigger_head_lemma.casefold()
        text = clause.trigger_head_text.casefold()
        for word in parsed_words:
            if word.deprel == "root" and (
                word.lemma.casefold() == lemma or word.text.casefold() == text
            ):
                return word
        for word in parsed_words:
            if word.lemma.casefold() == lemma or word.text.casefold() == text:
                return word
        return next((word for word in parsed_words if word.deprel == "root"), parsed_words[0])

    def _arguments_for_clause(
        self,
        clause: ClauseUnit,
        parsed_words: list[ParsedWord],
        trigger: ParsedWord,
        context: ExtractionContext,
    ) -> list[DependencyArgument]:
        arguments: list[DependencyArgument] = []
        seen: set[tuple[DependencyArgumentRole, ClusterID | None, int]] = set()
        for word in parsed_words:
            role = self._argument_role(word, trigger, parsed_words)
            if role is None:
                continue
            cluster = self._cluster_for_word(clause, word, context)
            key = (role, cluster.entity_id if cluster else None, word.index)
            if key in seen:
                continue
            seen.add(key)
            arguments.append(
                DependencyArgument(
                    role=role,
                    token_index=word.index,
                    token_text=word.text,
                    token_lemma=word.lemma,
                    deprel=word.deprel,
                    cluster_id=cluster.entity_id if cluster else None,
                    entity_type=cluster.entity_type if cluster else None,
                )
            )
        return arguments

    def _argument_role(
        self,
        word: ParsedWord,
        trigger: ParsedWord,
        parsed_words: list[ParsedWord],
    ) -> DependencyArgumentRole | None:
        attached = word.head == trigger.index
        parent = self._word_by_index(parsed_words, word.head)
        attached_via_case = parent is not None and parent.head == trigger.index
        if not attached and not attached_via_case:
            return None
        deprel = word.deprel
        if deprel == "nsubj:pass":
            return DependencyArgumentRole.PASSIVE_SUBJECT
        if deprel == "nsubj":
            return DependencyArgumentRole.SUBJECT
        if deprel in {"obj", "ccomp", "xcomp"}:
            return DependencyArgumentRole.OBJECT
        if deprel == "iobj":
            return DependencyArgumentRole.INDIRECT_OBJECT
        if deprel == "obl" or (attached_via_case and parent is not None and parent.deprel == "obl"):
            return DependencyArgumentRole.OBLIQUE
        if deprel in {"appos", "cop"} or word.lemma.casefold() in {"prezes", "członek"}:
            return DependencyArgumentRole.ROLE
        return None

    @staticmethod
    def _word_by_index(parsed_words: list[ParsedWord], index: int) -> ParsedWord | None:
        return next((word for word in parsed_words if word.index == index), None)

    @staticmethod
    def _cluster_for_word(
        clause: ClauseUnit,
        word: ParsedWord,
        context: ExtractionContext,
    ) -> ResolvedEntity | None:
        absolute_start = clause.start_char + word.start
        absolute_end = clause.start_char + word.end
        candidates = [
            cluster
            for cluster in context.clusters_for_mentions(
                clause.cluster_mentions,
                {
                    EntityType.PERSON,
                    EntityType.ORGANIZATION,
                    EntityType.PUBLIC_INSTITUTION,
                    EntityType.POSITION,
                },
            )
            if any(
                mention.sentence_index == clause.sentence_index
                and mention.start_char <= absolute_start
                and mention.end_char >= absolute_end
                for mention in cluster.mentions
            )
        ]
        if candidates:
            return min(candidates, key=lambda cluster: len(cluster.canonical_name))
        return None

    def _money_spans(
        self,
        clause: ClauseUnit,
        parsed_words: list[ParsedWord],
        trigger: ParsedWord,
    ) -> list[DependencyMoneySpan]:
        spans: list[DependencyMoneySpan] = []
        seen_offsets: set[tuple[int, int]] = set()

        # 1. Syntactic discovery: find numeric arguments of the trigger
        for word in parsed_words:
            role = self._argument_role(word, trigger, parsed_words)
            if role is None:
                continue

            # If it's a number or contains digits, it might be an amount
            if word.upos == "NUM" or any(c.isdigit() for c in word.text):
                # Search for the full currency pattern starting near this word
                search_start = max(0, word.start - 10)
                search_end = min(len(clause.text), word.end + 20)

                for match in COMPENSATION_PATTERN.finditer(clause.text, search_start, search_end):
                    amount = match.group("amount")
                    offsets = (
                        clause.start_char + match.start("amount"),
                        clause.start_char + match.end("amount"),
                    )
                    if offsets in seen_offsets:
                        continue

                    spans.append(
                        DependencyMoneySpan(
                            text=amount,
                            normalized_text=amount.title(),
                            start_char=offsets[0],
                            end_char=offsets[1],
                            attached_role=role,
                        )
                    )
                    seen_offsets.add(offsets)

        # 2. Global fallback for the clause if no syntactic links found
        if not spans:
            for match in COMPENSATION_PATTERN.finditer(clause.text):
                amount = match.group("amount")
                offsets = (
                    clause.start_char + match.start("amount"),
                    clause.start_char + match.end("amount"),
                )
                if offsets in seen_offsets:
                    continue
                spans.append(
                    DependencyMoneySpan(
                        text=amount,
                        normalized_text=amount.title(),
                        start_char=offsets[0],
                        end_char=offsets[1],
                        attached_role=DependencyArgumentRole.OBJECT,
                    )
                )
                seen_offsets.add(offsets)
        return spans

    def _is_reporting_transfer(
        self,
        trigger: ParsedWord,
        arguments: tuple[DependencyArgument, ...],
        parsed_words: list[ParsedWord],
    ) -> bool:
        if trigger.lemma.casefold() != "przekazać":
            return False
        if any(word.lemma.casefold() in self._FUNDING_NOUN_LEMMAS for word in parsed_words):
            return False
        reporting_lemmas = self._REPORTING_RECIPIENT_LEMMAS | self._REPORTING_OBJECT_LEMMAS
        return any(argument.token_lemma.casefold() in reporting_lemmas for argument in arguments)

    def _has_money_transfer_evidence(
        self,
        trigger: ParsedWord,
        arguments: tuple[DependencyArgument, ...],
        parsed_words: list[ParsedWord],
        money_spans: tuple[DependencyMoneySpan, ...],
    ) -> bool:
        if trigger.lemma.casefold() not in FUNDING_HINTS:
            return False
        if money_spans:
            return True
        if any(word.lemma.casefold() in self._FUNDING_NOUN_LEMMAS for word in parsed_words):
            return True
        org_roles = {
            argument.role
            for argument in arguments
            if argument.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        }
        return DependencyArgumentRole.SUBJECT in org_roles and bool(
            org_roles
            & {
                DependencyArgumentRole.OBJECT,
                DependencyArgumentRole.INDIRECT_OBJECT,
                DependencyArgumentRole.OBLIQUE,
            }
        )
