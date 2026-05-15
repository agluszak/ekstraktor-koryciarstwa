from __future__ import annotations

from dataclasses import replace

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import TokenId
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, MorphologyAdapter, Span, Token


class MorfeuszMorphologyStage:
    def __init__(self, morphology: MorphologyAdapter | None = None) -> None:
        self.morphology = morphology or Morfeusz2MorphologyAdapter()

    def name(self) -> str:
        return "morfeusz_morphology_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for sentence in sorted(
            document.store.sentences.values(),
            key=lambda item: item.sentence_index,
        ):
            token_ids: list[TokenId] = []
            cursor = 0
            for token_index, morph_token in enumerate(self.morphology.analyze_text(sentence.text)):
                local_start = sentence.text.find(morph_token.text, cursor)
                if local_start < 0:
                    local_start = cursor
                local_end = local_start + len(morph_token.text)
                cursor = local_end
                token_id = TokenId(f"{sentence.id}:token-{token_index}")
                document.store.add_token(
                    Token(
                        id=token_id,
                        sentence_id=sentence.id,
                        text=morph_token.text,
                        span=Span(
                            start_char=sentence.span.start_char + local_start,
                            end_char=sentence.span.start_char + local_end,
                        ),
                        morph=morph_token.analyses,
                    )
                )
                token_ids.append(token_id)
            document.store.sentences[sentence.id] = replace(sentence, token_ids=tuple(token_ids))
        return document
