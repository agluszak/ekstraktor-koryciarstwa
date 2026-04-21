from pipeline.config import PipelineConfig
from pipeline.domain_types import (
    EntityType,
    FactType,
    IdentityHypothesisReason,
    IdentityHypothesisStatus,
    KinshipDetail,
    RelationshipType,
)
from pipeline.frames import PolishGovernanceFrameExtractor
from pipeline.identity import PolishFamilyIdentityResolver
from pipeline.models import (
    ArticleDocument,
    ClauseUnit,
    ClusterMention,
    Entity,
    EntityCluster,
    EvidenceSpan,
    ParsedWord,
    SentenceFragment,
)
from pipeline.normalization import DocumentEntityCanonicalizer


def _word(
    index: int,
    text: str,
    lemma: str,
    upos: str,
    head: int,
    deprel: str,
    start: int,
) -> ParsedWord:
    return ParsedWord(
        index=index,
        text=text,
        lemma=lemma,
        upos=upos,
        head=head,
        deprel=deprel,
        start=start,
        end=start + len(text),
    )


def _person_cluster(
    entity_id: str,
    name: str,
    *,
    sentence_index: int,
    paragraph_index: int,
    start_char: int,
) -> tuple[Entity, EntityCluster]:
    evidence = EvidenceSpan(
        text=name,
        sentence_index=sentence_index,
        paragraph_index=paragraph_index,
        start_char=start_char,
        end_char=start_char + len(name),
    )
    entity = Entity(
        entity_id=entity_id,
        entity_type=EntityType.PERSON,
        canonical_name=name,
        normalized_name=name,
        evidence=[evidence],
    )
    cluster = EntityCluster(
        cluster_id=f"cluster-{entity_id}",
        entity_type=EntityType.PERSON,
        canonical_name=name,
        normalized_name=name,
        mentions=[
            ClusterMention(
                text=name,
                entity_type=EntityType.PERSON,
                sentence_index=sentence_index,
                paragraph_index=paragraph_index,
                start_char=start_char,
                end_char=start_char + len(name),
                entity_id=entity_id,
            )
        ],
    )
    return entity, cluster


def _document(sentences: list[str], parsed: dict[int, list[ParsedWord]]) -> ArticleDocument:
    offsets: list[int] = []
    cursor = 0
    for sentence in sentences:
        offsets.append(cursor)
        cursor += len(sentence) + 1
    text = " ".join(sentences)
    return ArticleDocument(
        document_id="family-doc",
        source_url=None,
        raw_html="",
        title="Test",
        publication_date="2026-04-21",
        cleaned_text=text,
        paragraphs=[text],
        sentences=[
            SentenceFragment(
                text=sentence,
                paragraph_index=0,
                sentence_index=index,
                start_char=offsets[index],
                end_char=offsets[index] + len(sentence),
            )
            for index, sentence in enumerate(sentences)
        ],
        parsed_sentences=parsed,
        clause_units=[
            ClauseUnit(
                clause_id=f"clause-{index}",
                text=sentence,
                trigger_head_text="",
                trigger_head_lemma="",
                sentence_index=index,
                paragraph_index=0,
                start_char=offsets[index],
                end_char=offsets[index] + len(sentence),
            )
            for index, sentence in enumerate(sentences)
        ],
    )


def test_creates_spouse_proxy_and_family_tie() -> None:
    text = "Żona Karola Wilczyńskiego była zatrudniona w spółce."
    doc = _document(
        [text],
        {
            0: [
                _word(1, "Żona", "żona", "NOUN", 4, "nsubj", 0),
                _word(2, "Karola", "Karol", "PROPN", 1, "nmod", 5),
                _word(3, "Wilczyńskiego", "Wilczyński", "PROPN", 2, "flat", 12),
                _word(4, "była", "być", "AUX", 0, "root", 26),
            ]
        },
    )
    entity, cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=0,
        paragraph_index=0,
        start_char=5,
    )
    doc.entities.append(entity)
    doc.clusters.append(cluster)

    resolved = PolishFamilyIdentityResolver(PipelineConfig.from_file("config.yaml")).run(doc)

    proxy = next(entity for entity in resolved.entities if entity.attributes.get("is_proxy_person"))
    assert proxy.attributes["kinship_detail"] == KinshipDetail.SPOUSE
    assert proxy.attributes["proxy_anchor_entity_id"] == "person-karol"
    family_facts = [
        fact for fact in resolved.facts if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
    ]
    assert family_facts
    assert family_facts[0].subject_entity_id == proxy.entity_id
    assert family_facts[0].object_entity_id == "person-karol"
    assert family_facts[0].attributes["relationship_type"] == RelationshipType.FAMILY


