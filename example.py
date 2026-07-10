import json

from pipeline_v2.cli import fetch_html
from wrapped_pipeline_v2 import ExtractorWrapper

URL = "https://tvn24.pl/tvnwarszawa/srodmiescie/warszawa-zmiany-w-radach-nadzorczych-miejskich-szpitali-kto-stracil-stanowisko-lista-st9108816"

# 1. Initialize the pipeline once (this loads the heavy models)
# We decide to exclude public contracts, public employment and loose friendships.
pipeline = ExtractorWrapper(
    min_confidence=0.75,
    exclude_fact_kinds=["public_contract", "public_employment"],
    exclude_relationships=["friend", "associate"],
)

# 2. Read your raw HTML
raw_html_content = fetch_html(URL)

# 3. Process the text
result_json = pipeline.process_html(
    raw_html=raw_html_content,
    source_url=URL,
)

# 4. Print or save the filtered results
print(json.dumps(result_json, ensure_ascii=False, indent=2))
