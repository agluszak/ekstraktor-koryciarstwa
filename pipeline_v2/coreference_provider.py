from __future__ import annotations

import stanza
import torch
from stanza.pipeline.coref_processor import extract_text

from pipeline_v2.coreference import CoreferenceProvider
from pipeline_v2.nlp import CoreferenceSpanLink, Span
from pipeline_v2.types import ReferenceKind

_GENERIC_ORG_NOUNS = frozenset(
    {
        "spółka",
        "firma",
        "instytucja",
        "organizacja",
        "stowarzyszenie",
        "fundacja",
        "podmiot",
        "przedsiębiorstwo",
        "zakład",
        "towarzystwo",
        "urząd",
    }
)


class StanzaCoreferenceProvider(CoreferenceProvider):
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self._nlp = stanza.Pipeline(
            "pl",
            processors="tokenize,coref",
            coref_model_path=model_path,
            download_method=stanza.DownloadMethod.REUSE_RESOURCES,
        )

    def links(self, text: str) -> tuple[CoreferenceSpanLink, ...]:
        links: list[CoreferenceSpanLink] = []
        with torch.inference_mode():
            doc = self._nlp(text)

        for chain in doc.coref:
            rep_text = chain.representative_text
            if not rep_text:
                continue
            # Skip chain if the representative text contains a generic org noun
            if any(token in _GENERIC_ORG_NOUNS for token in rep_text.casefold().split()):
                continue

            # Map mentions to their spans and text
            mentions_with_spans: list[tuple[str, Span]] = []
            for mention in chain.mentions:
                sentence_index = mention.sentence
                if sentence_index < 0 or sentence_index >= len(doc.sentences):
                    continue
                sentence = doc.sentences[sentence_index]
                if mention.start_word < 0 or mention.end_word > len(sentence.words):
                    continue
                first_word = sentence.words[mention.start_word]
                last_word = sentence.words[mention.end_word - 1]
                start_char = first_word.start_char
                end_char = last_word.end_char
                if end_char <= start_char:
                    continue
                mention_text = extract_text(
                    doc,
                    mention.sentence,
                    mention.start_word,
                    mention.end_word,
                )
                mentions_with_spans.append((mention_text, Span(start_char, end_char)))

            if not mentions_with_spans:
                continue

            # Find the antecedent mention
            # Try to match the representative text
            antecedent_idx = 0
            for idx, (m_text, _) in enumerate(mentions_with_spans):
                if m_text.casefold() == rep_text.casefold():
                    antecedent_idx = idx
                    break

            antecedent_text, antecedent_span = mentions_with_spans[antecedent_idx]

            # Link subsequent mentions
            for idx, (m_text, m_span) in enumerate(mentions_with_spans):
                if idx == antecedent_idx:
                    continue
                # Skip if reference does not follow antecedent
                if m_span.start_char < antecedent_span.end_char:
                    continue
                # Skip generic nouns
                if m_text.casefold() in _GENERIC_ORG_NOUNS:
                    continue

                ref_kind = self._classify_reference_kind(m_text)
                links.append(
                    CoreferenceSpanLink(
                        antecedent_text=antecedent_text,
                        antecedent_span=antecedent_span,
                        reference_text=m_text,
                        reference_span=m_span,
                        reference_kind=ref_kind,
                    )
                )
        return tuple(links)

    @staticmethod
    def _classify_reference_kind(text: str) -> ReferenceKind:
        tokens = text.lower().split()
        if len(tokens) == 1:
            word = tokens[0]
            if word in {
                "jego",
                "jej",
                "ich",
                "swój",
                "swoja",
                "swoje",
                "swoich",
                "swoim",
                "swojej",
            }:
                return ReferenceKind.POSSESSIVE_PRONOUN
            if word in {
                "on",
                "ona",
                "ono",
                "oni",
                "one",
                "go",
                "mu",
                "niego",
                "niemu",
                "nim",
                "nich",
                "nimi",
            }:
                return ReferenceKind.PRONOUN
        return ReferenceKind.DESCRIPTOR_NOUN_PHRASE
