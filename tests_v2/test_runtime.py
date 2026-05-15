from __future__ import annotations

from pipeline_v2.nlp import NamedEntitySpan
from pipeline_v2.runtime import CoreferenceMode, V2PipelineConfig, build_v2_pipeline


class EmptyNamedEntityProvider:
    def __init__(self, model_name: str) -> None:
        _ = model_name

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return ()


def test_runtime_records_disabled_coreference_as_stage_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(
        "pipeline_v2.runtime.SpacyNamedEntityProvider",
        EmptyNamedEntityProvider,
    )

    pipeline = build_v2_pipeline(V2PipelineConfig(coreference_mode=CoreferenceMode.OFF))
    stage_names = tuple(stage.name() for stage in pipeline.stages)

    assert "public_employment_candidate_stage_v2" in stage_names
    assert "family_proxy_candidate_stage_v2" in stage_names
    assert "personal_tie_candidate_stage_v2" in stage_names
    assert "coreference_stage_v2" in stage_names
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "public_employment_candidate_stage_v2"
    )
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "public_money_candidate_stage_v2"
    )
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "personal_tie_candidate_stage_v2"
    )


def test_runtime_light_coreference_adds_reference_stage(monkeypatch) -> None:
    monkeypatch.setattr(
        "pipeline_v2.runtime.SpacyNamedEntityProvider",
        EmptyNamedEntityProvider,
    )

    pipeline = build_v2_pipeline(V2PipelineConfig(coreference_mode=CoreferenceMode.LIGHT))
    stage_names = tuple(stage.name() for stage in pipeline.stages)

    assert "public_employment_candidate_stage_v2" in stage_names
    assert "family_proxy_candidate_stage_v2" in stage_names
    assert "personal_tie_candidate_stage_v2" in stage_names
    assert "light_reference_stage_v2" in stage_names
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "public_employment_candidate_stage_v2"
    )
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "public_money_candidate_stage_v2"
    )
    assert stage_names.index("fact_scoring_stage_v2") > stage_names.index(
        "personal_tie_candidate_stage_v2"
    )
