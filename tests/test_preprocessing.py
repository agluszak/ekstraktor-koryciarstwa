from pathlib import Path

from pipeline.models import PipelineInput
from pipeline.preprocessing import TrafilaturaPreprocessor


def test_tvp_article_recovers_from_metadata_when_trafilatura_fails() -> None:
    html = Path(
        "inputs/olsztyn.tvp.pl__41863255__z-wiceprezydenta-na-wiceprezesa-jaroslaw-sloma-w-zarzadzie-olsztynskich-wodociagow.html"
    ).read_text(encoding="utf-8")

    document = TrafilaturaPreprocessor().run(PipelineInput(raw_html=html))

    assert document.content_source in {"metadata_recovery", "hybrid"}
    assert document.cleaned_text
    assert "Jarosław Słoma" in document.cleaned_text
    assert "zastępcy prezesa Przedsiębiorstwa Wodociągów i Kanalizacji" in document.cleaned_text


def test_radomszczanska_comments_are_removed_from_cleaned_text() -> None:
    html = Path("inputs/radomszczanska.pl__artykul__nowy-zaciag-tlustych-n1256470.html").read_text(
        encoding="utf-8"
    )

    document = TrafilaturaPreprocessor().run(PipelineInput(raw_html=html))

    assert "niezalogowany" not in document.cleaned_text.lower()
    assert "Twoje zdanie jest ważne" not in document.cleaned_text
    assert "Marek Rząsowski, radny powiatowy PO" in document.cleaned_text
