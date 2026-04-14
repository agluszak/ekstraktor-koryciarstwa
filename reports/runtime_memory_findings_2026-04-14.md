# Runtime Memory Findings - 2026-04-14

This note records the investigation into the severe slowdown and RAM/pagefile blow-up
seen when running multiple relevant articles in one warm process.

## Summary

The main runtime problem is localized to the `Stanza` coreference path.

It is not primarily caused by:
- `--input-dir` or `--output-dir`
- output writing
- the batch runner itself

It is also not explained by "all articles together are mysteriously slower".
Some articles are individually heavy, but the much worse multi-article behavior comes
from memory retained by the long-lived coref pipeline.

## Confirmed Timing Findings

After the syntax regression fix, the dominant costs on relevant articles are:

- `spaCy NER`: article-wide, moderate cost
- `Stanza coref`: article-wide, very high cost
- `relations`: moderate-to-high cost, but no longer the main regression

Measured examples:

- `radomszczanska`
  - total: about `23-35s`
- `wfosigw`
  - total: about `23-32s`
- `sloma`
  - total: about `4-5s`
- `totalizator`
  - total: about `64s`
- `niezalezna`
  - total: about `111s`
- `oko`
  - total: about `34s`

So long benchmark runs are partly explained by some very heavy single articles.

## Confirmed Memory Findings

Measured on one article in one process:

- process start: about `436 MB`
- after preprocessing / segmentation: about `468 MB`
- after `spaCy NER`: about `1.26 GB`
- after current `Stanza coref`: about `6.10 GB`
- after relations: about `6.41 GB`
- after `gc.collect()`: still about `6.41 GB`

This shows the memory blow-up happens before relation extraction and is not released by normal Python GC.

## Coref-Specific Findings

### 1. Stanza coref prediction currently runs with autograd effectively on

Direct inspection showed that prediction tensors from the current coref path have:

- `coref_scores.requires_grad == True`
- `zero_scores.requires_grad == True`

That strongly suggests the upstream Stanza coref processor is calling model prediction
without `torch.no_grad()` / `torch.inference_mode()`.

### 2. Wrapping coref in `torch.inference_mode()` helps materially

Direct coref-call measurement with `torch.inference_mode()`:

- after coref pipeline load: about `1.39 GB`
- after coref inference: about `2.66 GB`

This is a major improvement over the earlier `6+ GB` behavior.

### 3. Inference mode alone does not fully solve retained memory across articles

Warm multi-article run with `torch.inference_mode()` still showed retained RSS such as:

- after `radomszczanska`: about `3.73 GB`
- after `wfosigw`: about `4.31 GB`
- after `sloma`: about `4.36 GB`

So inference mode reduces the spike, but the long-lived reused coref pipeline still retains too much memory.

### 4. Releasing the coref pipeline object frees a large chunk of memory

When the entire Stanza coref pipeline object is deleted, memory drops substantially.

When only the cached coref pipeline is reset between articles:

- after `radomszczanska` coref reset: about `2.01 GB`
- after `wfosigw` coref reset: about `2.69 GB`
- after `sloma` coref reset: about `2.70 GB`

This indicates the bad retention is specifically tied to keeping the coref pipeline alive across multiple articles.

## Configuration Probe

Current Stanza coref settings observed in runtime:

- `a_scoring_batch_size = 128`
- `bert_window_size = 512`
- `use_zeros = True`

Lowering `coref_batch_size` alone did not materially change peak inference RSS enough
to be the main fix.

## Conclusions

1. `Stanza coref` is the main memory culprit.
2. The current integration should wrap coref inference in `torch.inference_mode()`.
3. Keeping the same coref pipeline alive across many articles causes unacceptable RAM retention.
4. The most practical fix is:
   - run coref under inference mode
   - reset/rebuild only the coref pipeline between articles
   - keep `spaCy` and `Stanza` syntax warm

## Already Fixed Separately

The earlier syntax regression is already fixed:

- relation extraction now parses Stanza syntax once per document, not once per sentence

That reduced relation-stage runtime materially, but it did not address the coref memory problem.