def test_sister_proxy_is_separate_from_spouse_proxy() -> None:
    sentences = [
        "Żona Karola Wilczyńskiego pracowała w jednostce.",
        "Siostra pana przewodniczącego została dyrektorem.",
    ]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Żona", "żona", "NOUN", 4, "nsubj", 0),
                _word(2, "Karola", "Karol", "PROPN", 1, "nmod", 5),
                _word(3, "Wilczyńskiego", "Wilczyński", "PROPN", 2, "flat", 12),
                _word(4, "pracowała", "pracować", "VERB", 0, "root", 26),
            ],
            1: [
                _word(1, "Siostra", "siostra", "NOUN", 4, "nsubj", 0),
                _word(2, "pana", "pan", "NOUN", 1, "nmod", 8),
                _word(3, "przewodniczącego", "przewodniczący", "NOUN", 2, "flat", 13),
                _word(4, "została", "zostać", "VERB", 0, "root", 30),
            ],
        },
    )
    entity, cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=0,
        paragraph_index=0,
        start_char=5,
    )
    doc.entities.append(entity)
    doc.clusters.append(cluster)

    resolved = PolishFamilyIdentityResolver(PipelineConfig.from_file("config.yaml")).run(doc)

    proxy_kinds = {
        entity.attributes["kinship_detail"]
        for entity in resolved.entities
        if entity.attributes.get("is_proxy_person")
    }
    assert {KinshipDetail.SPOUSE, KinshipDetail.SIBLING_SISTER} <= proxy_kinds
    assert not any(
        hypothesis.status == IdentityHypothesisStatus.PROBABLE
        for hypothesis in resolved.identity_hypotheses
    )


def test_possessive_partner_is_probable_same_person_as_spouse_proxy() -> None:
    sentences = [
        "Żona Karola Wilczyńskiego była zatrudniona.",
        "Moja partnerka jest zatrudniona od 10 lat - mówi Karol Wilczyński.",
    ]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Żona", "żona", "NOUN", 4, "nsubj", 0),
                _word(2, "Karola", "Karol", "PROPN", 1, "nmod", 5),
                _word(3, "Wilczyńskiego", "Wilczyński", "PROPN", 2, "flat", 12),
                _word(4, "była", "być", "AUX", 0, "root", 26),
            ],
            1: [
                _word(1, "Moja", "mój", "DET", 2, "det:poss", 0),
                _word(2, "partnerka", "partnerka", "NOUN", 4, "nsubj", 5),
                _word(3, "jest", "być", "AUX", 4, "aux", 15),
                _word(4, "zatrudniona", "zatrudnić", "VERB", 8, "parataxis", 20),
                _word(8, "mówi", "mówić", "VERB", 0, "root", 49),
                _word(9, "Karol", "Karol", "PROPN", 8, "nsubj", 54),
                _word(10, "Wilczyński", "Wilczyński", "PROPN", 9, "flat", 60),
            ],
        },
    )
    offset = len(sentences[0]) + 1
    entity, cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=1,
        paragraph_index=0,
        start_char=offset + 54,
    )
    doc.entities.append(entity)
    doc.clusters.append(cluster)

    resolved = PolishFamilyIdentityResolver(PipelineConfig.from_file("config.yaml")).run(doc)

    assert any(
        hypothesis.status == IdentityHypothesisStatus.PROBABLE
        and hypothesis.reason == IdentityHypothesisReason.SAME_ANCHOR_COMPATIBLE_FAMILY_PROXY
        for hypothesis in resolved.identity_hypotheses
    )


def test_honorific_surname_only_stays_possible() -> None:
    sentences = [
        "Żona Karola Wilczyńskiego była zatrudniona.",
        "Pani Wilczyńska dostała nowe obowiązki.",
    ]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Żona", "żona", "NOUN", 4, "nsubj", 0),
                _word(2, "Karola", "Karol", "PROPN", 1, "nmod", 5),
                _word(3, "Wilczyńskiego", "Wilczyński", "PROPN", 2, "flat", 12),
                _word(4, "była", "być", "AUX", 0, "root", 26),
            ],
            1: [
                _word(1, "Pani", "pani", "NOUN", 3, "nsubj", 0),
                _word(2, "Wilczyńska", "Wilczyńska", "PROPN", 1, "flat", 5),
                _word(3, "dostała", "dostać", "VERB", 0, "root", 16),
            ],
        },
    )
    entity, cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=0,
        paragraph_index=0,
        start_char=5,
    )
    doc.entities.append(entity)
    doc.clusters.append(cluster)

    resolved = PolishFamilyIdentityResolver(PipelineConfig.from_file("config.yaml")).run(doc)

    assert any(
        hypothesis.status == IdentityHypothesisStatus.POSSIBLE
        and hypothesis.reason == IdentityHypothesisReason.HONORIFIC_SURNAME_ONLY
        for hypothesis in resolved.identity_hypotheses
    )
    assert not any(
        hypothesis.status == IdentityHypothesisStatus.PROBABLE
        for hypothesis in resolved.identity_hypotheses
    )
    canonicalized = DocumentEntityCanonicalizer(PipelineConfig.from_file("config.yaml")).run(
        resolved
    )
    assert any(
        entity.attributes.get("is_honorific_person_ref") for entity in canonicalized.entities
    )
    assert any(entity.entity_id == "person-karol" for entity in canonicalized.entities)


