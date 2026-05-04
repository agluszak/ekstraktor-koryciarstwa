from __future__ import annotations

import re
from collections.abc import Iterable

from pipeline.config import PipelineConfig
from pipeline.domain_types import EntityID, EntityType, FactType, TimeScope
from pipeline.models import ArticleDocument, Entity, EvidenceSpan, Fact, SentenceFragment
from pipeline.utils import generate_entity_id, generate_fact_id, normalize_entity_name

_DEICTIC_ROLE_WORDS = re.compile(
    r"\b(?:nasz(?:ego|ej|e|ym|ymi|ych)?|sw(?:ój|ojej|oje|oim|oimi|oich)|tego)\b",
    re.IGNORECASE,
)
_ROLE_TIME_TAIL = re.compile(r"\s+od\s+\d+\s+lat\b.*$", re.IGNORECASE)
_ROLE_PARTY_TAIL = re.compile(
    r"\s+(?:z|ze)\s+(?:[A-ZŻŹŁŚĆĄĘÓŃ][\wąćęłńóśźż-]*\s+){0,4}"
    r"(?:Ludowego|Obywatelskiej|Sprawiedliwości|Razem|PSL|PiS)\b.*$",
    re.IGNORECASE,
)
_PARTY_ROLE_FRAGMENT = re.compile(r"\s+partii\s+.+$", re.IGNORECASE)
_NON_ROLE_VERB_PREFIX = re.compile(
    r"^(?:złoży|zlozy|skontroluje|skontrolować|skontrolowac|zapytanie|wszystkie umowy)\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    r"\b\d+(?:[ .,]\d+)?\s*(?:tys(?:iące|ięcy|\.?)?|mln|milion(?:y|ów)?|zł(?:otych)?\.?)\b",
    re.IGNORECASE,
)
_PUBLIC_OFFICE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmarszał(?:ek|kiem)\b.*\bwojewództw", re.IGNORECASE), "marszałek województwa"),
    (re.compile(r"\bposł(?:anka|anka|owie|em|eł)\b", re.IGNORECASE), "poseł"),
    (re.compile(r"\bradn(?:a|y|ym)\b", re.IGNORECASE), "radny"),
    (re.compile(r"\bsenator(?:ka|em)?\b", re.IGNORECASE), "senator"),
    (re.compile(r"\bwojewod(?:a|ą)\b", re.IGNORECASE), "wojewoda"),
    (re.compile(r"\bwójt\b|\bwojt\b", re.IGNORECASE), "wójt"),
    (re.compile(r"\bstarost(?:a|ą)\b", re.IGNORECASE), "starosta"),
    (re.compile(r"\bprezydent(?:em)?\b.*\bmiast", re.IGNORECASE), "prezydent miasta"),
    (re.compile(r"\bminister(?:em)?\b", re.IGNORECASE), "minister"),
)
_ROLE_HELD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdyrektor(?:em|a)?\b", re.IGNORECASE), "dyrektor"),
    (
        re.compile(r"\b(?:wiceprezes(?:em|a|ką)?|zastępc[ay]\s+prezesa)\b", re.IGNORECASE),
        "wiceprezes",
    ),
    (re.compile(r"\bprezes(?:em|a|ką)?\b", re.IGNORECASE), "prezes"),
    (re.compile(r"\bszef(?:em|uje)?\b.*\bpogotowi", re.IGNORECASE), "szef pogotowia"),
)
_OWNER_ORGANIZATION_RE = re.compile(
    r"(?P<surface>(?P<head>[Ff]undacj\w*|[Ss]towarzyszen\w*|[Ii]nstytut\w*)"
    r"[^.!?]{0,120}?(?P<person>[A-ZŻŹŁŚĆĄĘÓŃ][a-ząćęłńóśźż]+\s+"
    r"[A-ZŻŹŁŚĆĄĘÓŃ][a-ząćęłńóśźż]+))"
)
_INSTITUTION_SURFACES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\burz(?:ąd|ędu)\s+marszałkowsk\w*", re.IGNORECASE), "Urząd Marszałkowski"),
    (re.compile(r"\burząd miasta\b.*", re.IGNORECASE), "Urząd Miasta"),
)
_PUBLIC_CONTRACT_CUES = (
    "otrzyma",
    "z urzędu",
    "z funduszu",
    "na rzecz",
    "promow",
    "działań promocyjnych",
    "umow",
)
_APPOINTMENT_CUES = (
    "zajął",
    "objął",
    "powoł",
    "powierzon",
    "stanowisk",
    "funkcj",
    "w zarządzie",
    "został",
)
_NEW_APPOINTMENT_CUES = (
    "nowym",
    "nową",
    "zajął",
    "objął",
    "powoł",
    "powierzon",
    "trafił",
    "trafiła",
    "zastąpił",
    "zastąpiła",
)
_BACKGROUND_ROLE_CUES = (
    "obecnie",
    "pełni tę funkcję od",
    "pełni funkcję od",
    "od 20",
    "od 19",
    "wcześniej",
    "ostatnio był",
    "ostatnio była",
    "był też",
    "była też",
    "pracował",
    "pracowała",
)
_EXPLICIT_TIE_CUES = (
    "brat",
    "siostra",
    "żona",
    "mąż",
    "syn",
    "córka",
    "znajomy",
    "znajoma",
    "współpracownik",
    "współpracowniczka",
    "doradca",
    "rekomendował",
    "z polecenia",
    "związany z",
)
_WEAK_COMMENTARY_TIE_CUES = (
    "twitter",
    "x.com",
    "hejter",
    "atakował",
    "chwalił",
    "krytykował",
    "wpisał",
    "wpis",
    "polubił",
)
_APPOINTMENT_ORG_HEAD = re.compile(
    r"(?P<surface>(?:[Pp]rzedsiębiorstw\w+|[Ss]półk\w+|[Zz]akład\w+|[Ff]undacj\w+|"
    r"[Ii]nstytut\w+|[Uu]rząd\w+|[Ww]odKan|PWiK)[^.!?;,:]*)"
)


