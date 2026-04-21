import sys
from pipeline.config import PipelineConfig
from pipeline.runtime import PipelineRuntime
from pipeline.syntax import StanzaClauseParser
from pipeline.models import ArticleDocument
from pipeline.segmentation.service import ParagraphSentenceSegmenter

text = (
    "A. Góralczyk, działaczka PSL, pracowała wcześniej w urzędzie. "
    "Teraz awansowała na stanowisko zastępcy prezesa. "
    "Chodzi o Stadninę Koni Iwno."
)

config = PipelineConfig.from_file("config.yaml")
runtime = PipelineRuntime(config)

doc = ArticleDocument(
    document_id="doc1",
    source_url=None,
    raw_html="",
    title="",
    publication_date=None,
    cleaned_text=text,
    paragraphs=[text]
)
doc = ParagraphSentenceSegmenter(config).run(doc)
doc = StanzaClauseParser(config, runtime).run(doc)

for clause in doc.clause_units:
    if clause.sentence_index == 1:
        print(f"Clause 1 bounds: {clause.start_char} - {clause.end_char}")
        for w in doc.parsed_sentences[clause.sentence_index]:
            print(f"  {w.text} ({w.lemma}) [{w.start}-{w.end}]")
