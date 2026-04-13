from __future__ import annotations

import re
from dataclasses import dataclass

import stanza
from stanza import DownloadMethod

from pipeline.base import RelationExtractor
from pipeline.config import PipelineConfig
from pipeline.models import (
    ArticleDocument,
    CoreferenceResult,
    Entity,
    EvidenceSpan,
    Fact,
    Relation,
)
from pipeline.utils import find_dates, normalize_entity_name, normalize_party_name, stable_id

BOARD_ROLE_NAMES = {
    "prezes",
    "wiceprezes",
    "członek zarządu",
    "rada nadzorcza",
    "wiceprzewodniczący rady nadzorczej",
    "zastępca prezesa",
}
ROLE_PATTERNS = {
    "prezes": re.compile(r"\bprezes(?:em|a)?\b", re.IGNORECASE),
    "wiceprezes": re.compile(r"\bwiceprezes(?:em|a)?\b", re.IGNORECASE),
    "zastępca prezesa": re.compile(r"\bzastępc(?:a|ą)\s+prezesa\b", re.IGNORECASE),
    "dyrektor": re.compile(r"\bdyrektor(?:em|a)?\b", re.IGNORECASE),
    "członek zarządu": re.compile(r"\bczłonk(?:iem|a)\s+zarządu\b", re.IGNORECASE),
    "rada nadzorcza": re.compile(r"\brad(?:y|zie|a)\s+nadzorczej\b", re.IGNORECASE),
    "wiceprzewodniczący rady nadzorczej": re.compile(
        r"\bwiceprzewodnicząc(?:y|ego)\s+rady\s+nadzorczej\b",
        re.IGNORECASE,
    ),
    "radny": re.compile(r"\bradn(?:y|ego|a|ą)\b", re.IGNORECASE),
    "poseł": re.compile(r"\bpos(?:eł|ła|łem|łanka|łem)\b", re.IGNORECASE),
    "senator": re.compile(r"\bsenator(?:em|a)?\b", re.IGNORECASE),
    "wiceminister": re.compile(r"\bwiceminister(?:em|a)?\b", re.IGNORECASE),
    "minister": re.compile(r"\bminister(?:em|a)?\b", re.IGNORECASE),
    "prezydent miasta": re.compile(r"\bprezydent(?:em|a)?\s+miasta\b", re.IGNORECASE),
    "wiceprezydent": re.compile(r"\bwiceprezydent(?:em|a)?\b", re.IGNORECASE),
    "wicewojewoda": re.compile(r"\bwicewojewod(?:a|ą|y)\b", re.IGNORECASE),
}
APPOINTMENT_LEMMAS = {"powołać", "objąć", "wybrać", "mianować", "trafić"}
APPOINTMENT_TEXTS = {
    "został prezesem",
    "została prezeską",
    "został wiceprezesem",
    "została wiceprezeską",
    "został dyrektorem",
    "została dyrektorką",
    "odebrał nominację",
    "objął stanowisko",
    "objęła stanowisko",
    "ma zostać",
}
DISMISSAL_LEMMAS = {"odwołać", "zrezygnować"}
DISMISSAL_TEXTS = {
    "nie jest już",
    "złożył rezygnację",
    "złożyła rezygnację",
    "przyjęła rezygnację",
    "przyjął rezygnację",
}
PARTY_CONTEXT_WORDS = {
    "działacz",
    "polityk",
    "poseł",
    "posłanka",
    "senator",
    "senatorka",
    "radny",
    "radna",
    "wicewojewoda",
    "wiceminister",
}
FORMER_MARKERS = {"były", "była", "dawny", "dawna", "eks"}
TIE_WORDS = {
    "znajomy": "associate",
    "współpracownik": "collaborator",
    "przyjaciel": "friend",
    "doradca": "advisor",
    "ochroniarz": "bodyguard",
    "rekomendować": "recommender",
    "rekomendacja": "recommender",
    "szef biura": "office_chief",
}
FUNDING_HINTS = {
    "dotacja",
    "dotacje",
    "dofinansowanie",
    "dofinansowania",
    "wyłożyć",
    "przekazać",
    "sfinansować",
    "pochłonąć",
}
COMPENSATION_PATTERN = re.compile(
    r"\b(?P<amount>\d+(?:[ .,]\d+)*(?:\s*tys\.)?\s*zł(?:\s*brutto)?)"
    r"(?:\s*(?P<period>miesięcznie|mies\.|rocznie|za rok \d{4}|za miesiąc))?",
    re.IGNORECASE,
)
OFFICE_CANDIDACY_LEMMAS = {"kandydować", "startować", "ubiegać"}


