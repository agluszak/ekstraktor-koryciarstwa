from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.document import ArticleDocument, PipelineInput
from pipeline_v2.fact_resolution import FactResolutionStage
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.nominal_coreference import NominalKinshipCandidateStage
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.preprocessing import compact_text
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.relevance import ProfileRelevanceFilter
from pipeline_v2.resolution_scoring import ResolutionScoringStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.stages import V2Pipeline
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import FactKind, NerLabel


@dataclass(slots=True)
class StaticPreprocessor:
    document: ArticleDocument

    def name(self) -> str:
        return "static_article_preprocessor"

    def run(self, data: PipelineInput) -> ArticleDocument:
        _ = data
        return self.document


@dataclass(frozen=True, slots=True)
class StaticEntityProvider:
    entities: tuple[NamedEntitySpan, ...]

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def run_article_pipeline(
    *,
    title: str,
    paragraphs: tuple[str, ...],
    entities: tuple[NamedEntitySpan, ...] = (),
) -> ArticleDocument:
    document = ArticleDocument(
        document_id=DocumentId("article-fixture"),
        source_url=None,
        title=title,
        publication_date=None,
        cleaned_text="\n".join(compact_text(paragraph) for paragraph in paragraphs),
        paragraphs=tuple(compact_text(paragraph) for paragraph in paragraphs),
    )
    morphology = Morfeusz2MorphologyAdapter()
    pipeline = V2Pipeline(
        preprocessor=StaticPreprocessor(document),
        stages=(
            ProfileRelevanceFilter(),
            ParagraphSentenceSegmenter(),
            MorfeuszMorphologyStage(morphology),
            NamedEntityCandidateStage(
                provider=StaticEntityProvider(entities),
                morphology=morphology,
            ),
            PartyCandidateStage(morphology),
            RoleCandidateStage(morphology),
            NominalKinshipCandidateStage(),
            GovernanceCandidateStage(),
            PublicEmploymentCandidateStage(),
            PublicMoneyCandidateStage(),
            AntiCorruptionCandidateStage(),
            FamilyProxyCandidateStage(),
            PersonalTieCandidateStage(),
            ResolutionScoringStage(),
            FactResolutionStage(),
            FactScoringStage(),
        ),
    )
    return pipeline.run_document(PipelineInput(raw_html="<html></html>"))


def test_article_fixture_keeps_compensation_article_relevant() -> None:
    title = (
        "Sprawdzili zarobki prezesów przedsiębiorstw wodociągowych w największych "
        "miastach. Ile zarabia prezes WodKanu w Olsztynie?"
    )
    paragraphs = (
        "Wiesław Pancer, prezes Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie, "
        "według danych za rok 2019 zarabiał 322 030,80 zł, co plasowało go mniej więcej "
        "w środku stawki, zaraz za prezesem z Katowic i nad prezesem z Gdańska.",
        "Przekładając kwoty na liczbę mieszkańców pensja Wiesława Pancera kosztuje "
        "każdego olsztynianina 1,88 zł.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Wiesław Pancer"),
            organization_span(text, "Przedsiębiorstwa Wodociągów i Kanalizacji w Olsztynie"),
        ),
    )

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any(
        candidate.to_fact_record().kind is FactKind.COMPENSATION
        for candidate in document.store.fact_candidates.values()
    )


def test_article_fixture_keeps_funding_article_relevant() -> None:
    title = "Miliony złotych od państwa na „pajęczynę” o. Rydzyka. Liczymy pieniądze"
    paragraphs = (
        "Wprawdzie realizowała go założona przez o. Rydzyka Fundacja Lux Veritatis, ale "
        "pieniądze wyłożyły w znacznej części państwowe instytucje i spółki.",
        "W czerwcu 2018 roku Fundacja Lux Veritatis podpisała z ministerstwem kultury "
        "umowę o powołaniu Muzeum Pamięć i Tożsamość. Resort wyłoży 117,7 mln zł na budowę "
        "jego siedziby.",
        "W październiku 2018 roku premier Mateusz Morawiecki przyznał Fundacji Lux "
        "Veritatis 5 mln zł z rezerwy budżetowej na realizację Parku Pamięci Narodowej.",
        "W maju 2019 roku fundacja dostała kolejne 3 mln zł z rezerwy budżetowej na drugi "
        "etap budowy Parku Pamięci.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Mateusz Morawiecki"),
            organization_span(text, "Fundacja Lux Veritatis"),
            organization_span(text, "ministerstwem kultury"),
        ),
    )

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any(
        candidate.to_fact_record().kind is FactKind.FUNDING
        for candidate in document.store.fact_candidates.values()
    )


def test_article_fixture_rejects_tribunal_legal_analysis_article() -> None:
    title = "Nowi sędziowie TK zapowiadają pozwy. Eksperci mają wątpliwości"
    paragraphs = (
        "Po tym, jak prezes Trybunału Konstytucyjnego, Bogdan Święczkowski nie dopuścił "
        "do orzekania czworga nowych sędziów TK, należy się spodziewać skorzystania przez "
        "nich z drogi sądowej.",
        "Rozważam drogę sądową, ale jeśli chodzi o sferę stosunku pracowniczego. "
        "Stosunek służby sędziego TK ma dwie warstwy i droga sądowa przysługuje tylko "
        "w tym zakresie.",
        "Potwierdza to orzeczenie Sądu Najwyższego, w którym uznano, że sprawa nie ma "
        "charakteru sprawy cywilnej i pozew podlega odrzuceniu.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Bogdan Święczkowski"),
            organization_span(text, "Trybunału Konstytucyjnego"),
            organization_span(text, "Sądu Najwyższego"),
        ),
    )

    assert document.relevance is not None
    assert document.relevance.is_relevant is False
    assert tuple(document.store.fact_candidates.values()) == ()


def test_article_fixture_keeps_governance_control_article_relevant() -> None:
    title = "Partyjny desant na Totalizator Sportowy. Polityczni działacze dostali stanowiska"
    paragraphs = (
        "Kadrowa miotła nowego rządu dotarła tu w lutym 2024 r. Wtedy to z funkcji "
        "odwołany został dotychczasowy prezes Olgierd Cieślik.",
        "Dyrektorem kieleckiego oddziału Totalizatora Sportowego został związany z "
        "Koalicją Obywatelską przewodniczący Rady Miasta w Kielcach Karol Wilczyński.",
        "Jego zastępcą na nowym stanowisku jest z kolei Sebastian Nowaczkiewicz, były "
        "wójt podkieleckich Nowin, związany z Polskim Stronnictwem Ludowym.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Olgierd Cieślik"),
            person_span(text, "Karol Wilczyński"),
            person_span(text, "Sebastian Nowaczkiewicz"),
            organization_span(text, "Totalizatora Sportowego"),
            organization_span(text, "Rady Miasta w Kielcach"),
        ),
    )

    assert document.relevance is not None
    assert document.relevance.is_relevant is True
    assert any(
        candidate.to_fact_record().kind
        in {FactKind.GOVERNANCE_APPOINTMENT, FactKind.GOVERNANCE_DISMISSAL}
        for candidate in document.store.fact_candidates.values()
    )
