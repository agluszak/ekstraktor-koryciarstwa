# V2 Governance And Referral Grounding Follow-Up - 2026-05-26

## Changes

- Governance no longer drops implausible PERSON fillers inside the producer. It emits the binding with an `ImplausiblePersonBindingSignal`, and inference suppresses that filler through role compatibility.
- NER reclassifies PERSON spans with stable organization suffix tokens such as `OFE` as organizations. This fixed the observed `Allianza OFE` person leak without listing the article-specific name.
- Anti-corruption referrals now keep multiple plausible local target candidates after the oversight institution instead of selecting only the nearest one in the producer.

## Validation

- `uv run ruff check pipeline_v2 tests_v2 --fix`
- `uv run ruff format pipeline_v2 tests_v2`
- `uv run ruff check pipeline_v2 tests_v2`
- `uv run ty check`
- `uv run pytest -c pytest-v2.ini -q` -> 255 passed
- `uv run extractor-v2 --input-dir inputs --glob "*.html" --output-dir output/v2_plan_run_20260526`

## Output Check

- Fresh batch: 33 output docs, 486 materialized facts.
- No fresh output fact used `Allianza OFE` as `person`, `complainant`, or `target`.
- Anti-corruption referral variants still remain in the Bytom-style article. The remaining issue is not candidate visibility but target/context ranking and same-event grouping.

## Remaining Work

- Governance still contains substantial producer-side role/person/organization selection logic. This should be converted into role-binding candidates plus typed factors in a larger pass.
- Anti-corruption investigation target selection is still nearest-only.
- `FactPriorPolicy` and materialization still contain scorer/projection policy that should move toward composable factor families.