class LLMPostProcessor:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def apply(self, document: ArticleDocument) -> ArticleDocument:
        entities_by_id: dict[EntityID, Entity] = {
            entity.entity_id: entity for entity in document.entities
        }
        self._ground_entities(document, entities_by_id)
        document.facts = self._refine_facts(document, entities_by_id)
        self._recover_public_contract_facts(document, entities_by_id)
        self._drop_unused_ungrounded_entities(document, entities_by_id)
        document.entities = list(entities_by_id.values())
        return document

    def _ground_entities(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
    ) -> None:
        referencing_facts = _facts_by_entity(document.facts)
        for entity in list(entities_by_id.values()):
            if entity.evidence:
                continue
            if entity.canonical_name.startswith("Urząd"):
                entity.entity_type = EntityType.PUBLIC_INSTITUTION
            facts = referencing_facts.get(entity.entity_id, [])
            if entity.entity_type == EntityType.ORGANIZATION:
                self._ground_organization_entity(document, entity, facts)
            elif entity.entity_type == EntityType.PUBLIC_INSTITUTION:
                self._ground_institution_entity(document, entity, facts)
            elif entity.entity_type == EntityType.POLITICAL_PARTY:
                self._ground_party_entity(document, entity, facts)

    def _refine_facts(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
    ) -> list[Fact]:
        refined: list[Fact] = []
        existing_keys: set[tuple[FactType, EntityID, EntityID | None, str, str | None]] = set()

        for fact in document.facts:
            subject = entities_by_id.get(fact.subject_entity_id)
            if subject is None:
                continue
            if _is_unsupported_llm_fact(fact):
                continue
            if fact.fact_type == FactType.PUBLIC_CONTRACT:
                self._normalize_public_money_fact(fact)
            if fact.fact_type == FactType.PARTY_MEMBERSHIP:
                refined.extend(
                    self._augment_party_fact(
                        document,
                        fact,
                        entities_by_id,
                        existing_keys,
                    )
                )
                continue
            if fact.fact_type in {FactType.POLITICAL_OFFICE, FactType.ROLE_HELD}:
                updated_facts = self._refine_role_fact(
                    document,
                    fact,
                    subject,
                    entities_by_id,
                    existing_keys,
                )
                refined.extend(updated_facts)
                continue
            self._append_fact_if_new(refined, fact, existing_keys)

        return refined

    def _recover_public_contract_facts(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
    ) -> None:
        if any(fact.fact_type == FactType.PUBLIC_CONTRACT for fact in document.facts):
            return
        existing_keys = {_fact_dedupe_key(fact) for fact in document.facts}
        for sentence in document.sentences:
            lowered = sentence.text.casefold()
            if _MONEY_RE.search(sentence.text) is None:
                continue
            if not any(cue in lowered for cue in _PUBLIC_CONTRACT_CUES):
                continue
            subject_entity = self._ensure_organization_from_sentence(
                document,
                entities_by_id,
                sentence,
            )
            object_entity = self._ensure_institution_from_sentence(
                document,
                entities_by_id,
                sentence,
            )
            if subject_entity is None or object_entity is None:
                continue
            amount_match = _MONEY_RE.search(sentence.text)
            if amount_match is None:
                continue
            evidence = EvidenceSpan(
                text=sentence.text,
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=sentence.start_char,
                end_char=sentence.end_char,
            )
            fact = Fact(
                fact_id=generate_fact_id(
                    "llm_fact",
                    str(document.document_id),
                    FactType.PUBLIC_CONTRACT.value,
                    str(subject_entity.entity_id),
                    str(object_entity.entity_id),
                    sentence.text,
                    amount_match.group(0),
                ),
                fact_type=FactType.PUBLIC_CONTRACT,
                subject_entity_id=subject_entity.entity_id,
                object_entity_id=object_entity.entity_id,
                value_text=amount_match.group(0),
                value_normalized=amount_match.group(0).casefold(),
                time_scope=TimeScope.UNKNOWN,
                event_date=document.publication_date,
                confidence=0.8,
                evidence=evidence,
                amount_text=amount_match.group(0),
                extraction_signal="llm_postprocessing",
                evidence_scope="llm_sentence_fallback",
                source_extractor="llm_postprocessing",
                score_reason="llm_public_contract_fallback",
            )
            self._append_fact_if_new(document.facts, fact, existing_keys)

    def _ensure_organization_from_sentence(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
        sentence: SentenceFragment,
    ) -> Entity | None:
        match = _OWNER_ORGANIZATION_RE.search(sentence.text)
        if match is None:
            return None
        head = match.group("head").casefold()
        head_name = "Fundacja" if head.startswith("fundacj") else "Stowarzyszenie"
        if head.startswith("instytut"):
            head_name = "Instytut"
        person_name = normalize_entity_name(match.group("person"))
        canonical_name = f"{head_name} {person_name}"
        span = _sentence_span(sentence, match.group("surface"))
        for entity in entities_by_id.values():
            if entity.entity_type != EntityType.ORGANIZATION:
                continue
            if entity.canonical_name == canonical_name or entity.canonical_name.startswith(
                head_name
            ):
                entity.canonical_name = canonical_name
                entity.normalized_name = canonical_name.casefold()
                entity.aliases = _unique_nonempty([canonical_name, match.group("surface")])
                if span is not None:
                    entity.evidence = [span]
                return entity
        entity_id = generate_entity_id(
            "llm_entity",
            str(document.document_id),
            canonical_name,
            EntityType.ORGANIZATION.value,
        )
        entity = Entity(
            entity_id=entity_id,
            entity_type=EntityType.ORGANIZATION,
            canonical_name=canonical_name,
            normalized_name=canonical_name.casefold(),
            aliases=_unique_nonempty([canonical_name, match.group("surface")]),
            evidence=[span] if span is not None else [],
        )
        entities_by_id[entity.entity_id] = entity
        return entity

    def _ensure_institution_from_sentence(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
        sentence: SentenceFragment,
    ) -> Entity | None:
        for pattern, canonical_name in _INSTITUTION_SURFACES:
            match = pattern.search(sentence.text)
            if match is None:
                continue
            span = _sentence_span(sentence, match.group(0))
            for entity in entities_by_id.values():
                if entity.canonical_name != canonical_name:
                    continue
                entity.entity_type = EntityType.PUBLIC_INSTITUTION
                if span is not None and not entity.evidence:
                    entity.evidence = [span]
                return entity
            entity_id = generate_entity_id(
                "llm_entity",
                str(document.document_id),
                canonical_name,
                EntityType.PUBLIC_INSTITUTION.value,
            )
            entity = Entity(
                entity_id=entity_id,
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name=canonical_name,
                normalized_name=canonical_name.casefold(),
                aliases=_unique_nonempty([canonical_name, match.group(0)]),
                evidence=[span] if span is not None else [],
            )
            entities_by_id[entity.entity_id] = entity
            return entity
        return None

    def _ground_organization_entity(
        self,
        document: ArticleDocument,
        entity: Entity,
        facts: list[Fact],
    ) -> None:
        for fact in facts:
            match = _OWNER_ORGANIZATION_RE.search(fact.evidence.text)
            if match is None:
                continue
            head = match.group("head").casefold()
            head_name = "Fundacja" if head.startswith("fundacj") else "Stowarzyszenie"
            if head.startswith("instytut"):
                head_name = "Instytut"
            person_name = normalize_entity_name(match.group("person"))
            entity.canonical_name = f"{head_name} {person_name}"
            entity.normalized_name = entity.canonical_name.casefold()
            entity.aliases = _unique_nonempty([entity.canonical_name, match.group("surface")])
            span = _span_from_local_match(document, fact.evidence, match.group("surface"))
            if span is not None:
                entity.evidence = [span]
            return

    def _ground_institution_entity(
        self,
        document: ArticleDocument,
        entity: Entity,
        facts: list[Fact],
    ) -> None:
        for fact in facts:
            for pattern, canonical_name in _INSTITUTION_SURFACES:
                match = pattern.search(fact.evidence.text)
                if match is None:
                    continue
                entity.canonical_name = canonical_name
                entity.normalized_name = canonical_name.casefold()
                entity.aliases = _unique_nonempty([canonical_name, match.group(0)])
                span = _span_from_local_match(document, fact.evidence, match.group(0))
                if span is not None:
                    entity.evidence = [span]
                return

    def _ground_party_entity(
        self,
        document: ArticleDocument,
        entity: Entity,
        facts: list[Fact],
    ) -> None:
        for fact in facts:
            for alias, canonical_name in self.config.party_aliases.items():
                matched_text = _match_party_surface(fact.evidence.text, alias)
                if matched_text is None or canonical_name != entity.canonical_name:
                    continue
                span = _span_from_local_match(document, fact.evidence, matched_text)
                entity.aliases = _unique_nonempty([entity.canonical_name, matched_text])
                if span is not None:
                    entity.evidence = [span]
                return

    def _normalize_public_money_fact(self, fact: Fact) -> None:
        if fact.value_text is None:
            return
        amount_match = _MONEY_RE.search(fact.value_text)
        if amount_match is not None:
            fact.amount_text = amount_match.group(0)

    def _augment_party_fact(
        self,
        document: ArticleDocument,
        fact: Fact,
        entities_by_id: dict[EntityID, Entity],
        existing_keys: set[tuple[FactType, EntityID, EntityID | None, str, str | None]],
    ) -> list[Fact]:
        party_name: str | None = None
        if fact.object_entity_id is not None:
            object_entity = entities_by_id.get(fact.object_entity_id)
            if (
                object_entity is not None
                and object_entity.entity_type == EntityType.POLITICAL_PARTY
            ):
                party_name = object_entity.canonical_name
                if not object_entity.evidence:
                    grounded_party = self._ensure_party_entity(
                        document,
                        entities_by_id,
                        party_name,
                        fact.evidence,
                    )
                    fact.object_entity_id = grounded_party.entity_id
        if party_name is None:
            names = _party_names_from_text(fact.evidence.text, self.config)
            if names:
                party_name = names[0]
                party_entity = self._ensure_party_entity(
                    document,
                    entities_by_id,
                    party_name,
                    fact.evidence,
                )
                fact.object_entity_id = party_entity.entity_id
        if party_name is None:
            return []
        fact.value_text = party_name
        fact.value_normalized = party_name.casefold()
        fact.party = party_name
        output: list[Fact] = []
        self._append_fact_if_new(output, fact, existing_keys)

        subject = entities_by_id.get(fact.subject_entity_id)
        if subject is None or subject.entity_type != EntityType.PERSON:
            return output

        office_name = _canonical_office_name(_clean_role_label(fact.evidence.text))
        if office_name is None:
            return output

        office_fact = Fact(
            fact_id=generate_fact_id(
                "llm_fact",
                str(document.document_id),
                FactType.POLITICAL_OFFICE.value,
                str(subject.entity_id),
                "",
                fact.evidence.text,
                office_name,
            ),
            fact_type=FactType.POLITICAL_OFFICE,
            subject_entity_id=subject.entity_id,
            object_entity_id=None,
            value_text=office_name,
            value_normalized=office_name.casefold(),
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=fact.confidence,
            evidence=fact.evidence,
            role=office_name,
            extraction_signal="llm_postprocessing",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_postprocessing",
            score_reason="llm_party_office_split",
        )
        self._append_fact_if_new(output, office_fact, existing_keys)
        return output

    def _refine_role_fact(
        self,
        document: ArticleDocument,
        fact: Fact,
        subject: Entity,
        entities_by_id: dict[EntityID, Entity],
        existing_keys: set[tuple[FactType, EntityID, EntityID | None, str, str | None]],
    ) -> list[Fact]:
        role_text = fact.role or fact.value_text
        if role_text is None:
            return []
        if subject.entity_type == EntityType.PERSON and not _person_entity_mentioned_in_text(
            subject, fact.evidence.text
        ):
            return []
        cleaned_role = _clean_role_label(role_text)
        canonical_public_office = _canonical_office_name(cleaned_role)
        canonical_role_held = _canonical_role_held_name(cleaned_role)
        if canonical_public_office is not None:
            cleaned_role = canonical_public_office
            fact.fact_type = FactType.POLITICAL_OFFICE
        elif canonical_role_held is not None:
            cleaned_role = canonical_role_held
            fact.fact_type = FactType.ROLE_HELD
        else:
            return []

        fact.value_text = cleaned_role
        fact.value_normalized = cleaned_role.casefold()
        fact.role = cleaned_role
        fact.object_entity_id = None
        fact.board_role = _looks_like_board_role(cleaned_role)

        output: list[Fact] = []
        party_names = _party_names_from_text(fact.evidence.text, self.config)
        for party_name in party_names:
            party_entity = self._ensure_party_entity(
                document,
                entities_by_id,
                party_name,
                fact.evidence,
            )
            party_fact = Fact(
                fact_id=generate_fact_id(
                    "llm_fact",
                    str(document.document_id),
                    FactType.PARTY_MEMBERSHIP.value,
                    str(subject.entity_id),
                    str(party_entity.entity_id),
                    fact.evidence.text,
                    party_name,
                ),
                fact_type=FactType.PARTY_MEMBERSHIP,
                subject_entity_id=subject.entity_id,
                object_entity_id=party_entity.entity_id,
                value_text=party_name,
                value_normalized=party_name.casefold(),
                time_scope=TimeScope.UNKNOWN,
                event_date=document.publication_date,
                confidence=fact.confidence,
                evidence=fact.evidence,
                party=party_name,
                extraction_signal="llm_postprocessing",
                evidence_scope="llm_evidence_quote",
                source_extractor="llm_postprocessing",
                score_reason="llm_evidence_grounded",
            )
            self._append_fact_if_new(output, party_fact, existing_keys)

        appointment_fact = self._recover_appointment_fact(
            document,
            fact,
            subject,
            cleaned_role,
            entities_by_id,
        )
        if appointment_fact is not None:
            self._append_fact_if_new(output, appointment_fact, existing_keys)
            return output

        self._append_fact_if_new(output, fact, existing_keys)
        return output

    def _recover_appointment_fact(
        self,
        document: ArticleDocument,
        fact: Fact,
        subject: Entity,
        cleaned_role: str,
        entities_by_id: dict[EntityID, Entity],
    ) -> Fact | None:
        if fact.fact_type != FactType.ROLE_HELD:
            return None
        evidence_lower = fact.evidence.text.casefold()
        if not any(cue in evidence_lower for cue in _APPOINTMENT_CUES):
            return None
        organization = self._ensure_organization_from_role_evidence(
            document,
            entities_by_id,
            fact.evidence,
        )
        if organization is None:
            return None
        appointment_role = _appointment_role_from_text(fact.evidence.text) or cleaned_role
        return Fact(
            fact_id=generate_fact_id(
                "llm_fact",
                str(document.document_id),
                FactType.APPOINTMENT.value,
                str(subject.entity_id),
                str(organization.entity_id),
                fact.evidence.text,
                appointment_role,
            ),
            fact_type=FactType.APPOINTMENT,
            subject_entity_id=subject.entity_id,
            object_entity_id=organization.entity_id,
            value_text=appointment_role,
            value_normalized=appointment_role.casefold(),
            time_scope=TimeScope.UNKNOWN,
            event_date=document.publication_date,
            confidence=fact.confidence,
            evidence=fact.evidence,
            role=appointment_role,
            board_role=_looks_like_board_role(appointment_role),
            extraction_signal="llm_postprocessing",
            evidence_scope="llm_evidence_quote",
            source_extractor="llm_postprocessing",
            score_reason="llm_appointment_grounded",
        )

    def _ensure_organization_from_role_evidence(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
        evidence: EvidenceSpan,
    ) -> Entity | None:
        matched_surface = _organization_surface_from_text(evidence.text)
        if matched_surface is None:
            return None
        canonical_name = normalize_entity_name(matched_surface)
        span = _span_from_local_match(document, evidence, matched_surface)
        entity_type = (
            EntityType.PUBLIC_INSTITUTION
            if canonical_name.startswith("Urząd")
            else EntityType.ORGANIZATION
        )
        for entity in entities_by_id.values():
            if entity.canonical_name != canonical_name:
                continue
            entity.entity_type = entity_type
            entity.normalized_name = canonical_name.casefold()
            entity.aliases = _unique_nonempty([canonical_name, matched_surface, *entity.aliases])
            if span is not None and not entity.evidence:
                entity.evidence = [span]
            return entity
        entity_id = generate_entity_id(
            "llm_entity",
            str(document.document_id),
            canonical_name,
            entity_type.value,
        )
        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name.casefold(),
            aliases=_unique_nonempty([canonical_name, matched_surface]),
            evidence=[span] if span is not None else [],
        )
        entities_by_id[entity.entity_id] = entity
        return entity

    def _ensure_party_entity(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
        party_name: str,
        evidence: EvidenceSpan,
    ) -> Entity:
        for entity in entities_by_id.values():
            if (
                entity.entity_type == EntityType.POLITICAL_PARTY
                and entity.canonical_name == party_name
            ):
                if not entity.evidence:
                    matched_text = (
                        _match_party_surface_for_canonical(
                            evidence.text,
                            party_name,
                            self.config,
                        )
                        or party_name
                    )
                    span = _span_from_local_match(document, evidence, matched_text)
                    entity.aliases = _unique_nonempty([entity.canonical_name, matched_text])
                    if span is not None:
                        entity.evidence = [span]
                return entity

        matched_text = (
            _match_party_surface_for_canonical(evidence.text, party_name, self.config) or party_name
        )
        span = _span_from_local_match(document, evidence, matched_text)
        entity_id = generate_entity_id(
            "llm_entity",
            str(document.document_id),
            party_name,
            EntityType.POLITICAL_PARTY.value,
        )
        entity = Entity(
            entity_id=entity_id,
            entity_type=EntityType.POLITICAL_PARTY,
            canonical_name=party_name,
            normalized_name=party_name.casefold(),
            aliases=_unique_nonempty([party_name, matched_text]),
            evidence=[span] if span is not None else [],
        )
        entities_by_id[entity.entity_id] = entity
        return entity

    def _append_fact_if_new(
        self,
        output: list[Fact],
        fact: Fact,
        existing_keys: set[tuple[FactType, EntityID, EntityID | None, str, str | None]],
    ) -> None:
        key = _fact_dedupe_key(fact)
        if key in existing_keys:
            return
        existing_keys.add(key)
        output.append(fact)

    def _drop_unused_ungrounded_entities(
        self,
        document: ArticleDocument,
        entities_by_id: dict[EntityID, Entity],
    ) -> None:
        used_ids = {
            entity_id
            for fact in document.facts
            for entity_id in (fact.subject_entity_id, fact.object_entity_id)
            if entity_id is not None
        }
        for entity_id, entity in list(entities_by_id.items()):
            if entity.evidence or entity_id in used_ids:
                continue
            del entities_by_id[entity_id]


