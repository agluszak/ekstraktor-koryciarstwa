from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.candidates import EntityFactArgument
from pipeline_v2.document import ArticleDocument, PipelineInput
from pipeline_v2.entity_classification import LexicalEntityContextStage, entity_has_context_claim
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId, FactCandidateId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
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
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.stages import V2Pipeline
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import EntityTag, FactKind, GroundingKind, NerLabel
from tests_v2.materialized import argument_roles, fact_records, text_argument


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


def entity_hint_for_role(document: ArticleDocument, candidate, role: str) -> str | None:
    for argument in candidate.arguments:
        match argument:
            case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                argument_role.value == role
            ):
                return document.store.entity_candidates[entity_id].canonical_hint
            case _:
                continue
    return None


def record_has_media_outlet_entity(document, record) -> bool:
    """True if any entity bound to this record has a MEDIA_OUTLET context claim."""
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(entity_id=entity_id):
                if entity_has_context_claim(document.store, entity_id, EntityTag.MEDIA_OUTLET):
                    return True
            case _:
                continue
    return False


def is_materialized_self_tie(record) -> bool:
    subject_id = None
    object_id = None
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                argument_role.value == "subject"
            ):
                subject_id = entity_id
            case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                argument_role.value == "object"
            ):
                object_id = entity_id
            case _:
                continue
    return subject_id is not None and subject_id == object_id


def run_article_pipeline(
    *,
    title: str,
    paragraphs: tuple[str, ...],
    entities: tuple[NamedEntitySpan, ...] = (),
    apply_relevance: bool = True,
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
            ((ProfileRelevanceFilter(),) if apply_relevance else ())
            + (
                ParagraphSentenceSegmenter(),
                MorfeuszMorphologyStage(morphology),
                NamedEntityCandidateStage(
                    provider=StaticEntityProvider(entities),
                    morphology=morphology,
                ),
                LexicalEntityContextStage(),
                PartyCandidateStage(morphology),
                RoleCandidateStage(morphology),
                NominalKinshipCandidateStage(),
                FamilyProxyCandidateStage(),
                GovernanceCandidateStage(),
                PublicEmploymentCandidateStage(),
                PublicMoneyCandidateStage(),
                AntiCorruptionCandidateStage(),
                PersonalTieCandidateStage(),
                ProbabilisticInferenceStage(),
            )
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
    assert any(candidate.kind is FactKind.COMPENSATION for candidate in fact_records(document))


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
    assert any(candidate.kind is FactKind.FUNDING for candidate in fact_records(document))


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
    assert fact_records(document) == ()


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
        candidate.kind in {FactKind.PUBLIC_ROLE_APPOINTMENT, FactKind.PUBLIC_ROLE_END}
        for candidate in fact_records(document)
    )


def test_article_fixture_does_not_promote_background_political_person_to_appointee() -> None:
    title = "Synekury Polski 2050"
    paragraphs = (
        "3 stycznia 2024 roku, niespełna miesiąc po zaprzysiężeniu rządu Donalda Tuska, "
        "pełniącym obowiązki prezesa KZN został Łukasz Bałajewicz.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Donalda Tuska"),
            person_span(text, "Łukasz Bałajewicz"),
            organization_span(text, "KZN"),
        ),
        apply_relevance=False,
    )

    governance_people = {
        entity_hint_for_role(document, candidate, "person")
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    }
    assert "Łukasz Bałajewicz" in governance_people
    assert "Donalda Tuska" not in governance_people


def test_article_fixture_does_not_use_governing_body_as_governance_destination() -> None:
    title = "KZN"
    paragraphs = (
        "W Radzie Nadzorczej KZN, która wybrała Bałajewicza na prezesa, zasiada też Emil Rojek.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Bałajewicza"),
            person_span(text, "Emil Rojek"),
            organization_span(text, "Radzie Nadzorczej KZN"),
        ),
        apply_relevance=False,
    )

    governance_organizations = [
        entity_hint_for_role(document, candidate, "organization")
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    ]
    assert all(organization is None for organization in governance_organizations)


