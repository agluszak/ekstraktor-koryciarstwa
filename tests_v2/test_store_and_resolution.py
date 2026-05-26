from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate, EntityResolutionProposal
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    DocumentId,
    EntityCandidateId,
    EvidenceId,
    MentionId,
    ProducerId,
    SentenceId,
    TokenId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.nlp import (
    EvidenceSpan,
    Mention,
    MentionFactory,
    Morfeusz2MorphologyAdapter,
    MorphAnalysis,
    ReferenceMention,
    Sentence,
    Span,
    Token,
)
from pipeline_v2.producers import EvidenceSignalProducer, SimpleEntityCandidateProducer
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    CanonicalHintMatchSignal,
    EntityKind,
    GroundingKind,
    MentionKind,
    ReferenceKind,
    ResolutionRelation,
    SameNameContradictionSignal,
)


def _add_sentence(store: ExtractionStore, text: str, *, paragraph_index: int = 0) -> SentenceId:
    sentence_id = SentenceId(f"sentence-{len(store.sentences)}")
    store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=len(store.sentences),
            paragraph_index=paragraph_index,
            text=text,
            span=Span(start_char=0, end_char=len(text)),
        )
    )
    return sentence_id


def _add_mention(
    store: ExtractionStore,
    *,
    sentence_id: SentenceId,
    text: str,
    start: int,
    kind: MentionKind = MentionKind.NER,
    use_morphology: bool = False,
) -> MentionId:
    evidence_id = EvidenceId(f"evidence-{len(store.evidence)}")
    sentence = store.sentences[sentence_id]
    store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text=sentence.text,
            span=Span(start_char=0, end_char=len(sentence.text)),
            sentence_id=sentence_id,
            paragraph_index=sentence.paragraph_index,
        )
    )
    mention_id = MentionId(f"mention-{len(store.mentions)}")
    if use_morphology:
        mention = MentionFactory(Morfeusz2MorphologyAdapter()).build_mention(
            mention_id=mention_id,
            text=text,
            kind=kind,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
        )
    else:
        mention = Mention(
            id=mention_id,
            text=text,
            kind=kind,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
        )
    store.add_mention(mention)
    _ = start
    return mention_id


def _add_tokenized_mention(
    store: ExtractionStore,
    *,
    sentence_id: SentenceId,
    evidence_id: EvidenceId,
    mention_id: MentionId,
    tokens: tuple[tuple[str, tuple[MorphAnalysis, ...]], ...],
) -> MentionId:
    sentence = store.sentences[sentence_id]
    offset = 0
    token_ids: list[TokenId] = []
    for index, (text, morph) in enumerate(tokens):
        while offset < len(sentence.text) and sentence.text[offset] == " ":
            offset += 1
        start = offset
        end = start + len(text)
        token_id = TokenId(f"{sentence_id}:token-extra-{index}")
        store.add_token(
            Token(
                id=token_id,
                sentence_id=sentence_id,
                text=text,
                span=Span(start_char=start, end_char=end),
                morph=morph,
            )
        )
        token_ids.append(token_id)
        offset = end
    store.add_mention(
        Mention(
            id=mention_id,
            text=" ".join(text for text, _ in tokens),
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
            token_ids=tuple(token_ids),
        )
    )
    return mention_id


def test_full_inflected_name_creates_resolution_proposal_instead_of_reuse() -> None:
    store = ExtractionStore()
    producer = SimpleEntityCandidateProducer()
    first_sentence = _add_sentence(store, "Krzysztof Staruch wygrał wybory.")
    second_sentence = _add_sentence(store, "Krzysztofa Starucha poparł komitet.")
    first_mention = _add_mention(
        store, sentence_id=first_sentence, text="Krzysztof Staruch", start=0
    )
    second_mention = _add_mention(
        store,
        sentence_id=second_sentence,
        text="Krzysztofa Starucha",
        start=0,
    )

    first_id = producer.add_full_person(
        store,
        candidate_id=EntityCandidateId("person-1"),
        mention_ids=(first_mention,),
        given_name_lemma="krzysztof",
        surname_base="staruch",
        canonical_hint="Krzysztof Staruch",
    )
    second_id = producer.add_full_person(
        store,
        candidate_id=EntityCandidateId("person-2"),
        mention_ids=(second_mention,),
        given_name_lemma="krzysztof",
        surname_base="staruch",
        canonical_hint="Krzysztof Staruch",
    )

    assert first_id != second_id
    assert store.entity_candidates[first_id].mention_ids == (first_mention,)
    assert store.entity_candidates[second_id].mention_ids == (second_mention,)

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[second_id]
    )
    assert len(proposals) == 1
    assert proposals[0].left_entity_id == second_id
    assert proposals[0].right_entity_id == first_id