def _facts_by_entity(facts: Iterable[Fact]) -> dict[EntityID, list[Fact]]:
    output: dict[EntityID, list[Fact]] = {}
    for fact in facts:
        output.setdefault(fact.subject_entity_id, []).append(fact)
        if fact.object_entity_id is not None:
            output.setdefault(fact.object_entity_id, []).append(fact)
    return output


def _fact_dedupe_key(fact: Fact) -> tuple[FactType, EntityID, EntityID | None, str, str | None]:
    if fact.fact_type == FactType.PARTY_MEMBERSHIP:
        return (fact.fact_type, fact.subject_entity_id, fact.object_entity_id, "", None)
    if fact.fact_type in {FactType.POLITICAL_OFFICE, FactType.ROLE_HELD}:
        return (fact.fact_type, fact.subject_entity_id, None, "", fact.value_normalized)
    return (
        fact.fact_type,
        fact.subject_entity_id,
        fact.object_entity_id,
        fact.evidence.text,
        fact.value_normalized,
    )


def _party_names_from_text(text: str, config: PipelineConfig) -> list[str]:
    party_names: list[str] = []
    seen: set[str] = set()
    for alias, canonical_name in config.party_aliases.items():
        matched = _match_party_surface(text, alias)
        if matched is None or canonical_name in seen:
            continue
        seen.add(canonical_name)
        party_names.append(canonical_name)
    return party_names