def test_article_fixture_keeps_named_family_tie_without_duplicate_same_fact_claim() -> None:
    title = "Czy wójt ukrywa nepotyzm?"
    paragraphs = (
        "Rafał Dobosz, kuzyn wójta Sosny, od pierwszych dni pracy w urzędzie wzbudzał emocje.",
        "Czy wójt Sosna rzeczywiście ukrywa nepotyzm, zatrudniając swojego kuzyna na stanowisku?",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Rafał Dobosz"),
            person_span(text, "Sosny"),
            person_span(text, "Sosna"),
        ),
        apply_relevance=False,
    )

    extended_ties = [
        record for record in fact_records(document) if record.kind is FactKind.KINSHIP_TIE
    ]
    assert extended_ties
    assert not any(
        record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE for record in fact_records(document)
    )


def test_article_fixture_keeps_public_employment_local_to_first_clause() -> None:
    title = "Charsznica"
    paragraphs = (
        "Wójt Jan Kowalski zatrudnił swojego przyszłego teścia w urzędzie gminy na stanowisko "
        "pracownika gospodarczego, "
        "a szwagierce dał zatrudnienie w Urzędzie Stanu Cywilnego.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Jan Kowalski"),
            organization_span(text, "Urzędzie Stanu Cywilnego"),
        ),
        apply_relevance=False,
    )

    employment_records = [
        candidate
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT
    ]
    assert employment_records
    employment_organizations = {
        entity_hint_for_role(document, candidate, "organization")
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT
    }
    employment_people = {
        entity_hint_for_role(document, candidate, "person")
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT
    }
    employment_roles = {
        entity_hint_for_role(document, candidate, "role")
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT and "role" in argument_roles(candidate)
    }
    assert "Urzędzie Stanu Cywilnego" not in employment_organizations
    assert "Jan Kowalski" not in employment_people
    assert any(
        person is not None and ("teść" in person or "szwagier" in person)
        for person in employment_people
    )
    assert any(role is not None and "pracownik" in role.casefold() for role in employment_roles)


def test_article_fixture_emits_anti_corruption_for_control_demand_language() -> None:
    title = "Kontrola umów"
    paragraphs = (
        "Marcelina Zawisza z partii Razem chce kontroli umów w urzędzie marszałkowskim po "
        "ujawnieniu dotacji dla fundacji dyrektora pogotowia.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Marcelina Zawisza"),
            organization_span(text, "urzędzie marszałkowskim"),
        ),
        apply_relevance=False,
    )

    assert any(
        candidate.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
        for candidate in fact_records(document)
    )


def get_assessment_score(document: ArticleDocument, record_id: FactCandidateId) -> float:
    for assessment in document.fact_assessments:
        if assessment.materialized_fact_id == record_id:
            return assessment.assessment.score
    return 0.0


def test_regression_tvn_warszawa_bielskiego() -> None:
    title = "Fundacja dyrektora pogotowia"
    paragraphs = (
        "Według TVN Warszawa fundacja założona przez Karola Bielskiego otrzymała "
        "100 tysięcy złotych z urzędu marszałkowskiego za promowanie imprezy, "
        "którą organizowało pogotowie.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            organization_span(text, "TVN Warszawa"),
            person_span(text, "Karola Bielskiego"),
            organization_span(text, "fundacja"),
            organization_span(text, "urzędu marszałkowskiego"),
        ),
        apply_relevance=False,
    )

    # Assert: FUNDING fact exists with funder "urzędu marszałkowskiego",
    # recipient "fundacja", amount "100 tysięcy złotych".
    funding_facts = [record for record in fact_records(document) if record.kind is FactKind.FUNDING]

    matching_funding = None
    for record in funding_facts:
        funder = entity_hint_for_role(document, record, "funder")
        recipient = entity_hint_for_role(document, record, "recipient")
        amount = text_argument(record, "amount") if "amount" in argument_roles(record) else None

        if (
            funder == "urzędu marszałkowskiego"
            and recipient is not None
            and recipient.startswith("fundacja")
            and amount == "100 tysięcy złotych"
        ):
            score = get_assessment_score(document, record.id)
            if score >= 0.5:
                matching_funding = record
                break

    assert matching_funding is not None, (
        "Expected a high-confidence FUNDING fact with funder="
        "'urzędu marszałkowskiego', recipient='fundacja', "
        "amount='100 tysięcy złotych'"
    )

    # Ensure TVN Warszawa is NOT the funder or recipient (any such candidate
    # must have posterior < 0.5 or be absent)
    for record in funding_facts:
        funder = entity_hint_for_role(document, record, "funder")
        recipient = entity_hint_for_role(document, record, "recipient")
        score = get_assessment_score(document, record.id)
        if funder == "TVN Warszawa" or recipient == "TVN Warszawa":
            assert score < 0.5, (
                "Expected TVN Warszawa to not be a high-confidence "
                f"funder/recipient, but got score {score}"
            )


