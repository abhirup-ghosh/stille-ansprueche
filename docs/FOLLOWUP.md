# Follow-up notes

Tracks items outside `PLAN.md`'s scope: things to verify later (**FOLLOWUP CHECKS**) and work
deliberately deferred (**OUT-OF-SCOPE**). Both categories are to be revisited only after
`PLAN.md` has been fully implemented (all 8 phases done), not during the phased build-out.

## FOLLOWUP CHECKS AND FUTURE IMPROVEMENTS

- Verify that the ifo-institute/sozialleistungen inventory (Phase 1a source, 502 entries) is
  actually complete — independently research and cross-check whether there are well-known German
  Sozialleistungen missing from it. Do this only after PLAN.md is fully implemented.

- Try to increase portal enrichment coverage beyond the Phase 1b result (49/502 benefits
  enriched from sozialplattform.de + familienportal.de). Ideas to explore: more source
  websites beyond the two pinned in PLAN.md, deep crawling (following in-page links rather
  than only sitemap-listed URLs), broader/fuzzier candidate-matching heuristics. Do this only
  after PLAN.md is fully implemented.

- Once PLAN.md is fully implemented end-to-end, revisit every metric/KPI logged below and look
  for ways to push each one higher (better retrieval strategy/fusion weighting, richer corpus
  from more enrichment, better prompts, etc.). Baseline values, as measured during the phased
  build-out, for comparison against future attempts:

  **Retrieval (Phase 3, `data/eval/retrieval_results.csv`, 1000 ground-truth questions, 800 de /
  200 en)** — all-language row per strategy:
  | strategy | hit_rate@5 | mrr@5 | hit_rate@10 | mrr@10 |
  |---|---|---|---|---|
  | text (BM25) | 0.046 | 0.025 | 0.107 | 0.033 |
  | **vector (winner, = `search_best`)** | **0.282** | **0.173** | **0.399** | **0.189** |
  | hybrid (RRF) | 0.217 | 0.125 | 0.338 | 0.140 |
  | hybrid_rerank | 0.276 | 0.164 | 0.378 | 0.178 |
  | hybrid_rewritten | 0.261 | 0.145 | 0.375 | 0.160 |

  **RAG / LLM evaluation (Phase 4, `data/eval/rag_results.csv`, 100 questions x 3 variants,
  judged by relevance + faithfulness LLM judges)**:
  | variant | %relevant | %faithful | mean_sentence_len |
  |---|---|---|---|
  | baseline | 91.0% | 41.0% | 14.2 |
  | **einfache_sprache (winner, = `PROMPT_VBEST`)** | 87.0% | **57.0%** | 6.1 |
  | structured | 80.0% | 36.0% | 17.2 |

  **Corpus (Phases 1a-1c)**: 502 ifo benefit records parsed; 49/502 (9.8%) enriched with
  plain-language portal text; 502 documents in the final corpus (no chunking triggered — max
  composed text length 4555 chars, under the 6000-char threshold).

  **Cost so far**: ground truth generation $0.026, retrieval eval (query rewriting) $0.045, RAG
  eval (answers + judges) $0.18 — cumulative well under the project's ~$3 budget.

## OUT-OF-SCOPE

(none yet)