def _match_party_surface(text: str, alias: str) -> str | None:
    escaped = re.escape(alias)
    if alias.isupper() and len(alias) <= 4:
        pattern = re.compile(rf"\b{escaped}\b")
        match = pattern.search(text)
        return match.group(0) if match is not None else None

    exact_pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    exact_match = exact_pattern.search(text)
    if exact_match is not None:
        return exact_match.group(0)

    alias_tokens = [token for token in alias.split() if token]
    if len(alias_tokens) < 2:
        return None
    stem_parts = [rf"{re.escape(token[:5])}\w*" for token in alias_tokens if len(token) >= 5]
    stem_pattern = r"\s+".join(stem_parts)
    if not stem_pattern:
        return None
    match = re.search(rf"\b{stem_pattern}\b", text, re.IGNORECASE)
    return match.group(0) if match is not None else None


def _match_party_surface_for_canonical(
    text: str,
    canonical_name: str,
    config: PipelineConfig,
) -> str | None:
    for alias, mapped_name in config.party_aliases.items():
        if mapped_name != canonical_name:
            continue
        matched = _match_party_surface(text, alias)
        if matched is not None:
            return matched
    return None


def _person_entity_mentioned_in_text(entity: Entity, text: str) -> bool:
    name = entity.canonical_name
    if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
        return True
    name_tokens = [token for token in name.split() if token]
    if len(name_tokens) < 2:
        return False
    surname = name_tokens[-1]
    return re.search(rf"\b{re.escape(surname)}\b", text, re.IGNORECASE) is not None