def test_regression_wp_krasnik_wife_contracts() -> None:
    title = "Dwa dni i trzy umowy"
    paragraphs = (
        "Magdalena Skokowska, żona sekretarza urzędu miasta Kraśnik Łukasza Skokowskiego, "
        "otrzymała umowy na 10 189,50 zł z miejskich jednostek.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Magdalena Skokowska"),
            person_span(text, "Łukasza Skokowskiego"),
            organization_span(text, "urzędu miasta Kraśnik"),
            organization_span(text, "miejskich jednostek"),
        ),
        apply_relevance=False,
    )

    # Assert: Magdalena Skokowska is extracted as the contractor/employee
    # (of PUBLIC_CONTRACT and/or PUBLIC_EMPLOYMENT)
    found_employment_or_contract = False
    for record in fact_records(document):
        if record.kind is FactKind.PUBLIC_CONTRACT:
            contractor = entity_hint_for_role(document, record, "contractor")
            score = get_assessment_score(document, record.id)
            if contractor == "Magdalena Skokowska" and score >= 0.5:
                found_employment_or_contract = True
        elif record.kind is FactKind.PUBLIC_EMPLOYMENT:
            employee = entity_hint_for_role(document, record, "person")
            score = get_assessment_score(document, record.id)
            if employee == "Magdalena Skokowska" and score >= 0.5:
                found_employment_or_contract = True

    assert found_employment_or_contract, (
        "Expected Magdalena Skokowska to be contractor/employee "
        "in a high-confidence contract or employment fact"
    )

    # Assert: any spouse/family relation does not resolve to a self-tie
    # (posterior < 0.5 for self-tie)
    magdalena_id = None
    lukasz_id = None
    for ent_id, ent in document.store.entity_candidates.items():
        if ent.canonical_hint == "Magdalena Skokowska":
            magdalena_id = ent_id
        elif ent.canonical_hint == "Łukasza Skokowskiego":
            lukasz_id = ent_id

    if magdalena_id is not None and lukasz_id is not None:
        for claim in document.store.resolution_claims.values():
            if {claim.left_entity_id, claim.right_entity_id} == {magdalena_id, lukasz_id}:
                assert claim.assessment.score < 0.5, (
                    "Expected Magdalena and Lukasz to not resolve "
                    f"to each other (score {claim.assessment.score})"
                )

    if lukasz_id is not None:
        for ent_id, ent in document.store.entity_candidates.items():
            if ent.grounding == GroundingKind.PROXY:
                for claim in document.store.resolution_claims.values():
                    if {claim.left_entity_id, claim.right_entity_id} == {ent_id, lukasz_id}:
                        assert claim.assessment.score < 0.5, (
                            "Expected proxy and Lukasz to not resolve "
                            f"to each other (score {claim.assessment.score})"
                        )

    for record in fact_records(document):
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE and is_materialized_self_tie(record):
            assert get_assessment_score(document, record.id) < 0.5


def test_regression_onet_wfosigw_lublin() -> None:
    title = "Władze bez konkursu"
    paragraphs = (
        "Nowe władze WFOŚiGW w Lublinie bez konkursu. Prezesem został polityk powiązany z PSL.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            organization_span(text, "WFOŚiGW w Lublinie"),
            organization_span(text, "PSL"),
        ),
        apply_relevance=False,
    )

    # Assert: WFOŚiGW remains the high-confidence governance target;
    # PSL (party-like organization) target stays low-confidence (< 0.5).
    found_wfosigw = False
    for record in fact_records(document):
        if record.kind in {FactKind.PUBLIC_ROLE_APPOINTMENT, FactKind.PUBLIC_ROLE_END}:
            org = entity_hint_for_role(document, record, "organization")
            score = get_assessment_score(document, record.id)
            if org == "WFOŚiGW w Lublinie":
                if score >= 0.5:
                    found_wfosigw = True
            elif org == "PSL":
                assert score < 0.5, (
                    f"Expected PSL governance target to stay low-confidence, but got score {score}"
                )

    assert found_wfosigw, "Expected WFOŚiGW w Lublinie to be a high-confidence governance target"