def test_surname_only_candidate_creates_resolution_claim_instead_of_reuse() -> None:
    store = ExtractionStore()
    producer = SimpleEntityCandidateProducer()
    sentence_id = _add_sentence(store, "Krzysztof Staruch rozmawiał ze Staruchem.")
    full_mention = _add_mention(store, sentence_id=sentence_id, text="Krzysztof Staruch", start=0)
    surname_mention = _add_mention(
        store,
        sentence_id=sentence_id,
        text="Staruchem",
        start=29,
        kind=MentionKind.SURNAME_ONLY,
        use_morphology=True,
    )

    full_id = producer.add_full_person(
        store,
        candidate_id=EntityCandidateId("person-full"),
        mention_ids=(full_mention,),
        given_name_lemma="krzysztof",
        surname_base="staruch",
        canonical_hint="Krzysztof Staruch",
    )
    partial_id = producer.add_surname_only_person(
        store,
        candidate_id=EntityCandidateId("person-partial"),
        mention_ids=(surname_mention,),
        canonical_hint="Staruch",
    )

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[partial_id]
    )
    assert len(proposals) == 1

    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Krzysztof Staruch rozmawiał ze Staruchem.",
        paragraphs=("Krzysztof Staruch rozmawiał ze Staruchem.",),
    )
    document.store = store
    ProbabilisticInferenceStage().run(document)
    claims = tuple(store.resolution_claims_for_entity(partial_id))

    assert partial_id != full_id
    assert len(claims) == 1
    assert claims[0].relation is ResolutionRelation.SAME_AS
    assert claims[0].assessment.score > 0.5


def test_repeated_political_party_mentions_create_resolution_proposal() -> None:
    store = ExtractionStore()
    first_sentence = _add_sentence(store, "Z PO rozmawiał prezydent.")
    second_sentence = _add_sentence(store, "Radny z PO poparł decyzję.")
    first_mention = _add_mention(store, sentence_id=first_sentence, text="PO", start=2)
    second_mention = _add_mention(store, sentence_id=second_sentence, text="PO", start=8)

    first_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-1"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(first_mention,),
            canonical_hint="Platforma Obywatelska",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    second_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-2"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(second_mention,),
            canonical_hint="Platforma Obywatelska",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[second_id]
    )

    assert len(proposals) == 1
    assert proposals[0].left_entity_id == second_id
    assert proposals[0].right_entity_id == first_id
    assert proposals[0].retrieval_signals == (
        CanonicalHintMatchSignal(hint="platforma obywatelska"),
    )


def test_repeated_organization_mentions_create_resolution_proposal() -> None:
    store = ExtractionStore()
    first_sentence = _add_sentence(store, "CBA sprawdzi sprawę.")
    second_sentence = _add_sentence(store, "Do CBA trafiło zawiadomienie.")
    first_mention = _add_mention(store, sentence_id=first_sentence, text="CBA", start=0)
    second_mention = _add_mention(store, sentence_id=second_sentence, text="CBA", start=3)

    first_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(first_mention,),
            canonical_hint="CBA",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    second_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-2"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(second_mention,),
            canonical_hint="CBA",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[second_id]
    )

    assert len(proposals) == 1
    assert proposals[0].left_entity_id == second_id
    assert proposals[0].right_entity_id == first_id
    assert proposals[0].retrieval_signals == (CanonicalHintMatchSignal(hint="cba"),)


def test_inflected_full_name_candidates_create_resolution_proposal_without_reuse_key() -> None:
    store = ExtractionStore()
    first_sentence = _add_sentence(store, "Dominika Herberholza skrytykowano.")
    second_sentence = _add_sentence(store, "Dominik Herberholz odpowiedział.")
    first_evidence_id = EvidenceId("evidence-inflected-1")
    second_evidence_id = EvidenceId("evidence-inflected-2")
    store.add_evidence(
        EvidenceSpan(
            id=first_evidence_id,
            text="Dominika Herberholza",
            span=Span(start_char=0, end_char=20),
            sentence_id=first_sentence,
            paragraph_index=0,
            source=ProducerId("test"),
        )
    )
    store.add_evidence(
        EvidenceSpan(
            id=second_evidence_id,
            text="Dominik Herberholz",
            span=Span(start_char=0, end_char=19),
            sentence_id=second_sentence,
            paragraph_index=1,
            source=ProducerId("test"),
        )
    )
    first_mention = _add_tokenized_mention(
        store,
        sentence_id=first_sentence,
        evidence_id=first_evidence_id,
        mention_id=MentionId("mention-inflected-1"),
        tokens=(
            (
                "Dominika",
                (
                    MorphAnalysis(lemma="dominika", pos="subst", labels=("imię",)),
                    MorphAnalysis(lemma="dominik", pos="subst", labels=("imię",)),
                ),
            ),
            (
                "Herberholza",
                (MorphAnalysis(lemma="herberholza", pos="ign"),),
            ),
        ),
    )
    second_mention = _add_tokenized_mention(
        store,
        sentence_id=second_sentence,
        evidence_id=second_evidence_id,
        mention_id=MentionId("mention-inflected-2"),
        tokens=(
            (
                "Dominik",
                (MorphAnalysis(lemma="dominik", pos="subst", labels=("imię",)),),
            ),
            (
                "Herberholz",
                (MorphAnalysis(lemma="herberholz", pos="ign"),),
            ),
        ),
    )

    first_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person-1"),
            kind=EntityKind.PERSON,
            mention_ids=(first_mention,),
            canonical_hint="Dominika Herberholza",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    second_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person-2"),
            kind=EntityKind.PERSON,
            mention_ids=(second_mention,),
            canonical_hint="Dominik Herberholz",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[second_id]
    )

    assert len(proposals) == 1
    assert proposals[0].left_entity_id == second_id
    assert proposals[0].right_entity_id == first_id