def _appointment_role_from_text(text: str) -> str | None:
    for pattern, role_name in _ROLE_HELD_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            return role_name
    return None


def _organization_surface_from_text(text: str) -> str | None:
    for prefix in ("wiceprezes", "zastępca prezesa", "prezes", "dyrektor", "członek zarządu"):
        index = text.casefold().find(prefix)
        if index == -1:
            continue
        tail = text[index + len(prefix) :]
        match = _APPOINTMENT_ORG_HEAD.search(tail.strip())
        if match is not None:
            return match.group("surface").strip()
    match = _APPOINTMENT_ORG_HEAD.search(text)
    return match.group("surface").strip() if match is not None else None


def _clean_role_label(role_text: str) -> str:
    normalized = normalize_entity_name(role_text)
    normalized = _DEICTIC_ROLE_WORDS.sub("", normalized)
    normalized = _ROLE_TIME_TAIL.sub("", normalized)
    normalized = _ROLE_PARTY_TAIL.sub("", normalized)
    normalized = _PARTY_ROLE_FRAGMENT.sub("", normalized)
    normalized = normalize_entity_name(normalized)
    return normalized


def _canonical_office_name(role_text: str) -> str | None:
    if _NON_ROLE_VERB_PREFIX.search(role_text):
        return None
    for pattern, canonical_name in _PUBLIC_OFFICE_PATTERNS:
        if pattern.search(role_text):
            return canonical_name
    return None


