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

- **Phase 5:** two small adaptations:
  1. `RagAnswer.sources` (`src/rag.py`) gained an extra `"id"` key per source dict beyond the
     plan's literal `{"name":..., "legal_norm":..., "official_url":...}` shape. Needed so the
     Streamlit app and `src/db.py` can populate the `conversations.retrieved_ids` column without
     re-deriving ids from names; purely additive, doesn't remove/rename any documented field.
  2. `app/app.py` inserts `sys.path.insert(0, <repo root>)` before importing `src.*`. Caught
     during browser testing: `streamlit run app/app.py` sets `sys.path[0]` to `app/`'s own
     directory (not the repo root, unlike `python -m`), so `from src import db` raised
     `ModuleNotFoundError` at runtime despite working fine from every other entry point
     (`python -m src.*`, pytest). Verified fix by driving the running app in a real (headless)
     browser via Playwright — installed temporarily into `.venv` for that check only, then
     uninstalled; it is not a project dependency and is not in `requirements.txt`.

- **Phase 6:** the Grafana Postgres datasource provisioning YAML needed `database: stille`
  nested under `jsonData`, not only as a top-level key next to `url`/`user` — the installed
  `grafana/grafana:latest` (13.1.1) Postgres plugin's dashboard-panel query path otherwise
  refuses every panel with "You do not currently have a default database configured for this
  data source", even though a manual `/api/ds/query` HTTP call against the same datasource UID
  (bypassing the dashboard's own panel-rendering code) had returned real rows with the pre-fix
  config. That gap is exactly why this was caught by actually opening the provisioned dashboard
  in a real (headless) browser via Playwright (installed temporarily, then uninstalled, same as
  Phase 5) instead of trusting the API smoke test alone. Also added `"rawQuery": true,
  "editorMode": "code"` to every panel target in `grafana/dashboards/stille.json` — without it
  the SQL datasource plugin ignores `rawSql` and tries to use the (empty) visual query builder
  instead.

- **Phase 7:** the literal fresh-clone rehearsal (`git clone` into an empty `/tmp` dir, `.env`
  from example + real key, `make up && make index-docker && make seed`) failed three separate
  ways on the *first* attempt, none of which showed up in earlier phases because the local repo
  directory already had the state each fix now handles generically:
  1. **Nested volume in a read-only mount doesn't work on a fresh host.** The `app` service
     originally mounted `./data:/app/data:ro` plus a named volume nested at
     `/app/data/.llm_cache` for the writable LLM disk cache. This worked in the original repo
     directory (where `data/.llm_cache/` already existed on the host from local runs) but fails
     on a truly fresh clone with "read-only file system" trying to create the mountpoint, since
     Docker can't create a directory inside an already-read-only bind mount. Fixed by moving the
     cache to a wholly separate path: `src/config.py` gained `LLM_CACHE_DIR` (overridable via
     env var, defaults to `data/.llm_cache` for local runs), `src/llm.py` uses it instead of a
     hardcoded path, and `docker-compose.yml` mounts a named volume at `/app/llm_cache` (a
     sibling of `/app/data`, not nested inside it) with `LLM_CACHE_DIR=/app/llm_cache` for the
     `app` service.
  2. **`make seed` assumed a local Python venv.** Its original Makefile target activated
     `.venv/bin/activate`, which doesn't exist on a fresh clone that only ever ran things through
     Docker. Changed to `docker compose run --rm app python -m src.seed_traffic`, matching
     `index-docker`'s pattern.
  3. **`docker compose up -d` silently reuses a stale image.** Compose only builds an image if
     one doesn't already exist under the project's derived image name; re-running `make up`
     after a code change (or, as tested here, a second fresh-clone attempt reusing the same
     `/tmp` directory name) kept the *old* image without rebuilding, so a `config.py` fix that
     was already pushed and cloned still wasn't present inside the running container. Fixed by
     changing the `up` Makefile target to `docker compose up -d --build`.

  All three were only caught because the rehearsal was actually run twice from a clean `/tmp`
  clone (first attempt surfaced #1, second attempt after fixing #1 and #2 surfaced #3) — a
  README/API-level check alone would have missed all of them. After all three fixes, a third
  fully-fresh clone (`rm -rf` + re-clone + fresh `.env`) passed `make up && make index-docker &&
  make seed` end-to-end, confirmed via `docker compose exec postgres psql` (15 rows, matching
  the seed count exactly, i.e. no leftover state) and a real browser session (Playwright,
  installed temporarily then removed) against both the app and the Grafana dashboard.

- **Phase 8 — `docs/README_PROJECT_EVALUATION.md` (instruction outside PLAN.md, from before
  Phase 2):** the human asked, before Phase 2 started, for a standalone document mapping this
  project against the *actual* evaluation criteria at
  https://github.com/abhirup-ghosh/llm-zoomcamp/blob/main/project.md — for a reviewer to
  quickly check off each rubric line with evidence of where/how it's implemented. An initial
  attempt to also write this requirement into `docs/PLAN.md` itself was rejected mid-edit by the
  human (who then said to continue with the phases); the underlying document request was not
  rescinded, so it's fulfilled now in Phase 8, where the rubric table naturally belongs.
  `docs/README_PROJECT_EVALUATION.md` uses the real fetched rubric text (core criteria, "Best
  practices" checkboxes, and "Bonus points") rather than PLAN.md's own approximate placeholder
  table in §Phase 8 — the two mostly agree (18 core + 3 best-practice points), but the real
  rubric additionally has an explicit cloud-deployment bonus (correctly marked unclaimed/0) and
  an open-ended "up to 3 extra" bonus (left to reviewer discretion, with candidate reasons listed
  rather than presumptuously self-awarded). The condensed table in the main `README.md` is a
  summary of this document, not an independently-derived duplicate.
