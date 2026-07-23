# Project Evaluation — Stille Ansprüche

Maps this project against the official DataTalksClub LLM Zoomcamp rubric
(https://github.com/abhirup-ghosh/llm-zoomcamp/blob/main/project.md, "Evaluation Criteria"
section), so a reviewer can verify each point claimed in under a minute without re-deriving it.
Every "Evidence" cell points at a specific file/path in this repo. Every claim below was checked
against the actual repo state before writing it.

## Core criteria

| Criterion | Points claimed | Max | Evidence |
|---|---|---|---|
| **Problem description** | 2 | 2 | README "Problem" section: the non-take-up problem, documented numbers, why RAG (discovery gap not calculation gap), differentiation from CityLAB Berlin's Beyond Forms. |
| **Retrieval flow** (both a knowledge base and an LLM used) | 2 | 2 | `src/search.py` (Qdrant retrieval) feeds `src/rag.py`, which calls OpenAI `gpt-4o-mini` for generation. Both used in every answer — see `RagAnswer` / `answer()` in `src/rag.py`. |
| **Retrieval evaluation** (multiple approaches evaluated, best one used) | 2 | 2 | 5 strategies (`text`, `vector`, `hybrid`, `hybrid_rerank`, `hybrid_rewritten`) evaluated in `src/eval_retrieval.py` over 1000 ground-truth questions → `data/eval/retrieval_results.csv`. Winner (`vector`) is wired in as `search_best` in `src/search.py` and used by `src/rag.py`. README "Retrieval evaluation" section has the full table + interpretation. |
| **LLM evaluation** (multiple approaches evaluated, best one used) | 2 | 2 | 3 prompt variants (`baseline`, `einfache_sprache`, `structured`) evaluated in `src/eval_rag.py` over 300 (question, variant) pairs with relevance + faithfulness LLM judges → `data/eval/rag_results.csv`. Winner (`einfache_sprache`) is wired in as `PROMPT_VBEST` in `src/rag.py`. README "RAG evaluation" section has the full table + interpretation. |
| **Interface** | 2 | 2 | `app/app.py` — a Streamlit chat UI (not just a script/notebook): chat history, sidebar controls, source citations, 👍/👎 feedback. Verified working end-to-end in a real browser (see `docs/PROGRESS.md` Phase 5/7). |
| **Ingestion pipeline** (automated, Python script) | 2 | 2 | `src/ingest_ifo.py` → `src/enrich_portals.py` → `src/build_corpus.py`, fully automated via `make ingest`, idempotent (safe to re-run, caches network responses). No manual/notebook steps required. |
| **Monitoring** (feedback collected AND dashboard with ≥5 charts) | 2 | 2 | 👍/👎 feedback → Postgres `feedback` table (`src/db.py`, `app/app.py`). Grafana dashboard (`grafana/dashboards/stille.json`) has **8** panels (see README "Monitoring" + `docs/screenshot_grafana.png`), exceeding the ≥5 bar. |
| **Containerization** (everything in docker-compose) | 2 | 2 | `docker-compose.yml`: `qdrant`, `postgres`, `grafana`, and `app` (built from the repo's own `Dockerfile`) — all 4 services. The two one-shot operations needed after `make up` (indexing, demo seeding) also run inside the `app` container via `docker compose run` (`make index-docker`, `make seed`); only the one-time data-pipeline scripts (ingestion, ground-truth generation, evaluation — run once by the author to produce the committed `data/` artifacts, not needed by a reviewer) run via a local venv (`make ingest`, `make ground-truth`, etc.). |
| **Reproducibility** (clear instructions, dataset accessible, easy to run, dependency versions pinned) | 2 | 2 | `requirements.txt` pinned to exact installed versions (`pip freeze`). `data/documents.jsonl`, `data/ground_truth.jsonl`, and both eval CSVs are committed (not regenerated-only). README "How to run" gives the exact commands, **literally rehearsed from a fresh `git clone` in an empty directory three times** until it passed clean (see `docs/PLAN.md`'s Phase 7 section for the 3 bugs that rehearsal caught: a nested-read-only-mount issue, `make seed` assuming a local venv, and `docker compose up` reusing a stale image). |
| **Core subtotal** | **18** | **18** | |

## Best practices (bonus)

| Practice | Claimed? | Points | Evidence |
|---|---|---|---|
| Hybrid search (text + vector, at least evaluated) | Yes | 1 | `search_hybrid()` in `src/search.py` (Qdrant Query API, dense + BM25 sparse prefetch, RRF fusion); evaluated as its own strategy in `data/eval/retrieval_results.csv`. |
| Document re-ranking | Yes | 1 | `search_hybrid_rerank()` in `src/search.py` — CrossEncoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) reranks the top-20 hybrid candidates; evaluated as its own strategy. |
| User query rewriting | Yes | 1 | `rewrite_query()` in `src/search.py` — LLM-based translation-to-German + Amtsdeutsch term expansion (langdetect-gated); evaluated as `hybrid_rewritten` in `data/eval/retrieval_results.csv`. |
| **Best-practices subtotal** | | **3** | |

## Bonus points

| Item | Claimed? | Points | Notes |
|---|---|---|---|
| Deployment to the cloud | No | 0 / 2 | Out of scope for this submission — runs locally / via `docker-compose` only. |
| Extra bonus (up to 3) | Reviewer's discretion | 0–3 | Candidates worth considering, not presumptuously claimed here: (1) cross-lingual retrieval evaluation (every strategy reported separately for German vs. English questions, not just aggregate — see README "Retrieval evaluation"); (2) the retrieval result itself is an honest, interpreted *negative* finding (plain vector search beats hybrid/rerank/rewrite) with root-cause analysis, rather than only reporting whichever number is highest; (3) the fresh-clone reproducibility rehearsal was run three times to convergence and every bug it found is documented with root cause directly in `docs/PLAN.md` (each phase section notes what actually happened), not just silently fixed. |

## Total claimed: 21 / 21 core+best-practice (+ 0–3 possible extra bonus, reviewer's discretion)

---

*Methodology note: every "Evidence" cell above names a file that exists in this repo at the time
of writing and was checked against its actual content (not assumed from memory) — see
`docs/PROGRESS.md` for the phase-by-phase build log this table is derived from.*