def _canonical_role_held_name(role_text: str) -> str | None:
    if _NON_ROLE_VERB_PREFIX.search(role_text):
        return None
    for pattern, canonical_name in _ROLE_HELD_PATTERNS:
        if pattern.search(role_text):
            return canonical_name
    return None


def _is_unsupported_llm_fact(fact: Fact) -> bool:
    evidence = fact.evidence.text.casefold()
    if fact.fact_type == FactType.APPOINTMENT and _is_background_role_evidence(evidence):
        return True
    if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE and _is_weak_commentary_tie_evidence(
        evidence
    ):
        return True
    return False


def _is_background_role_evidence(evidence: str) -> bool:
    if any(cue in evidence for cue in _NEW_APPOINTMENT_CUES):
        return False
    return any(cue in evidence for cue in _BACKGROUND_ROLE_CUES)


def _is_weak_commentary_tie_evidence(evidence: str) -> bool:
    if any(cue in evidence for cue in _EXPLICIT_TIE_CUES):
        return False
    return any(cue in evidence for cue in _WEAK_COMMENTARY_TIE_CUES)


def _span_from_local_match(
    document: ArticleDocument,
    evidence: EvidenceSpan,
    matched_text: str,
) -> EvidenceSpan | None:
    local_start = evidence.text.find(matched_text)
    if local_start < 0:
        return None
    if evidence.start_char is None:
        return None
    start_char = evidence.start_char + local_start
    end_char = start_char + len(matched_text)
    return EvidenceSpan(
        text=matched_text,
        sentence_index=evidence.sentence_index,
        paragraph_index=evidence.paragraph_index,
        start_char=start_char,
        end_char=end_char,
    )


def _sentence_span(sentence: SentenceFragment, matched_text: str) -> EvidenceSpan | None:
    local_start = sentence.text.find(matched_text)
    if local_start < 0:
        return None
    start_char = sentence.start_char + local_start
    end_char = start_char + len(matched_text)
    return EvidenceSpan(
        text=matched_text,
        sentence_index=sentence.sentence_index,
        paragraph_index=sentence.paragraph_index,
        start_char=start_char,
        end_char=end_char,
    )


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _looks_like_board_role(role: str | None) -> bool:
    if role is None:
        return False
    lowered = role.casefold()
    return any(marker in lowered for marker in ("prezes", "zarząd", "rada nadzorcza"))
