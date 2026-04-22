# Full Benchmark Report - 2026-04-22

## Overview
This report evaluates the performance of the Extraction Pipeline against a set of 21 Polish articles. The evaluation compares actual JSON output against manual expectations and integration test assertions.

## Statistics
- **Total Articles processed:** 21
- **Relevance Accuracy:** 90% (19/21)
- **Fact Extraction Recall (Major Facts):** ~75%

## Detailed Analysis

### 1. Notable Successes
- **Totalizator Sportowy (Onet):** Successfully extracted a large network of appointments and party ties. Demonstrated robustness in handling many entities in one document.
- **Sylwia Sobolewska (WP/Onet):** Correctly identified the "wife" (tie) relationship and several board appointments/dismissals.
- **Pleszew Stadnina (Pleszew24):** Correctly identified both the appointment and the dismissal of the predecessor.

### 2. Known Issues & Gaps
- **Lemmatization Artifacts:** Names ending in `-ska` or simple short surnames like `Bury` sometimes result in broken lemmas ("Giermasińk", "Bure").
- **Missing Ties in Complex Sentences:** The "Marta Giermasińska - Dariusz Klimczak" (fiancée) link was missed. Investigation shows that the dependency parser or the cross-sentence extractor is not yet robust enough for this specific phrasing.
- **Relevance Scoring Jitter:** `wiadomosci.onet.pl__lublin...` was scored 0.2 (irrelevant) while `onet_wfosigw_lublin.html` (same content) was 1.0. This suggests the cleaner text or different HTML structure impacts the keyword density or NER confidence.
- **Role Value Extraction:** Appointment roles (e.g., "wiceprezes") are sometimes missed if they aren't in a direct dependency relationship with the verb that the extractor expects.

## Comparison with `tests/integration/test_benchmark.py`

| Test Case | Integration Test Status | Manual Run Observation |
| :--- | :--- | :--- |
| `test_wp_lubczyk` | PASS (Partial targets xfail) | Matches. Hołownia found, Sejm found. |
| `test_onet_totalizator` | PASS (Targets passing) | Strong performance. Extracted multiple directors. |
| `test_pleszew24_stadnina` | PASS | Matches. Góralczyk/Pacia facts extracted. |
| `test_rp_klich` | PASS (Targets partial) | Klich-Hodura tie found. Appts weak. |
| `test_wfosigw_lublin_xfail` | XFAIL | CONFIRMED: One version of input fails relevance. |

## Synthesized Areas for Improvement

### A. High Fidelity Lemmatization Fallback
Implement a "majority vote" or "nominative preference" for lemmas. If Stanza returns "Bure" but the text has "Bury" (Nom), we should stick to the Nominative surface form. (Partially implemented, needs refinement).

### B. Dependency-Agile Role Extraction
The current `has_governance_verb_with_role` relies on specific `obj/xcomp` relations. Phrasings like "objął funkcję wiceprezesa" where "wiceprezesa" is a `nmod` of "funkcję" might be missed. We need to traverse deeper or use a broader role-search window near governance verbs.

### C. Strengthening Interpersonal Tie Extractor
Improve the `_cross_sentence_kinship_ties` to look for "anchors" (newly introduced persons) relative to "known persons" in the paragraph, even if they aren't in adjacent sentences, using coreference more aggressively.

### D. Relevance Scoring Refinement
Move away from raw keyword counts to a more structural approach that weights the co-occurrence of a `Person`, a `Company/Board marker`, and an `Appointment verb` within the same or adjacent sentences.
