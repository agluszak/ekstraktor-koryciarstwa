from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.types import EntityKind
from tests_v2.helpers import setup_base_test_document


def run_role_stage(text: str) -> ArticleDocument:
    document = setup_base_test_document(text)
    morphology = Morfeusz2MorphologyAdapter()
    RoleCandidateStage(morphology).run(document)
    return document


def test_role_stage_extracts_inflected_single_and_multi_token_roles_by_lemma() -> None:
    document = run_role_stage("Został prezesem, członkiem zarządu i wszedł do zarządu spółki.")

    role_candidates = tuple(document.store.entity_candidates.values())

    assert tuple(candidate.kind for candidate in role_candidates) == (
        EntityKind.ROLE,
        EntityKind.ROLE,
        EntityKind.ROLE,
    )
    assert tuple(candidate.canonical_hint for candidate in role_candidates) == (
        "prezesem",
        "członkiem zarządu",
        "zarządu",
    )


def test_role_stage_prefers_longest_role_phrase_over_nested_role_words() -> None:
    document = run_role_stage("Odwołano ją z rady nadzorczej spółki.")

    assert tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    ) == ("rady nadzorczej",)


def test_role_stage_extracts_consultancy_and_proxy_roles_by_lemma() -> None:
    document = run_role_stage("Został doradcą, konsultantką projektu i pełnomocnikiem burmistrza.")

    role_hints = tuple(
        candidate.canonical_hint for candidate in document.store.entity_candidates.values()
    )

    assert "doradcą" in role_hints
    assert "konsultantką" in role_hints
    assert "pełnomocnikiem" in role_hints