def test_full_name_with_near_family_context_is_probable_proxy_match() -> None:
    sentences = [
        "Żona Karola Wilczyńskiego była zatrudniona.",
        "Agnieszka Wilczyńska pracowała w jednostce publicznej.",
    ]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Żona", "żona", "NOUN", 4, "nsubj", 0),
                _word(2, "Karola", "Karol", "PROPN", 1, "nmod", 5),
                _word(3, "Wilczyńskiego", "Wilczyński", "PROPN", 2, "flat", 12),
                _word(4, "była", "być", "AUX", 0, "root", 26),
            ],
            1: [
                _word(1, "Agnieszka", "Agnieszka", "PROPN", 3, "nsubj", 0),
                _word(2, "Wilczyńska", "Wilczyńska", "PROPN", 1, "flat", 10),
                _word(3, "pracowała", "pracować", "VERB", 0, "root", 21),
            ],
        },
    )
    karol, karol_cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=0,
        paragraph_index=0,
        start_char=5,
    )
    agnieszka_start = len(sentences[0]) + 1
    agnieszka, agnieszka_cluster = _person_cluster(
        "person-agnieszka",
        "Agnieszka Wilczyńska",
        sentence_index=1,
        paragraph_index=0,
        start_char=agnieszka_start,
    )
    doc.entities.extend([karol, agnieszka])
    doc.clusters.extend([karol_cluster, agnieszka_cluster])

    resolved = PolishFamilyIdentityResolver(PipelineConfig.from_file("config.yaml")).run(doc)

    assert any(
        hypothesis.status == IdentityHypothesisStatus.PROBABLE
        and hypothesis.reason == IdentityHypothesisReason.SURNAME_COMPATIBLE_NEAR_FAMILY_CONTEXT
        and "person-agnieszka" in {hypothesis.left_entity_id, hypothesis.right_entity_id}
        for hypothesis in resolved.identity_hypotheses
    )


def test_sister_proxy_is_governance_subject_not_anchor() -> None:
    sentences = [
        "Karol Wilczyński przewodniczył komisji.",
        "Siostra pana przewodniczącego została dyrektorem Miejskiego Urzędu Pracy.",
    ]
    doc = _document(
        sentences,
        {
            0: [
                _word(1, "Karol", "Karol", "PROPN", 2, "nsubj", 0),
                _word(2, "Wilczyński", "Wilczyński", "PROPN", 3, "flat", 6),
                _word(3, "przewodniczył", "przewodniczyć", "VERB", 0, "root", 17),
            ],
            1: [
                _word(1, "Siostra", "siostra", "NOUN", 4, "nsubj", 0),
                _word(2, "pana", "pan", "NOUN", 1, "nmod", 8),
                _word(3, "przewodniczącego", "przewodniczący", "NOUN", 2, "flat", 13),
                _word(4, "została", "zostać", "VERB", 0, "root", 30),
                _word(5, "dyrektorem", "dyrektor", "NOUN", 4, "xcomp", 38),
                _word(6, "Miejskiego", "miejski", "ADJ", 7, "amod", 49),
                _word(7, "Urzędu", "urząd", "NOUN", 4, "obl", 59),
                _word(8, "Pracy", "praca", "NOUN", 7, "flat", 66),
            ],
        },
    )
    karol, karol_cluster = _person_cluster(
        "person-karol",
        "Karol Wilczyński",
        sentence_index=0,
        paragraph_index=0,
        start_char=0,
    )
    org_start = len(sentences[0]) + 1 + sentences[1].index("Miejskiego")
    org = Entity(
        entity_id="org-mup",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        canonical_name="Miejski Urząd Pracy",
        normalized_name="Miejski Urząd Pracy",
    )
    org_cluster = EntityCluster(
        cluster_id="cluster-mup",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        canonical_name="Miejski Urząd Pracy",
        normalized_name="Miejski Urząd Pracy",
        mentions=[
            ClusterMention(
                text="Miejskiego Urzędu Pracy",
                entity_type=EntityType.PUBLIC_INSTITUTION,
                sentence_index=1,
                paragraph_index=0,
                start_char=org_start,
                end_char=org_start + len("Miejskiego Urzędu Pracy"),
                entity_id="org-mup",
            )
        ],
    )
    doc.entities.extend([karol, org])
    doc.clusters.extend([karol_cluster, org_cluster])
    doc.clause_units[1].trigger_head_text = "została"
    doc.clause_units[1].trigger_head_lemma = "zostać"
    doc.clause_units[1].cluster_mentions.append(org_cluster.mentions[0])

    config = PipelineConfig.from_file("config.yaml")
    resolved = PolishFamilyIdentityResolver(config).run(doc)
    framed = PolishGovernanceFrameExtractor(config).run(resolved)

    frame = framed.governance_frames[0]
    proxy_cluster_ids = {
        cluster.cluster_id
        for cluster in framed.clusters
        if cluster.attributes.get("kinship_detail") == KinshipDetail.SIBLING_SISTER
    }
    assert frame.person_cluster_id in proxy_cluster_ids
    assert frame.person_cluster_id != "cluster-person-karol"