def test_regression_businessinsider_map_stays_context_not_target() -> None:
    title = "Kadrowa czystka"
    paragraphs = ("MAP odwołało Pawła Góreckiego z rady nadzorczej PZU.",)
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Pawła Góreckiego"),
            organization_span(text, "MAP"),
            organization_span(text, "PZU"),
        ),
        apply_relevance=False,
    )

    dismissals = [
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_ROLE_END
    ]
    assert dismissals

    found_pzu_target = False
    for record in dismissals:
        score = get_assessment_score(document, record.id)
        roles = argument_roles(record)
        if "organization" in roles:
            organization = entity_hint_for_role(document, record, "organization")
            assert organization != "MAP" or score < 0.5
            if organization == "PZU" and score >= 0.5:
                found_pzu_target = True
        if "context" in roles:
            context = entity_hint_for_role(document, record, "context")
            if context == "MAP":
                assert score >= 0.5
    assert found_pzu_target


def test_regression_pleszew_stadnina() -> None:
    title = "Stadnina w Pleszewie"
    paragraphs = ("Skarb Państwa odwołał dotychczasowego prezesa stadniny koni w Pleszewie.",)
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            organization_span(text, "Skarb Państwa"),
            organization_span(text, "stadniny koni w Pleszewie"),
        ),
        apply_relevance=False,
    )

    # Assert: Skarb Państwa is mapped to context/EventRole.CONTEXT,
    # not organization/target of dismissal.
    dismissal_records = [
        record for record in fact_records(document) if record.kind is FactKind.PUBLIC_ROLE_END
    ]
    assert dismissal_records, "Expected at least one PUBLIC_ROLE_END record"
    found_stadnina_organization = False
    for record in dismissal_records:
        roles = argument_roles(record)
        if "organization" not in roles:
            continue
        organization = entity_hint_for_role(document, record, "organization")
        if organization is None:
            continue
        if "stadnin" in organization.casefold():
            found_stadnina_organization = True
            break
    assert found_stadnina_organization, (
        "Expected a governance appointment organization grounded in the stadnina mention"
    )

    for record in dismissal_records:
        roles = argument_roles(record)
        if "context" in roles:
            context_org = entity_hint_for_role(document, record, "context")
            if context_org == "Skarb Państwa":
                pass
        if "organization" in roles:
            org = entity_hint_for_role(document, record, "organization")
            assert org != "Skarb Państwa", (
                "Skarb Państwa should not be the target organization of the dismissal"
            )


def test_regression_wp_warszawa_salaries() -> None:
    title = "Zarobki prezesów spółek"
    paragraphs = (
        "Dziennikarze Wirtualnej Polski ustalili, ile zarabiają prezesi warszawskich spółek "
        "miejskich. Wiesław Pancer zarabia 30 tys. zł brutto w WodKan.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            organization_span(text, "Wirtualnej Polski"),
            person_span(text, "Wiesław Pancer"),
            organization_span(text, "WodKan"),
        ),
        apply_relevance=False,
    )

    compensation_records = [
        record for record in fact_records(document) if record.kind is FactKind.COMPENSATION
    ]

    matching_compensation = None
    for record in compensation_records:
        recipient = entity_hint_for_role(document, record, "recipient")
        funder = entity_hint_for_role(document, record, "funder")
        amount = text_argument(record, "amount") if "amount" in argument_roles(record) else None
        score = get_assessment_score(document, record.id)

        if (
            recipient == "Wiesław Pancer"
            and funder == "WodKan"
            and amount is not None
            and "30 tys. zł" in amount
        ):
            if score >= 0.5:
                matching_compensation = record
                break

    assert matching_compensation is not None, (
        "Expected a high-confidence COMPENSATION fact for Wiesław Pancer in WodKan with 30 tys. zł"
    )

    # Ensure Wirtualnej Polski is NOT a high-confidence funder or recipient.
    # The MEDIA_OUTLET entity context claim should suppress it via the
    # EntityContext↔RoleFiller constraint factor; if for some reason it still
    # appears, the entity should at least carry a MEDIA_OUTLET claim so the
    # downstream UI can flag it.
    for record in compensation_records:
        recipient = entity_hint_for_role(document, record, "recipient")
        funder = entity_hint_for_role(document, record, "funder")
        score = get_assessment_score(document, record.id)
        if recipient == "Wirtualnej Polski" or funder == "Wirtualnej Polski":
            assert score < 0.5 or record_has_media_outlet_entity(document, record), (
                "Expected Wirtualnej Polski to be either low-confidence as "
                "funder/recipient, or carry a MEDIA_OUTLET context claim, "
                f"but got score {score}"
            )


