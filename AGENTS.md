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