def test_unique_far_surname_match_creates_resolution_proposal() -> None:
    store = ExtractionStore()
    producer = SimpleEntityCandidateProducer()
    first_sentence = _add_sentence(store, "Rafał Krzemień zabrał głos.", paragraph_index=0)
    second_sentence = _add_sentence(store, "Krzemień został odwołany.", paragraph_index=6)
    full_mention = _add_mention(
        store,
        sentence_id=first_sentence,
        text="Rafał Krzemień",
        start=0,
    )
    surname_mention = _add_mention(
        store,
        sentence_id=second_sentence,
        text="Krzemień",
        start=0,
        kind=MentionKind.SURNAME_ONLY,
        use_morphology=True,
    )

    full_id = producer.add_full_person(
        store,
        candidate_id=EntityCandidateId("person-full"),
        mention_ids=(full_mention,),
        given_name_lemma="rafał",
        surname_base="krzemień",
        canonical_hint="Rafał Krzemień",
    )
    surname_only_id = producer.add_surname_only_person(
        store,
        candidate_id=EntityCandidateId("person-surname"),
        mention_ids=(surname_mention,),
        canonical_hint="Krzemień",
    )

    proposals = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[surname_only_id]
    )

    assert len(proposals) == 1
    assert proposals[0].left_entity_id == surname_only_id
    assert proposals[0].right_entity_id == full_id


def test_same_name_contrast_context_does_not_confirm_identity() -> None:
    store = ExtractionStore()
    producer = SimpleEntityCandidateProducer()
    sentence_id = _add_sentence(
        store,
        "Jan Kowalski z PO, nie mylić z krakowskim politykiem PiS, Janem Kowalskim.",
    )
    first_mention = _add_mention(store, sentence_id=sentence_id, text="Jan Kowalski", start=0)
    contrast_mention = _add_mention(
        store,
        sentence_id=sentence_id,
        text="Janem Kowalskim",
        start=61,
    )

    first_id = producer.add_full_person(
        store,
        candidate_id=EntityCandidateId("jan-po"),
        mention_ids=(first_mention,),
        given_name_lemma="jan",
        surname_base="kowalski",
        canonical_hint="Jan Kowalski",
    )
    # Contrast contexts intentionally create a separate candidate even with the
    # same full-name key; the resolution scorer must see the contradiction.
    contrast_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("jan-pis"),
            kind=EntityKind.PERSON,
            mention_ids=(contrast_mention,),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("contrast_context_test"),
            blocking_key=None,
            reuse_key=None,
        )
    )

    proposal = EntityCandidateRetriever(store).proposals_for_entity(
        store.entity_candidates[contrast_id]
    )
    assert proposal == ()

    manual_proposal = EntityResolutionProposal(
        left_entity_id=first_id,
        right_entity_id=contrast_id,
        evidence_ids=tuple(
            evidence.id
            for evidence in store.evidence_for_entity(first_id)
            + store.evidence_for_entity(contrast_id)
        ),
    )
    enriched = EvidenceSignalProducer().enrich_resolution_proposal(
        store,
        manual_proposal,
    )
    assert SameNameContradictionSignal() in enriched.context_signals


def test_reference_mentions_are_typed_not_stringly_typed() -> None:
    store = ExtractionStore()
    sentence_id = _add_sentence(
        store,
        "Jan Kowalski pochodzi z Pińczowa. Ten lokalny polityk zatrudnił żonę.",
    )
    evidence_id = EvidenceId("descriptor-evidence")
    store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text="Ten lokalny polityk",
            span=Span(start_char=34, end_char=53),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    reference_id = MentionId("reference-descriptor")
    store.add_reference(
        ReferenceMention(
            id=reference_id,
            text="Ten lokalny polityk",
            kind=ReferenceKind.DESCRIPTOR_NOUN_PHRASE,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
            head_lemma="polityk",
            modifier_lemmas=("lokalny",),
        )
    )

    assert store.references[reference_id].kind is ReferenceKind.DESCRIPTOR_NOUN_PHRASE
    assert store.references_for_sentence(sentence_id) == (store.references[reference_id],)
