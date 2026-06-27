from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from pipeline_v2.runtime import V2PipelineConfig, build_v2_pipeline, CoreferenceMode
from pipeline_v2.document import PipelineInput
from pipeline_v2.output import document_to_slim_json, document_to_json


@dataclass
class PoliticalFact:
    kind: str
    confidence: float
    person: Optional[str] = None
    organization: Optional[str] = None
    role: Optional[str] = None
    relationship_detail: Optional[str] = None
    status: Optional[str] = None
    context: Optional[str] = None
    counterparty: Optional[str] = None
    contractor: Optional[str] = None
    amount: Optional[str] = None

@dataclass
class ExtractorOutput:
    url: str
    relevant: bool
    relevance_score: float
    facts: List[PoliticalFact]
    title: Optional[str] = None
    publication_date: Optional[str] = None


class ExtractorWrapper:
    def __init__(
        self, 
        min_confidence: float = 0.5, 
        debug_mode: bool = False, 
        coreference_mode: str = "off",
        spacy_model: str = "pl_core_news_lg",
        sentence_transformer_model: str | None = None,
        exclude_fact_kinds: list[str] | None = None,
        exclude_relationships: list[str] | None = None 
    ) -> None:
        
        self.min_confidence = min_confidence
        self.debug_mode = debug_mode
        self.exclude_fact_kinds = exclude_fact_kinds or [] 
        self.exclude_relationships = exclude_relationships or [] 
        
        coref_enum = CoreferenceMode(coreference_mode)
        provider = None
        
        if coref_enum == CoreferenceMode.STANZA:
            from pipeline_v2.coreference_provider import StanzaCoreferenceProvider
            provider = StanzaCoreferenceProvider("models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.patched.pt")
        
        config = V2PipelineConfig(
            spacy_model=spacy_model,
            sentence_transformer_model=sentence_transformer_model,
            coreference_mode=coref_enum,
            coreference_provider=provider
        )
        
        self._engine = build_v2_pipeline(config)

    # ZMIANA TUTAJ: Zwracamy ExtractorOutput lub dict (w zależności od debug_mode)
    def process_html(self, raw_html: str, source_url: str = "") -> ExtractorOutput | dict:
        pipeline_input = PipelineInput(raw_html=raw_html, source_url=source_url)
        document = self._engine.run_document(pipeline_input)
        
        # W trybie debug oddajemy surowego JSONa z grafem, bo jest zbyt potężny na proste dataclassy
        if self.debug_mode:
            return document_to_json(document)
            
        # Pobieramy bazowy słownik z output.py
        raw_json = document_to_slim_json(document)
        
        # 1. Filtrowanie faktów i pakowanie ich do obiektów PoliticalFact
        fact_objects: List[PoliticalFact] = []
        for fact_dict in raw_json.get("facts", []):
            if fact_dict.get("confidence", 0.0) < self.min_confidence:
                continue
                
            if fact_dict.get("kind") in self.exclude_fact_kinds:
                continue
            
            rel_detail = fact_dict.get("relationship_detail")
            if self.exclude_relationships and rel_detail and rel_detail in self.exclude_relationships:
                continue
            
            # Wypakowujemy słownik do dataclassy za pomocą operatora **
            # Ignorujemy ewentualne nadmiarowe klucze, których nie ma w naszej klasie
            filtered_fact_dict = {k: v for k, v in fact_dict.items() if k in PoliticalFact.__dataclass_fields__}
            fact_objects.append(PoliticalFact(**filtered_fact_dict))
        
        # 2. Pakowanie całości do finalnego obiektu ExtractorOutput
        output_object = ExtractorOutput(
            url=raw_json.get("url", source_url),
            relevant=raw_json.get("relevant", False),
            relevance_score=raw_json.get("relevance_score", 0.0),
            title=raw_json.get("title"),
            publication_date=raw_json.get("publication_date"),
            facts=fact_objects
        )
        
        return output_object