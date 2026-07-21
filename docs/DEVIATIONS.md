# Deviations from PLAN.md

- **Phase 0:** `pytest` exits with code 5 ("no tests collected") when the `tests/` directory
  contains only empty placeholder files, which `make` treats as a failure. The `test` Makefile
  target now treats exit code 5 as success. This only applies while test files are empty; once
  Phase 1 adds real tests to `tests/test_corpus.py`, normal pytest exit codes (0 on pass, 1 on
  failure) apply and this special-case is inert.

- **Instruction outside PLAN.md (provided directly by the human, before Phase 1b):**
  1. `docs/` was created at repo root and `DEVIATIONS.md`, `PLAN.md`, and `PROGRESS.md` were
     moved there (`docs/DEVIATIONS.md`, `docs/PLAN.md`, `docs/PROGRESS.md`), overriding
     PLAN.md §3's repo layout which places them at root. `docs/PLAN.md` was initially kept
     gitignored per an earlier instruction, but the human later changed their mind — it is now
     committed like every other planning doc.
  2. `docs/FOLLOWUP.md` was created to track two kinds of items outside PLAN.md's scope:
     **FOLLOWUP CHECKS** (things to verify later) and **OUT-OF-SCOPE** (deferred work). Both are
     to be revisited only after PLAN.md is fully implemented (i.e. after Phase 8).

- **Phase 2:** two small adaptations to the plan's sketch of `src/index_qdrant.py`:
  1. Sparse BM25 vectors are computed **client-side** with `fastembed.SparseTextEmbedding("Qdrant/bm25")`
     rather than via Qdrant's server-side inference (`models.Document(text=..., model=...)` passed
     directly as a point's vector). The installed `qdrant-client`/local `qdrant/qdrant:latest`
     combination's server-side inference path wasn't verified to work out of the box, and
     client-side computation is simpler to reason about and test; the resulting sparse vectors
     are stored the same way either way (named vector `bm25`, IDF modifier).
  2. Qdrant point ids must be an unsigned int or a UUID; our slug-style document ids (e.g.
     `wohngeld-3f2a`) are neither, so each point's id is a `uuid.uuid5` deterministically derived
     from the document id. The original id is unaffected in the payload (`payload["id"]`), which
     is what all downstream code (search, eval, RAG) reads.
