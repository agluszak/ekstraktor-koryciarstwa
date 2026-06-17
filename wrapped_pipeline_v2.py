from __future__ import annotations

from pipeline_v2.runtime import V2PipelineConfig, build_v2_pipeline, CoreferenceMode
from pipeline_v2.document import PipelineInput
from pipeline_v2.output import document_to_slim_json, document_to_json

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

    def process_html(self, raw_html: str, source_url: str = "") -> dict:
        pipeline_input = PipelineInput(raw_html=raw_html, source_url=source_url)
        document = self._engine.run_document(pipeline_input)
        
        if self.debug_mode:
            return document_to_json(document)
            
        raw_json = document_to_slim_json(document)
        
        filtered_facts = []
        for fact in raw_json.get("facts", []):
            # 1. Filtrowanie po pewności (Confidence filter)
            if fact.get("confidence", 0.0) < self.min_confidence:
                continue
                
            # 2. Wykluczanie typów faktów (Fact kinds blacklist)
            if fact.get("kind") in self.exclude_fact_kinds:
                continue
            
            # 3. Wykluczanie detali relacji (Relationships blacklist)
            if self.exclude_relationships:
                rel_detail = fact.get("relationship_detail")
                if rel_detail and rel_detail in self.exclude_relationships:
                    continue
            
            filtered_facts.append(fact)
        
        raw_json["facts"] = filtered_facts
        return raw_json