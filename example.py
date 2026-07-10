import json

from wrapped_pipeline_v2 import ExtractorWrapper

# 1. Initialize the pipeline once (this loads the heavy models)
# We decide to exclude public contracts, public employment and loose friendships.
pipeline = ExtractorWrapper(
    min_confidence=0.75,
    exclude_fact_kinds=["public_contract", "public_employment"],
    exclude_relationships=["friend", "associate"],
)

# 2. Read your raw HTML
raw_html_content = "<html>...wójt zatrudnił brata...</html>"

# 3. Process the text
result_json = pipeline.process_html(
    raw_html=raw_html_content,
    source_url="[https://example.com/article](https://example.com/article)",
)

# 4. Print or save the filtered results
print(json.dumps(result_json, ensure_ascii=False, indent=2))
