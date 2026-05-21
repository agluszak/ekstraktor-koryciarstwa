from __future__ import annotations

from typing import Protocol

import stanza
from stanza import DownloadMethod

from pipeline_v2.document import ArticleDocument
from pipeline_v2.nlp import DependencyArc, ParsedDependencySentence, ParsedDependencyToken
from pipeline_v2.types import DependencyRelation


class DependencyProvider(Protocol):
    def parse(self, text: str) -> tuple[ParsedDependencySentence, ...]: ...


class StanzaDependencyProvider:
    def __init__(self) -> None:
        self._pipeline = stanza.Pipeline(
            lang="pl",
            processors="tokenize,mwt,pos,lemma,depparse",
            download_method=DownloadMethod.REUSE_RESOURCES,
            verbose=False,
        )

    def parse(self, text: str) -> tuple[ParsedDependencySentence, ...]:
        document = self._pipeline(text)
        parsed_sentences: list[ParsedDependencySentence] = []
        for sentence_index, sentence in enumerate(document.sentences):
            tokens: list[ParsedDependencyToken] = []
            for word in sentence.words:
                tokens.append(
                    ParsedDependencyToken(
                        token_index=word.id,
                        text=word.text,
                        lemma=word.lemma,
                        upos=word.upos,
                        head_index=word.head,
                        relation=DependencyRelation.from_raw(word.deprel),
                    )
                )
            parsed_sentences.append(
                ParsedDependencySentence(
                    sentence_index=sentence_index,
                    tokens=tuple(tokens),
                )
            )
        return tuple(parsed_sentences)


class DependencyParseStage:
    def __init__(self, provider: DependencyProvider) -> None:
        self.provider = provider

    def name(self) -> str:
        return "dependency_parse_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        parsed_by_sentence_index = {
            parsed.sentence_index: parsed for parsed in self.provider.parse(document.cleaned_text)
        }
        for sentence in document.store.sentences.values():
            parsed = parsed_by_sentence_index.get(sentence.sentence_index)
            if parsed is None:
                continue
            token_ids = sentence.token_ids
            for parsed_token in parsed.tokens:
                dependent_position = parsed_token.token_index - 1
                if dependent_position < 0 or dependent_position >= len(token_ids):
                    continue
                head_token_id = None
                if parsed_token.head_index > 0:
                    head_position = parsed_token.head_index - 1
                    if head_position < len(token_ids):
                        head_token_id = token_ids[head_position]
                document.store.add_dependency_arc(
                    sentence.id,
                    DependencyArc(
                        head_token_id=head_token_id,
                        dependent_token_id=token_ids[dependent_position],
                        relation=parsed_token.relation,
                        backend="stanza",
                    ),
                )
        return document
