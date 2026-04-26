from pipeline.complaint_classifier import detect_patronage_complaint
from pipeline.config import PipelineConfig
from pipeline.entity_classifiers import is_media_like_name, is_party_like_name
from pipeline.preprocessing.boilerplate import is_boilerplate_paragraph


def test_party_classifier_uses_shared_aliases_without_overmatching() -> None:
    config = PipelineConfig.from_file("config.yaml")

    assert is_party_like_name("Platforma Obywatelska", config) is True
    assert is_party_like_name("Rewita Hoteli", config) is False


def test_media_classifier_is_shared_and_generic() -> None:
    assert is_media_like_name("Portal Onet") is True
    assert is_media_like_name("Urząd Miasta Lublin") is False


def test_patronage_complaint_classifier_detects_generalized_signal() -> None:
    signal = detect_patronage_complaint(
        "Radna opisała kolesiostwo i rozdawanie posad wokół prezydenta miasta i jego koalicji."
    )

    assert signal is not None
    assert "kolesiostw" in signal.patronage_markers


def test_boilerplate_classifier_matches_generic_navigation_copy() -> None:
    assert is_boilerplate_paragraph(
        "Strona główna wiadomości. Logowanie i kup subskrypcję premium."
    )
    assert not is_boilerplate_paragraph(
        "Radna ujawniła publiczne wydatki i opisała nepotyzm w miejskiej spółce."
    )