@dataclass(slots=True)
class SentenceEntityAnchor:
    entity: Entity
    start: int
    end: int


@dataclass(slots=True)
class ParsedWord:
    index: int
    text: str
    lemma: str
    upos: str
    head: int
    deprel: str
    start: int
    end: int


class PolishRuleBasedRelationExtractor(RelationExtractor):
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.syntax_nlp = stanza.Pipeline(
            "pl",
            processors="tokenize,mwt,pos,lemma,depparse",
            download_method=DownloadMethod.REUSE_RESOURCES,
        )
        self.party_alias_patterns = {
            alias: self._compile_party_pattern(alias) for alias in config.party_aliases
        }

    def name(self) -> str:
        return "polish_rule_based_relation_extractor"

    def run(self, document: ArticleDocument, coreference: CoreferenceResult) -> ArticleDocument:
        document.facts = []
        mentions_by_sentence = self._mentions_by_sentence(document, coreference)
        for sentence in document.sentences:
            sentence_mentions = mentions_by_sentence.get(sentence.sentence_index, [])
            if not sentence_mentions:
                continue
            parsed_words = self._parse_sentence(sentence.text)
            if not parsed_words:
                continue
            document.facts.extend(
                self._extract_sentence_facts(
                    document=document,
                    sentence=sentence,
                    parsed_words=parsed_words,
                    sentence_mentions=sentence_mentions,
                )
            )
        document.facts = self._deduplicate_facts(document.facts)
        document.relations = self._derive_relations(document)
        return document

    def _extract_sentence_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
        sentence_mentions: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        facts: list[Fact] = []
        persons = [anchor for anchor in sentence_mentions if anchor.entity.entity_type == "Person"]
        organizations = [
            anchor for anchor in sentence_mentions if anchor.entity.entity_type == "Organization"
        ]
        facts.extend(
            self._extract_party_membership_facts(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                persons=persons,
            )
        )
        facts.extend(
            self._extract_office_facts(
                document=document,
                sentence=sentence,
                persons=persons,
            )
        )
        facts.extend(
            self._extract_candidacy_facts(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                persons=persons,
            )
        )
        facts.extend(
            self._extract_governance_facts(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                persons=persons,
                organizations=organizations,
            )
        )
        facts.extend(
            self._extract_compensation_facts(
                document=document,
                sentence=sentence,
                persons=persons,
                organizations=organizations,
            )
        )
        facts.extend(
            self._extract_tie_facts(
                document=document,
                sentence=sentence,
                persons=persons,
            )
        )
        facts.extend(
            self._extract_funding_facts(
                document=document,
                sentence=sentence,
                parsed_words=parsed_words,
                organizations=organizations,
            )
        )
        return facts

    def _extract_governance_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
        persons: list[SentenceEntityAnchor],
        organizations: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        lowered = sentence.text.lower()
        appointment = self._has_appointment_signal(parsed_words, lowered)
        dismissal = self._has_dismissal_signal(parsed_words, lowered)
        if not appointment and not dismissal:
            return []
        subject = self._subject_from_parse(parsed_words, persons)
        if subject is None and persons:
            subject = persons[0]
        if subject is None:
            return []
        organization = self._organization_from_parse(organizations, subject)
        role = self._extract_position(sentence.text, document)
        if organization is None:
            return []
        fact_type = "DISMISSAL" if dismissal else "APPOINTMENT"
        return [
            Fact(
                fact_id=stable_id(
                    "fact",
                    document.document_id,
                    fact_type,
                    subject.entity.entity_id,
                    organization.entity.entity_id,
                    role.entity_id if role else "",
                    sentence.text,
                ),
                fact_type=fact_type,
                subject_entity_id=subject.entity.entity_id,
                object_entity_id=organization.entity.entity_id,
                value_text=role.canonical_name if role else None,
                value_normalized=role.normalized_name if role else None,
                time_scope=self._time_scope(sentence.text),
                event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                confidence=0.83 if fact_type == "APPOINTMENT" else 0.81,
                evidence=self._evidence(sentence),
                attributes={
                    "position_entity_id": role.entity_id if role else None,
                    "role": role.canonical_name if role else None,
                    "board_role": bool(
                        role is not None and role.canonical_name.lower() in BOARD_ROLE_NAMES
                    ),
                },
            )
        ]

    def _extract_compensation_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        persons: list[SentenceEntityAnchor],
        organizations: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        match = COMPENSATION_PATTERN.search(sentence.text)
        if match is None or not persons:
            return []
        person = self._nearest_anchor(persons, match.start()) or persons[0]
        target = self._nearest_non_party_org(organizations, match.start())
        role = self._extract_position(sentence.text, document)
        object_entity_id = target.entity.entity_id if target else None
        if object_entity_id is None and role is not None:
            object_entity_id = role.entity_id
        if object_entity_id is None:
            return []
        return [
            Fact(
                fact_id=stable_id(
                    "fact",
                    document.document_id,
                    "COMPENSATION",
                    person.entity.entity_id,
                    object_entity_id,
                    match.group("amount"),
                    sentence.text,
                ),
                fact_type="COMPENSATION",
                subject_entity_id=person.entity.entity_id,
                object_entity_id=object_entity_id,
                value_text=match.group("amount"),
                value_normalized=normalize_entity_name(match.group("amount").lower()),
                time_scope=self._time_scope(sentence.text),
                event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                confidence=0.74,
                evidence=self._evidence(sentence),
                attributes={
                    "amount_text": normalize_entity_name(match.group("amount").lower()),
                    "period": normalize_entity_name(match.group("period").lower())
                    if match.group("period")
                    else None,
                    "position_entity_id": role.entity_id if role else None,
                },
            )
        ]

    def _extract_funding_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
        organizations: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        if len(organizations) < 2:
            return []
        lemmas = {word.lemma for word in parsed_words}
        lowered = sentence.text.lower()
        if not any(hint in lemmas or hint in lowered for hint in FUNDING_HINTS):
            return []
        source = organizations[0]
        target = organizations[-1]
        if source.entity.entity_id == target.entity.entity_id:
            return []
        amount = COMPENSATION_PATTERN.search(sentence.text)
        return [
            Fact(
                fact_id=stable_id(
                    "fact",
                    document.document_id,
                    "FUNDING",
                    target.entity.entity_id,
                    source.entity.entity_id,
                    sentence.text,
                ),
                fact_type="FUNDING",
                subject_entity_id=target.entity.entity_id,
                object_entity_id=source.entity.entity_id,
                value_text=amount.group("amount") if amount else None,
                value_normalized=normalize_entity_name(amount.group("amount").lower())
                if amount
                else None,
                time_scope="current",
                event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                confidence=0.68,
                evidence=self._evidence(sentence),
                attributes={
                    "amount_text": normalize_entity_name(amount.group("amount").lower())
                    if amount
                    else None,
                },
            )
        ]

    def _extract_party_membership_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
        persons: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        if not persons:
            return []
        lowered = sentence.text.lower()
        lemmas = {word.lemma for word in parsed_words}
        if not (
            PARTY_CONTEXT_WORDS.intersection(lemmas)
            or PARTY_CONTEXT_WORDS.intersection(set(lowered.split()))
        ):
            return []
        scope = self._time_scope(sentence.text)
        fact_type = "FORMER_PARTY_MEMBERSHIP" if scope == "former" else "PARTY_MEMBERSHIP"
        facts: list[Fact] = []
        for alias, canonical in self.config.party_aliases.items():
            for match in self.party_alias_patterns[alias].finditer(sentence.text):
                person = self._nearest_anchor(persons, match.start())
                if person is None:
                    continue
                party = self._get_or_create_entity(
                    document,
                    "PoliticalParty",
                    normalize_party_name(canonical, self.config.party_aliases),
                    alias,
                )
                facts.append(
                    Fact(
                        fact_id=stable_id(
                            "fact",
                            document.document_id,
                            fact_type,
                            person.entity.entity_id,
                            party.entity_id,
                            sentence.text,
                        ),
                        fact_type=fact_type,
                        subject_entity_id=person.entity.entity_id,
                        object_entity_id=party.entity_id,
                        value_text=party.canonical_name,
                        value_normalized=party.normalized_name,
                        time_scope=scope,
                        event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                        confidence=0.77,
                        evidence=self._evidence(sentence),
                        attributes={"party": party.canonical_name},
                    )
                )
        return facts

    def _extract_office_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        persons: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        if not persons:
            return []
        facts: list[Fact] = []
        for office_name in (
            "radny",
            "poseł",
            "senator",
            "wiceminister",
            "minister",
            "prezydent miasta",
            "wiceprezydent",
            "wicewojewoda",
        ):
            for match in ROLE_PATTERNS[office_name].finditer(sentence.text):
                person = self._nearest_anchor(persons, match.start())
                if person is None:
                    continue
                office = self._get_or_create_entity(
                    document,
                    "Position",
                    normalize_entity_name(office_name),
                    office_name,
                )
                facts.append(
                    Fact(
                        fact_id=stable_id(
                            "fact",
                            document.document_id,
                            "POLITICAL_OFFICE",
                            person.entity.entity_id,
                            office.entity_id,
                            sentence.text,
                        ),
                        fact_type="POLITICAL_OFFICE",
                        subject_entity_id=person.entity.entity_id,
                        object_entity_id=office.entity_id,
                        value_text=office.canonical_name,
                        value_normalized=office.normalized_name,
                        time_scope=self._time_scope(sentence.text),
                        event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                        confidence=0.69,
                        evidence=self._evidence(sentence),
                        attributes={"office_type": office.canonical_name},
                    )
                )
        return facts

    def _extract_candidacy_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        parsed_words: list[ParsedWord],
        persons: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        if not persons:
            return []
        lemmas = {word.lemma for word in parsed_words}
        lowered = sentence.text.lower()
        if not (OFFICE_CANDIDACY_LEMMAS.intersection(lemmas) or "kandydat" in lowered):
            return []
        person = self._subject_from_parse(parsed_words, persons) or persons[0]
        return [
            Fact(
                fact_id=stable_id(
                    "fact",
                    document.document_id,
                    "ELECTION_CANDIDACY",
                    person.entity.entity_id,
                    "",
                    sentence.text,
                ),
                fact_type="ELECTION_CANDIDACY",
                subject_entity_id=person.entity.entity_id,
                object_entity_id=None,
                value_text=None,
                value_normalized=None,
                time_scope=self._time_scope(sentence.text),
                event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                confidence=0.66,
                evidence=self._evidence(sentence),
                attributes={"candidacy_scope": "mentioned"},
            )
        ]

    def _extract_tie_facts(
        self,
        *,
        document: ArticleDocument,
        sentence,
        persons: list[SentenceEntityAnchor],
    ) -> list[Fact]:
        if not persons:
            return []
        lowered = sentence.text.lower()
        facts: list[Fact] = []
        for trigger, relationship in TIE_WORDS.items():
            if trigger not in lowered:
                continue
            if len(persons) >= 2:
                source = persons[0]
                target = persons[1]
                facts.append(
                    Fact(
                        fact_id=stable_id(
                            "fact",
                            document.document_id,
                            "PERSONAL_OR_POLITICAL_TIE",
                            source.entity.entity_id,
                            target.entity.entity_id,
                            relationship,
                            sentence.text,
                        ),
                        fact_type="PERSONAL_OR_POLITICAL_TIE",
                        subject_entity_id=source.entity.entity_id,
                        object_entity_id=target.entity.entity_id,
                        value_text=relationship,
                        value_normalized=relationship,
                        time_scope=self._time_scope(sentence.text),
                        event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                        confidence=0.67,
                        evidence=self._evidence(sentence),
                        attributes={"relationship_type": relationship},
                    )
                )
            elif trigger == "znajomy":
                person = persons[0]
                relative = self._get_or_create_entity(
                    document,
                    "Person",
                    f"Nieustalony znajomy {person.entity.canonical_name}",
                    "znajomy",
                )
                facts.append(
                    Fact(
                        fact_id=stable_id(
                            "fact",
                            document.document_id,
                            "PERSONAL_OR_POLITICAL_TIE",
                            relative.entity_id,
                            person.entity.entity_id,
                            relationship,
                            sentence.text,
                        ),
                        fact_type="PERSONAL_OR_POLITICAL_TIE",
                        subject_entity_id=relative.entity_id,
                        object_entity_id=person.entity.entity_id,
                        value_text=relationship,
                        value_normalized=relationship,
                        time_scope=self._time_scope(sentence.text),
                        event_date=next(iter(find_dates(sentence.text)), document.publication_date),
                        confidence=0.65,
                        evidence=self._evidence(sentence),
                        attributes={"relationship_type": relationship},
                    )
                )
        return facts

    def _derive_relations(self, document: ArticleDocument) -> list[Relation]:
        derived: list[Relation] = []
        entity_map = {entity.entity_id: entity for entity in document.entities}
        for fact in document.facts:
            if fact.fact_type == "APPOINTMENT" and fact.object_entity_id:
                derived.append(
                    self._relation(
                        "APPOINTED_TO",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                    )
                )
                position_entity_id = fact.attributes.get("position_entity_id")
                if position_entity_id:
                    derived.append(
                        self._relation(
                            "HOLDS_POSITION",
                            fact.subject_entity_id,
                            position_entity_id,
                            fact,
                        )
                    )
                if fact.attributes.get("board_role"):
                    derived.append(
                        self._relation(
                            "MEMBER_OF_BOARD",
                            fact.subject_entity_id,
                            fact.object_entity_id,
                            fact,
                            {"status": "current"},
                        )
                    )
            elif fact.fact_type == "DISMISSAL" and fact.object_entity_id:
                derived.append(
                    self._relation(
                        "DISMISSED_FROM",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                    )
                )
                position_entity_id = fact.attributes.get("position_entity_id")
                if position_entity_id:
                    derived.append(
                        self._relation(
                            "LEFT_POSITION",
                            fact.subject_entity_id,
                            position_entity_id,
                            fact,
                        )
                    )
                if fact.attributes.get("board_role"):
                    derived.append(
                        self._relation(
                            "MEMBER_OF_BOARD",
                            fact.subject_entity_id,
                            fact.object_entity_id,
                            fact,
                            {"status": "former"},
                        )
                    )
            elif fact.fact_type == "COMPENSATION" and fact.object_entity_id:
                derived.append(
                    self._relation(
                        "RECEIVES_COMPENSATION",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {
                            "amount_text": fact.attributes.get("amount_text"),
                            "period": fact.attributes.get("period"),
                        },
                    )
                )
            elif fact.fact_type == "FUNDING" and fact.object_entity_id:
                derived.append(
                    self._relation(
                        "FUNDED_BY",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"amount_text": fact.attributes.get("amount_text")},
                    )
                )
            elif (
                fact.fact_type in {"PARTY_MEMBERSHIP", "FORMER_PARTY_MEMBERSHIP"}
                and fact.object_entity_id
            ):
                derived.append(
                    self._relation(
                        "AFFILIATED_WITH_PARTY",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"time_scope": fact.time_scope},
                    )
                )
                person = entity_map.get(fact.subject_entity_id)
                party = entity_map.get(fact.object_entity_id)
                if person and party:
                    self._append_person_attribute(person, "parties", party.canonical_name)
            elif fact.fact_type == "PERSONAL_OR_POLITICAL_TIE" and fact.object_entity_id:
                derived.append(
                    self._relation(
                        "RELATED_TO",
                        fact.subject_entity_id,
                        fact.object_entity_id,
                        fact,
                        {"relationship": fact.attributes.get("relationship_type")},
                    )
                )
        return self._deduplicate_relations(derived)

    def _relation(
        self,
        relation_type: str,
        source_entity_id: str,
        target_entity_id: str,
        fact: Fact,
        extra_attributes: dict[str, str | None] | None = None,
    ) -> Relation:
        attributes = {
            key: value
            for key, value in (extra_attributes or {}).items()
            if value is not None
        }
        return Relation(
            relation_type=relation_type,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            confidence=fact.confidence,
            evidence=fact.evidence,
            attributes=attributes,
        )

    def _parse_sentence(self, text: str) -> list[ParsedWord]:
        doc = self.syntax_nlp(text)
        if not doc.sentences:
            return []
        cursor = 0
        parsed: list[ParsedWord] = []
        lowered = text.lower()
        for index, word in enumerate(doc.sentences[0].words, start=1):
            start = lowered.find(word.text.lower(), cursor)
            if start < 0:
                start = cursor
            end = start + len(word.text)
            parsed.append(
                ParsedWord(
                    index=index,
                    text=word.text,
                    lemma=(word.lemma or word.text).lower(),
                    upos=word.upos or "",
                    head=int(word.head or 0),
                    deprel=word.deprel or "",
                    start=start,
                    end=end,
                )
            )
            cursor = end
        return parsed

    def _subject_from_parse(
        self,
        parsed_words: list[ParsedWord],
        persons: list[SentenceEntityAnchor],
    ) -> SentenceEntityAnchor | None:
        subject_words = [
            word
            for word in parsed_words
            if word.deprel.startswith("nsubj") or word.deprel == "root"
        ]
        for word in subject_words:
            anchor = self._nearest_anchor(persons, word.start)
            if anchor is not None:
                return anchor
        return persons[0] if persons else None

    def _organization_from_parse(
        self,
        organizations: list[SentenceEntityAnchor],
        subject: SentenceEntityAnchor,
    ) -> SentenceEntityAnchor | None:
        if not organizations:
            return None
        preferred = [
            anchor
            for anchor in organizations
            if anchor.start > subject.start and not self._looks_like_party_alias(anchor.entity)
        ]
        if preferred:
            return max(preferred, key=lambda anchor: len(anchor.entity.canonical_name))
        non_party = [
            anchor
            for anchor in organizations
            if not self._looks_like_party_alias(anchor.entity)
        ]
        if non_party:
            return max(non_party, key=lambda anchor: len(anchor.entity.canonical_name))
        return organizations[0]

    def _extract_position(self, sentence_text: str, document: ArticleDocument) -> Entity | None:
        for position_name, pattern in ROLE_PATTERNS.items():
            if pattern.search(sentence_text):
                return self._get_or_create_entity(
                    document,
                    "Position",
                    normalize_entity_name(position_name),
                    position_name,
                )
        return None

    def _mentions_by_sentence(
        self, document: ArticleDocument, coreference: CoreferenceResult
    ) -> dict[int, list[SentenceEntityAnchor]]:
        entity_map = {entity.entity_id: entity for entity in document.entities}
        grouped: dict[int, list[SentenceEntityAnchor]] = {}
        for mention in [*document.mentions, *coreference.resolved_mentions]:
            if not mention.entity_id or mention.entity_id not in entity_map:
                continue
            sentence_text = document.sentences[mention.sentence_index].text.lower()
            start = sentence_text.find(mention.text.lower())
            if start < 0:
                start = 0
            grouped.setdefault(mention.sentence_index, []).append(
                SentenceEntityAnchor(
                    entity=entity_map[mention.entity_id],
                    start=start,
                    end=start + len(mention.text),
                )
            )
        return {
            key: list(
                {
                    (anchor.entity.entity_id, anchor.start, anchor.end): anchor for anchor in value
                }.values()
            )
            for key, value in grouped.items()
        }

    def _has_appointment_signal(self, parsed_words: list[ParsedWord], lowered_text: str) -> bool:
        lemmas = {word.lemma for word in parsed_words}
        if APPOINTMENT_LEMMAS.intersection(lemmas):
            return True
        return any(trigger in lowered_text for trigger in APPOINTMENT_TEXTS)

    def _has_dismissal_signal(self, parsed_words: list[ParsedWord], lowered_text: str) -> bool:
        lemmas = {word.lemma for word in parsed_words}
        if DISMISSAL_LEMMAS.intersection(lemmas):
            return True
        return any(trigger in lowered_text for trigger in DISMISSAL_TEXTS)

    @staticmethod
    def _nearest_anchor(
        anchors: list[SentenceEntityAnchor], index: int
    ) -> SentenceEntityAnchor | None:
        if not anchors:
            return None
        return min(anchors, key=lambda anchor: abs(anchor.start - index))

    @staticmethod
    def _nearest_non_party_org(
        organizations: list[SentenceEntityAnchor], index: int
    ) -> SentenceEntityAnchor | None:
        non_party = [
            anchor
            for anchor in organizations
            if not PolishRuleBasedRelationExtractor._looks_like_party_alias(anchor.entity)
        ]
        if not non_party:
            return None
        return min(non_party, key=lambda anchor: abs(anchor.start - index))

    @staticmethod
    def _compile_party_pattern(alias: str) -> re.Pattern[str]:
        if alias.isupper() and len(alias) <= 4:
            return re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
        return re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)

    @staticmethod
    def _looks_like_party_alias(entity: Entity) -> bool:
        name = entity.canonical_name.upper()
        return (
            name in {"PO", "PSL", "PIS", "KO", "LEWICA"}
            or entity.entity_type == "PoliticalParty"
        )

    @staticmethod
    def _time_scope(sentence_text: str) -> str:
        lowered = sentence_text.lower()
        if any(marker in lowered for marker in FORMER_MARKERS):
            return "former"
        if "ma zostać" in lowered:
            return "future"
        return "current"

    @staticmethod
    def _evidence(sentence) -> EvidenceSpan:
        return EvidenceSpan(
            text=sentence.text,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=sentence.start_char,
            end_char=sentence.end_char,
        )

    @staticmethod
    def _get_or_create_entity(
        document: ArticleDocument, entity_type: str, canonical_name: str, alias: str
    ) -> Entity:
        existing = next(
            (
                entity
                for entity in document.entities
                if entity.entity_type == entity_type and entity.normalized_name == canonical_name
            ),
            None,
        )
        if existing is not None:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
            return existing
        entity = Entity(
            entity_id=stable_id(entity_type.lower(), document.document_id, canonical_name),
            entity_type=entity_type,
            canonical_name=canonical_name,
            normalized_name=canonical_name,
            aliases=[alias],
        )
        document.entities.append(entity)
        return entity

    @staticmethod
    def _append_person_attribute(entity: Entity, key: str, value: str) -> None:
        values = entity.attributes.setdefault(key, [])
        if value not in values:
            values.append(value)

    @staticmethod
    def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
        deduplicated: dict[tuple[str, str, str | None, str | None, str], Fact] = {}
        for fact in facts:
            key = (
                fact.fact_type,
                fact.subject_entity_id,
                fact.object_entity_id,
                fact.value_normalized,
                fact.evidence.text,
            )
            deduplicated[key] = fact
        return list(deduplicated.values())

    @staticmethod
    def _deduplicate_relations(relations: list[Relation]) -> list[Relation]:
        deduplicated: dict[tuple[str, str, str, str], Relation] = {}
        for relation in relations:
            key = (
                relation.relation_type,
                relation.source_entity_id,
                relation.target_entity_id,
                relation.evidence.text,
            )
            deduplicated[key] = relation
        return list(deduplicated.values())