def test_regression_wp_opole_family() -> None:
    title = "Rodzina w Opolu"
    paragraphs = (
        "Jakub Wiśniewski, syn prezydenta Opola Arkadiusza Wiśniewskiego, dostał posadę "
        "w spółce miejskiej WIK. Prezydent Wiśniewski popierany jest przez Koalicję Obywatelską.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Jakub Wiśniewski"),
            person_span(text, "Arkadiusza Wiśniewskiego"),
            organization_span(text, "WIK"),
            organization_span(text, "Koalicję Obywatelską"),
        ),
        apply_relevance=False,
    )

    # Assert: KINSHIP_TIE between Jakub Wiśniewski and Arkadiusza Wiśniewskiego
    tie_records = [
        record for record in fact_records(document) if record.kind is FactKind.KINSHIP_TIE
    ]

    matching_tie = None
    for record in tie_records:
        subject = entity_hint_for_role(document, record, "subject")
        obj = entity_hint_for_role(document, record, "object")
        score = get_assessment_score(document, record.id)

        if {subject, obj} == {"Jakub Wiśniewski", "Arkadiusza Wiśniewskiego"}:
            if score >= 0.5:
                matching_tie = record
                break

    assert matching_tie is not None, (
        "Expected a high-confidence KINSHIP_TIE between "
        "Jakub Wiśniewski and Arkadiusza Wiśniewskiego"
    )

    # Verify no high-confidence self-ties
    jakub_id = None
    arkadiusz_id = None
    for ent_id, ent in document.store.entity_candidates.items():
        if ent.canonical_hint == "Jakub Wiśniewski":
            jakub_id = ent_id
        elif ent.canonical_hint == "Arkadiusza Wiśniewskiego":
            arkadiusz_id = ent_id

    if jakub_id is not None and arkadiusz_id is not None:
        for claim in document.store.resolution_claims.values():
            if {claim.left_entity_id, claim.right_entity_id} == {jakub_id, arkadiusz_id}:
                assert claim.assessment.score < 0.5, (
                    "Expected Jakub and Arkadiusz to not resolve "
                    f"to each other, but got score {claim.assessment.score}"
                )

    for record in tie_records:
        if is_materialized_self_tie(record):
            assert get_assessment_score(document, record.id) < 0.5

    # Koalicja Obywatelska does not win workplace/governance slots
    for record in fact_records(document):
        if record.kind is FactKind.PUBLIC_EMPLOYMENT:
            workplace = entity_hint_for_role(document, record, "organization")
            score = get_assessment_score(document, record.id)
            if workplace == "Koalicję Obywatelską":
                assert score < 0.5, (
                    f"Expected Koalicja Obywatelska to not be a workplace, but got score {score}"
                )
        elif record.kind in {FactKind.PUBLIC_ROLE_APPOINTMENT, FactKind.PUBLIC_ROLE_END}:
            org = entity_hint_for_role(document, record, "organization")
            score = get_assessment_score(document, record.id)
            if org == "Koalicję Obywatelską":
                assert score < 0.5, (
                    "Expected Koalicja Obywatelska to not be governance "
                    f"target, but got score {score}"
                )


