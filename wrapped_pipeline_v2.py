from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pipeline_v2.document import PipelineInput
from pipeline_v2.output import document_to_json, document_to_slim_json
from pipeline_v2.runtime import CoreferenceMode, V2PipelineConfig, build_v2_pipeline
from pipeline_v2.types import RelationshipDetail


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
        exclude_relationships: list[RelationshipDetail | str] | None = None,
    ) -> None:

        self.min_confidence = min_confidence
        self.debug_mode = debug_mode
        self.exclude_fact_kinds = exclude_fact_kinds or []
        if exclude_relationships:
            self.exclude_relationships = [str(rel) for rel in exclude_relationships]
        else:
            self.exclude_relationships = []

        coref_enum = CoreferenceMode(coreference_mode)
        provider = None

        if coref_enum == CoreferenceMode.STANZA:
            from pipeline_v2.coreference_provider import StanzaCoreferenceProvider

            provider = StanzaCoreferenceProvider(
                "models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.patched.pt"
            )

        config = V2PipelineConfig(
            spacy_model=spacy_model,
            sentence_transformer_model=sentence_transformer_model,
            coreference_mode=coref_enum,
            coreference_provider=provider,
        )

        self._engine = build_v2_pipeline(config)

    def process_html(self, raw_html: str, source_url: str = "") -> ExtractorOutput | dict:
        pipeline_input = PipelineInput(raw_html=raw_html, source_url=source_url)
        document = self._engine.run_document(pipeline_input)
        
        
        if self.debug_mode:
            return document_to_json(document)
            
        raw_json = document_to_slim_json(document)
        
        fact_objects: List[PoliticalFact] = []
        raw_facts = raw_json.get("facts", [])
        
        
        if isinstance(raw_facts, list):
            for fact_dict in raw_facts:
                
                if not isinstance(fact_dict, dict):
                    continue
                
                confidence = fact_dict.get("confidence", 0.0)
                
                if not isinstance(confidence, (int, float)) or confidence < self.min_confidence:
                    continue
                    
                kind = fact_dict.get("kind")
                if self.exclude_fact_kinds and kind in self.exclude_fact_kinds:
                    continue
                
                rel_detail = fact_dict.get("relationship_detail")
                if self.exclude_relationships and rel_detail in self.exclude_relationships:
                    continue
                
               
                filtered_fact_dict = {
                    str(k): v for k, v in fact_dict.items() 
                    if isinstance(k, str) and k in PoliticalFact.__dataclass_fields__
                }
                fact_objects.append(PoliticalFact(**filtered_fact_dict))
        
       
        url_val = raw_json.get("url", source_url)
        relevant_val = raw_json.get("relevant", False)
        score_val = raw_json.get("relevance_score", 0.0)
        title_val = raw_json.get("title")
        date_val = raw_json.get("publication_date")

        output_object = ExtractorOutput(
            url=str(url_val) if url_val is not None else source_url,
            relevant=bool(relevant_val),
            relevance_score=float(score_val) if isinstance(score_val, (int, float)) else 0.0,
            title=str(title_val) if title_val is not None else None,
            publication_date=str(date_val) if date_val is not None else None,
            facts=fact_objects
        )
        
        return output_object
