from __future__ import annotations

from pipeline_v2.ids import EvidenceId, MentionId, SentenceId
from pipeline_v2.nlp import MentionFactory, Morfeusz2MorphologyAdapter
from pipeline_v2.types import MentionKind


def test_morfeusz_adapter_normalizes_inflected_surname_without_suffix_rules() -> None:
    analyses = Morfeusz2MorphologyAdapter().analyze_token("Staruchem")

    assert any(
        analysis.lemma == "staruch" and analysis.case == "inst" and "nazwisko" in analysis.labels
        for analysis in analyses
    )


def test_morfeusz_adapter_preserves_polish_morphology_for_inflected_given_name() -> None:
    analyses = Morfeusz2MorphologyAdapter().analyze_token("Krzysztofa")

    assert any(
        analysis.lemma == "krzysztof"
        and analysis.case == "gen"
        and analysis.gender == "m1"
        and "imię" in analysis.labels
        for analysis in analyses
    )


def test_mention_factory_uses_morfeusz_head_lemma_for_inflected_surname() -> None:
    mention = MentionFactory(Morfeusz2MorphologyAdapter()).build_mention(
        mention_id=MentionId("surname-only"),
        text="Staruchem",
        kind=MentionKind.SURNAME_ONLY,
        evidence_id=EvidenceId("evidence"),
        sentence_id=SentenceId("sentence"),
    )

    assert mention.head_lemma == "staruch"
