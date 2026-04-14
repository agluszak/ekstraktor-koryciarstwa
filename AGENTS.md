# Repository Instructions

- Use direct execution now that full access is available.
- If a task starts needing environment or sandbox workarounds, stop and notify the user instead of adding a workaround.
- When lint or formatting tools support autofix, run the autofix path first and only do manual cleanup for remaining issues.

# Project Context

This repository houses an information extraction pipeline ("ekstraktor-koryciarstwa") focused on analyzing Polish news articles. Its primary domain is monitoring "koryciarstwo" / public money extraction: nepotism, patronage, appointments to state-owned companies, and the flow of public funds.

## Domain Model
The pipeline extracts specific entities, relations, and events from text, using tools like spaCy NER and Stanza parsing. Key concepts include:
- **Entities**: People, Organizations (state-owned enterprises, public institutions, municipal utilities), Political Parties (e.g., KO, PO, PSL, Lewica, Polska 2050, PiS), Roles/Positions, and Salary figures.
- **Relations & Events**:
  - `APPOINTED_TO` / `MEMBER_OF_BOARD` / `HOLDS_POSITION_AT`: Tracking governance changes and new board members.
  - `DISMISSED_FROM`: Removals from management or supervisory boards.
  - `AFFILIATED_WITH_PARTY`: Direct political party affiliations.
  - `RELATED_TO`: Acquaintances, family ties, and patronage networks.

## Benchmarks and Evaluation
The `reports/` folder contains benchmark files (e.g., `expected_article_findings.md` and progress tracking reports) used to evaluate pipeline extraction quality. They document:
- Expected extraction scenarios for various high-signal articles (like appointments without competition, party-affiliated staffing in public trusts or utilities).
- True negative examples that should not trigger extraction (e.g., generic legal analysis or international news).
- Current parsing performance metrics, issues (like false-positive relations or noisy entity spans), and immediate focus areas for improvement.

Always consult the benchmark reports when modifying extraction rules or parsing logic to ensure changes align with expected outcomes and to avoid regressions.

## Regression Testing Workflow

When extraction, preprocessing, linking, scoring, or output logic changes:

1. Read [reports/expected_article_findings.md](/D:/extractor/reports/expected_article_findings.md:1) first.
   Use it as the manual oracle for what each benchmark article should and should not produce.

2. Run the automated checks first:
   - `uv run ruff check . --fix`
   - `uv run ruff format .`
   - `uv run ruff check .`
   - `uv run ty check`
   - `uv run pytest`

3. Rerun the benchmark HTML inputs in one warm process:
   - `uv run python main.py --input-dir inputs --glob "*.html" --output-dir output`
   Prefer batch mode so spaCy/Stanza load once.

4. Compare outputs against the benchmark report, especially for:
   - strong positives that should yield appointments / dismissals / funding / compensation
   - true negatives that should stay irrelevant or relation-empty
   - high-risk regressions such as party mentions becoming appointment destinations, bad person merges, or boilerplate/comment entities leaking in

5. If extraction behavior changed materially, update the progress snapshot in `reports/` with:
   - what improved
   - what regressed
   - which benchmark articles were checked
   - which bottleneck is next

Do not treat `pytest` success as sufficient for extraction changes. The checked-in benchmark report is part of regression testing and must be consulted after significant pipeline changes.
