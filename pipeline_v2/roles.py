from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EvidenceId, MentionId, ProducerId, TokenId
from pipeline_v2.nlp import EvidenceSpan, MentionFactory, MorphologyAdapter, Sentence, Span
from pipeline_v2.types import EntityKind, GroundingKind, MentionKind


@dataclass(frozen=True, slots=True)
class RolePattern:
    lemma_sequence: tuple[str, ...]


class RoleCandidateStage:
    producer_id = ProducerId("role_candidate_stage_v2")

    _patterns = tuple(
        sorted(
            (
                RolePattern(("członek", "zarząd")),
                RolePattern(("rada", "nadzorczy")),
                RolePattern(("prezes",)),
                RolePattern(("zarząd",)),
                RolePattern(("dyrektor",)),
                RolePattern(("doradca",)),
                RolePattern(("konsultant",)),
                RolePattern(("konsultantka",)),
                RolePattern(("pełnomocnik",)),
                RolePattern(("sekretarz",)),
                RolePattern(("burmistrz",)),
            ),
            key=lambda pattern: len(pattern.lemma_sequence),
            reverse=True,
        )
    )

    def __init__(self, morphology: MorphologyAdapter) -> None:
        self.mention_factory = MentionFactory(morphology)

    def name(self) -> str:
        return "role_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in document.store.sentences.values():
            used_token_ids: set[TokenId] = set()
            for token_ids in self._matched_token_ids(document, sentence):
                if used_token_ids & set(token_ids):
                    continue
                used_token_ids.update(token_ids)
                start_char = document.store.tokens[token_ids[0]].span.start_char
                end_char = document.store.tokens[token_ids[-1]].span.end_char
                text = document.cleaned_text[start_char:end_char]
                evidence = EvidenceSpan(
                    id=EvidenceId(f"evidence-{len(document.store.evidence)}"),
                    text=text,
                    span=Span(start_char, end_char),
                    sentence_id=sentence.id,
                    paragraph_index=sentence.paragraph_index,
                    source=self.name(),
                )
                document.store.add_evidence(evidence)
                mention_id = MentionId(f"mention-{len(document.store.mentions)}")
                document.store.add_mention(
                    self.mention_factory.build_mention(
                        mention_id=mention_id,
                        text=text,
                        kind=MentionKind.ROLE,
                        evidence_id=evidence.id,
                        sentence_id=sentence.id,
                        token_ids=token_ids,
                    )
                )
                document.store.add_entity_candidate(
                    EntityCandidate(
                        id=EntityCandidateId(f"entity-{len(document.store.entity_candidates)}"),
                        kind=EntityKind.ROLE,
                        mention_ids=(mention_id,),
                        canonical_hint=text,
                        grounding=GroundingKind.OBSERVED,
                        source=self.producer_id,
                    )
                )
        return document

    def _matched_token_ids(
        self,
        document: ArticleDocument,
        sentence: Sentence,
    ) -> tuple[tuple[TokenId, ...], ...]:
        matches: list[tuple[TokenId, ...]] = []
        token_ids = sentence.token_ids
        for start_index, _token_id in enumerate(token_ids):
            for pattern in self._patterns:
                end_index = start_index + len(pattern.lemma_sequence)
                if end_index > len(token_ids):
                    continue
                window = token_ids[start_index:end_index]
                if self._matches_pattern(document, window, pattern):
                    matches.append(window)
        return tuple(matches)

    def _matches_pattern(
        self,
        document: ArticleDocument,
        token_ids: tuple[TokenId, ...],
        pattern: RolePattern,
    ) -> bool:
        for token_id, expected_lemma in zip(token_ids, pattern.lemma_sequence, strict=True):
            token = document.store.tokens[token_id]
            if expected_lemma not in {analysis.lemma for analysis in token.morph}:
                return False
        return True
