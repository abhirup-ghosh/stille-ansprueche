# Progress Log

- 2026-07-21: Phase 0 — repository bootstrap complete. Repo structure created, venv (Python
  3.11.15 via Homebrew) + requirements.txt installed, `src/config.py` and `src/llm.py` written,
  Makefile stubs in place, initial README written.
- 2026-07-21: Phase 1a — ifo inventory ingestion complete. Downloaded
  ifo-institute/sozialleistungen (main branch, CC-BY-SA-4.0), parsed the single
  `sozialleistungen.yml` (21 law books, 502 entries) into `data/ifo/benefits_parsed.jsonl`.
  Actual schema matched the plan's sketch closely (`leistung`, `rechtsnorm`, `zielgruppen`,
  `themenfelder`); `name` extracted as the text before the first `.`/`,` in `leistung`
  (confirmed "Wohngeld" splits out cleanly for the Phase 2 smoke test). All 502 records unique,
  no empty required fields.
- 2026-07-21: Phase 1b — portal enrichment complete (best effort). sozialplattform.de's own
  `/sitemap.xml` lists 5138 URLs and familienportal.de's sitemap.xml 404s (its real sitemap
  index is named in robots.txt, one gzipped child sitemap, 127 URLs) — both filtered down to
  117 candidates via the benefit-name-token heuristic before fetching anything. Politeness:
  custom User-Agent, sozialplattform.de's robots.txt Crawl-delay:10 honored via
  `urllib.robotparser`, every response cached under `data/raw_html/`. Result: 83 usable pages
  extracted, 49/502 benefits enriched (well above the plan's ≥30 success bar). Re-running the
  script is fully cached (~2s, all cache hits, identical output).
- 2026-07-21: Phase 1c — final corpus built. Joined ifo records with enrichment into
  `data/documents.jsonl`: 502 documents (all one chunk each — max composed text length was
  4555 chars, under the 6000-char chunking threshold, so the chunker's split path is currently
  untested on real data but covered by a synthetic unit test). 49/502 (9.8%) enriched. All
  documents JSON-parse back into `Document`, no empty text, no duplicate ids.
- 2026-07-21: Phase 2 — Qdrant indexing + five search modes complete. Added `qdrant` service to
  `docker-compose.yml` (Docker Desktop wasn't running locally; started it). Dense embeddings via
  `sentence-transformers` (`intfloat/multilingual-e5-small`, MPS device, "query: "/"passage: "
  prefixes) and sparse BM25 via `fastembed` (`Qdrant/bm25`) computed client-side (not via Qdrant
  server-side inference) and stored as named vectors `dense`/`bm25`. Qdrant point ids are
  `uuid5`-derived from each document's slug id (Qdrant requires uint/UUID point ids; the
  original id stays in the payload). `make index` → 502/502 points, confirmed idempotent via
  `--keep`. All 5 `src/search.py` functions (`search_text`, `search_vector`, `search_hybrid`,
  `search_hybrid_rerank`, `search_hybrid_rewritten` + `rewrite_query`) implemented with lazy
  singleton model loading; smoke test (Wohngeld for a rent-subsidy query) passes and skips
  cleanly when Qdrant is down (verified both ways). `search_hybrid_rerank` warm-state latency
  ~0.2s per query (well under the 3s bar) — the first call in a process pays one-time model-load
  cost (~30s), which is expected given lazy loading.
- 2026-07-22: Phase 3 — ground truth + retrieval evaluation complete. Generated 1000 questions
  (800 de / 200 en) from 200 sampled documents (49 enriched + 151 random ifo-only, seed 42),
  cost $0.026. Evaluated all 5 strategies over all 1000 questions (Hit Rate@5/10, MRR@5/10, split
  de/en/all — 15-row `data/eval/retrieval_results.csv`), cost $0.045 for `hybrid_rewritten`'s
  per-question LLM rewrite calls. Refactored the naive first draft of `eval_retrieval.py` before
  running it at full scale: it was calling every search function 2x per question (once for the
  "de"/"en" split, again for "all", which is just their union) — fixed to search once per
  question and slice results into subsets, avoiding wasted Qdrant/CrossEncoder/LLM work.
  **Result: plain `search_vector` wins (MRR@5=0.173 all-lang)**, beating `hybrid` (0.125),
  `hybrid_rerank` (0.164), and `hybrid_rewritten` (0.145) — `search_best` in `src/search.py`
  updated accordingly. Root cause: the ground-truth questions are deliberately phrased without
  the benefit's official name, so BM25 (`text` strategy, MRR@5=0.025) contributes mostly noise,
  and naive RRF fusion in `hybrid` lets that noise drag vector-only performance down; reranking
  recovers most but not all of the gap. Full interpretation in README "Retrieval evaluation".
