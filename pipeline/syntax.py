from __future__ import annotations

import uuid
from typing import Any

from pipeline.base import ClauseParser
from pipeline.config import PipelineConfig
from pipeline.domain_types import ClauseID
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    ParsedSentence,
    ParsedWord,
    SentenceFragment,
)
from pipeline.runtime import PipelineRuntime


class StanzaClauseParser(ClauseParser):
    def __init__(self, config: PipelineConfig, runtime: PipelineRuntime) -> None:
        self.config = config
        self.runtime = runtime

    def name(self) -> str:
        return "stanza_clause_parser"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        parsed_stanza_sentences = self._parse_document(document)
        document.parsed_sentences = {
            sentence.sentence_index: self._align_sentence(sentence, parsed_stanza_sentences)
            for sentence in document.sentences
        }

        clause_units: list[ClauseUnit] = []

        for sentence_fragment in document.sentences:
            parsed_words = document.parsed_sentences.get(sentence_fragment.sentence_index, [])
            roots = [word for word in parsed_words if word.deprel == "root"]
            if not roots and parsed_words:
                roots = [parsed_words[0]]

            for root in roots:
                clause_id = ClauseID(f"clause-{uuid.uuid4().hex[:8]}")
                clause_mentions: list[ClusterMention] = []
                mention_roles: dict[str, str] = {}

                sent_offset = sentence_fragment.start_char

                for cluster in document.resolved_entities:
                    for mention in cluster.mentions:
                        if mention.sentence_index != sentence_fragment.sentence_index:
                            continue
                        clause_mentions.append(mention)
                        m_words = self._words_for_mention(
                            mention,
                            parsed_words,
                            sent_offset,
                        )
                        if not m_words:
                            continue
                        main_word = next(
                            (word for word in m_words if word.head == root.index),
                            m_words[0],
                        )
                        mention_roles[mention.text] = main_word.deprel

                clause_units.append(
                    ClauseUnit(
                        clause_id=clause_id,
                        text=sentence_fragment.text,
                        trigger_head_text=root.text,
                        trigger_head_lemma=root.lemma,
                        sentence_index=sentence_fragment.sentence_index,
                        paragraph_index=sentence_fragment.paragraph_index,
                        start_char=sentence_fragment.start_char,
                        end_char=sentence_fragment.end_char,
                        cluster_mentions=clause_mentions,
                        mention_roles=mention_roles,
                    )
                )

        document.clause_units = clause_units
        return document

    def _parse_document(self, document: ArticleDocument) -> list[ParsedSentence]:
        stanza_doc = self.runtime.get_stanza_syntax_pipeline()(document.cleaned_text)
        return [self._to_parsed_sentence(sentence) for sentence in stanza_doc.sentences]

    @staticmethod
    def _to_parsed_sentence(sentence: Any) -> ParsedSentence:
        parsed_words = [
            ParsedWord(
                index=int(word.id if isinstance(word.id, int) else word.id[0]),
                text=word.text,
                lemma=(word.lemma or word.text).lower(),
                upos=word.upos or "",
                head=int(word.head or 0),
                deprel=word.deprel or "",
                start=int(word.start_char),
                end=int(word.end_char),
                feats=_parse_feats(getattr(word, "feats", None)),
            )
            for word in sentence.words
        ]
        if not parsed_words:
            return ParsedSentence(start_char=0, end_char=0, words=[])
        return ParsedSentence(
            start_char=min(word.start for word in parsed_words),
            end_char=max(word.end for word in parsed_words),
            words=parsed_words,
        )

    @classmethod
    def _align_sentence(
        cls,
        sentence: SentenceFragment,
        parsed_sentences: list[ParsedSentence],
    ) -> list[ParsedWord]:
        if not parsed_sentences:
            return []

        best_sentence = max(
            parsed_sentences,
            key=lambda parsed_sentence: cls._sentence_overlap(sentence, parsed_sentence),
        )
        overlap = cls._sentence_overlap(sentence, best_sentence)
        if overlap <= 0:
            return []

        return [
            ParsedWord(
                index=word.index,
                text=word.text,
                lemma=word.lemma,
                upos=word.upos,
                head=word.head,
                deprel=word.deprel,
                start=max(0, word.start - sentence.start_char),
                end=max(0, word.end - sentence.start_char),
                feats=dict(word.feats),
            )
            for word in best_sentence.words
        ]

    @staticmethod
    def _sentence_overlap(sentence: SentenceFragment, parsed_sentence: ParsedSentence) -> int:
        return max(
            0,
            min(sentence.end_char, parsed_sentence.end_char)
            - max(sentence.start_char, parsed_sentence.start_char),
        )

    @staticmethod
    def _words_for_mention(
        mention: ClusterMention,
        parsed_words: list[ParsedWord],
        sent_offset: int,
    ) -> list[ParsedWord]:
        if mention.start_char == 0 and mention.end_char == 0:
            mention_text = mention.text.lower()
            return [
                word
                for word in parsed_words
                if word.text.lower() in mention_text or mention_text in word.text.lower()
            ]
        return [
            word
            for word in parsed_words
            if (word.start + sent_offset) >= mention.start_char
            and (word.end + sent_offset) <= mention.end_char
        ]


def _parse_feats(raw_feats: str | None) -> dict[str, str]:
    if raw_feats is None:
        return {}
    return dict(feature.split("=", 1) for feature in raw_feats.split("|") if "=" in feature)