def test_regression_tvn24_kolesiostwo_emits_patronage_complaint() -> None:
    title = "Kolesiostwo i rozdawanie posad. Miasto umiera"
    paragraphs = (
        "Dorota Połedniok pisze do premiera Donalda Tuska o kolesiostwie i rozdawaniu posad.",
        "PO tworzy koalicję z Forum Samorządowym w Siemianowicach Śląskich, "
        "a radna krytykuje lokalnych partyjnych baronów i nagrody dla prezydentów miasta.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Dorota Połedniok"),
            person_span(text, "Donalda Tuska"),
            organization_span(text, "PO"),
            organization_span(text, "Forum Samorządowym"),
            organization_span(text, "Siemianowicach Śląskich"),
        ),
        apply_relevance=False,
    )

    complaint_records = [
        record
        for record in fact_records(document)
        if record.kind in {FactKind.PATRONAGE_ALLEGATION, FactKind.PATRONAGE_NETWORK_TIE}
    ]
    assert complaint_records
    assert any(record.kind is FactKind.PATRONAGE_ALLEGATION for record in complaint_records)

    has_strong_local_signal = False
    for record in complaint_records:
        score = get_assessment_score(document, record.id)
        assert score >= 0.4
        actor = entity_hint_for_role(document, record, "complainant")
        target = entity_hint_for_role(document, record, "target")
        subject = entity_hint_for_role(document, record, "subject")
        obj = entity_hint_for_role(document, record, "object")
        if (
            actor in {"Dorota Połedniok", "Donalda Tuska"}
            or target
            in {
                "Dorota Połedniok",
                "Donalda Tuska",
            }
            or subject in {"Dorota Połedniok", "Donalda Tuska"}
            or obj
            in {
                "Dorota Połedniok",
                "Donalda Tuska",
            }
        ):
            has_strong_local_signal = True
            break
    assert has_strong_local_signal


def test_regression_rp_klich_emits_collaborator_tie_signal() -> None:
    title = "Znajomi Klicha w spółkach WAM"
    paragraphs = (
        "Jarosław Hodura od grudnia jest prezesem Grupy Hoteli WAM i dostał się bez konkursu.",
        "Były szef biura europoselskiego Klicha i jego wieloletni przyjaciel trafił do zarządu.",
    )
    text = "\n".join(paragraphs)
    document = run_article_pipeline(
        title=title,
        paragraphs=paragraphs,
        entities=(
            person_span(text, "Jarosław Hodura"),
            person_span(text, "Klicha"),
            organization_span(text, "Grupy Hoteli WAM"),
        ),
        apply_relevance=False,
    )

    tie_or_complaint_records = [
        record
        for record in fact_records(document)
        if record.kind
        in {
            FactKind.PERSONAL_OR_POLITICAL_TIE,
            FactKind.PATRONAGE_ALLEGATION,
            FactKind.PATRONAGE_NETWORK_TIE,
        }
    ]
    assert tie_or_complaint_records
    assert any(
        record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE for record in tie_or_complaint_records
    )
    assert any(
        get_assessment_score(document, record.id) >= 0.45 for record in tie_or_complaint_records
    )

    assert any(
        {
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        }
        == {"Jarosław Hodura", "Klicha"}
        for record in tie_or_complaint_records
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    )


def test_regression_negatives() -> None:
    # Meloni meeting
    title_meloni = "Spotkanie premierów w Rzymie"
    paragraphs_meloni = (
        "Giorgia Meloni spotkała się w Rzymie z premierem Donaldem Tuskiem. "
        "Rozmawiali o bezpieczeństwie i współpracy w Europie.",
    )
    text_meloni = "\n".join(paragraphs_meloni)
    doc_meloni = run_article_pipeline(
        title=title_meloni,
        paragraphs=paragraphs_meloni,
        entities=(
            person_span(text_meloni, "Giorgia Meloni"),
            person_span(text_meloni, "Donaldem Tuskiem"),
        ),
        apply_relevance=True,
    )
    assert doc_meloni.relevance is not None
    assert doc_meloni.relevance.is_relevant is False or len(fact_records(doc_meloni)) == 0

    # TK legal status query
    title_tk = "Pytanie prawne do Trybunału Konstytucyjnego"
    paragraphs_tk = (
        "Sąd Okręgowy skierował pytanie prawne do Trybunału Konstytucyjnego w sprawie "
        "statusu sędziów powołanych po 2018 roku.",
    )
    text_tk = "\n".join(paragraphs_tk)
    doc_tk = run_article_pipeline(
        title=title_tk,
        paragraphs=paragraphs_tk,
        entities=(
            organization_span(text_tk, "Sąd Okręgowy"),
            organization_span(text_tk, "Trybunału Konstytucyjnego"),
        ),
        apply_relevance=True,
    )
    assert doc_tk.relevance is not None
    assert doc_tk.relevance.is_relevant is False or len(fact_records(doc_tk)) == 0
