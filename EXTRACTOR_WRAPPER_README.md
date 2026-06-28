# ExtractorWrapper

A convenient, high-level Python wrapper for the `pipeline_v2` NLP extraction engine. 

`ExtractorWrapper` optimizes resource usage by loading heavy ML models (spaCy, Stanza) only once upon instantiation. It provides an easy-to-use interface to process raw HTML articles into structured JSON data, while allowing you to easily blacklist unwanted facts and relationships using simple Python lists.

## Parameters

* `min_confidence` *(float, default: 0.5)*: The minimum probability score required for a fact to be included in the output. Facts below this threshold are discarded.
* `debug_mode` *(bool, default: False)*: If set to `True`, the pipeline outputs the full, detailed graph JSON. If `False`, it outputs a slimmed-down, highly readable JSON summary.
* `coreference_mode` *(str, default: "off")*: Controls the coreference resolution engine. Options: `"off"`, `"light"`, `"stanza"`. *(Note: "stanza" requires significant RAM).*
* `spacy_model` *(str, default: "pl_core_news_lg")*: The spaCy model used for Named Entity Recognition (NER).
* `sentence_transformer_model` *(str | None, default: None)*: Optional embeddings model for semantic search enrichment.
* `exclude_fact_kinds` *(list[str] | None, default: None)*: A blacklist of main fact categories (e.g., `["public_contract", "funding"]`). Facts matching these kinds will not appear in the final output. List of possible values in pipeline_v2/types.py.
* `exclude_relationships` *(list[str] | None, default: None)*: A blacklist of specific relationship details (e.g., `["friend", "associate"]`). Any tie fact containing these specific relationship subtypes will be excluded. List of possible values in pipeline_v2/catalogues.py.

## Usage Example

```python
from wrapped_pipeline_v2 import ExtractorWrapper
import json

# 1. Initialize the pipeline once (this loads the heavy models)
# We decide to exclude public contracts, public employment and loose friendships.
pipeline = ExtractorWrapper(
    min_confidence=0.75,
    exclude_fact_kinds=["public_contract","public_employment"], 
    exclude_relationships=["friend", "associate"]
)

# 2. Read your raw HTML
raw_html_content = "<html>...wójt zatrudnił brata...</html>"

# 3. Process the text
result_json = pipeline.process_html(
    raw_html=raw_html_content, 
    source_url="[https://example.com/article](https://example.com/article)"
)

# 4. Print or save the filtered results
print(json.dumps(result_json, ensure_ascii=False, indent=2))