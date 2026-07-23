# Stille Ansprüche — End-to-End Implementation Plan

> **Purpose of this document:** This is the complete, authoritative implementation plan for the
> LLM Zoomcamp final project "Stille Ansprüche" (Silent Entitlements). It is written to be
> executed by Claude Code (or any coding agent) **sequentially, phase by phase, without
> improvisation**. Every technology choice, file name, schema, and acceptance criterion is
> pinned. If something in this plan conflicts with reality (e.g., a URL is dead, a library
> API changed), fix it minimally and record what actually happened directly in the relevant
> phase section below, and continue. (This document was updated in place as the project was
> built — every phase section below reflects what was actually done, including where reality
> forced a change from the original instruction.)

---

## 0. Project summary (context for the agent)

**What we are building:** A RAG (Retrieval-Augmented Generation) assistant that helps people in
Germany discover social benefits (Sozialleistungen) they may be entitled to but don't know
exist. Germany has **500+ distinct social benefits**; research (IAB, DIW, HRW, CityLAB Berlin)
documents that 40–60% of eligible people never claim key benefits — mostly an *information*
problem. The user describes their life situation in plain German or English
("alleinerziehend, Teilzeit, zwei Kinder, Miete 900 Euro — was steht mir zu?") and the
assistant answers in plain language, grounded strictly in an official/academic knowledge base,
always linking to official sources.

**Knowledge base:** The ifo Institute's open benefit inventory
(https://github.com/ifo-institute/sozialleistungen — YAML, 500+ benefits, each with legal norm,
target groups, topic fields), enriched where possible with plain-language descriptions scraped
politely from official portals (sozialplattform.de, familienportal.de).

**Why it exists / what makes it novel:** No open-source project connects a person's life
situation to the *full landscape* of German benefits conversationally. The closest project
(CityLAB Berlin "Beyond Forms", July 2026) covers exactly one benefit and focuses on
form-filling, not discovery.

**Course context:** This is the final project for DataTalksClub LLM Zoomcamp. It must
demonstrably cover Modules 1–6 and maximize the official evaluation rubric (see §14 for the
rubric mapping that the README must contain).

**Hard constraints:**
- Must run fully on a MacBook Pro M3 (development) and inside docker-compose (delivery).
- Near-zero token cost: local embeddings; `gpt-4o-mini` for generation/judging (< ~$3 total);
  everything batched and cached.
- One week of part-time work. Prefer the simple, working thing over the clever thing.

---

## 1. Ground rules for the executing agent

1. **Work strictly in phase order** (Phase 0 → Phase 8). Do not start a phase before the
   previous phase's acceptance criteria all pass.
2. **Commit after every phase** with the exact commit message given in that phase.
   Commit more often if useful, but the phase-end commit is mandatory.
3. **Every script must be idempotent and re-runnable.** Cache expensive results (scraped HTML,
   LLM outputs, embeddings) to disk under `data/` so re-runs are free.
4. **Never hardcode secrets.** All secrets come from `.env` (git-ignored). `.env.example` is
   committed.
5. **All LLM calls go through one module** (`src/llm.py`) so cost tracking and model switching
   live in one place.
6. **Language of the codebase:** English (comments, docstrings, README). Data content is
   German — do not translate the corpus.
7. **Politeness when scraping:** custom User-Agent
   `stille-ansprueche-research-bot/0.1 (educational project)`, ≥1.0 s delay between requests,
   respect robots.txt (use `urllib.robotparser`), cache every response to
   `data/raw_html/` and never re-fetch a cached URL.
8. **If a data source fails** (site blocks scraping, repo moved): fall back as specified in
   the phase's "Fallback" section. Never invent corpus content with the LLM.
9. **Attribution & licensing:** check the LICENSE of the ifo repository at ingestion time,
   record it in `data/ATTRIBUTION.md`, and attribute ifo + the portals in the README. The
   final answer UI must always show a disclaimer (see §10) and official links.
10. **Testing:** each phase lists acceptance checks. Implement them as pytest tests in
    `tests/` where marked `[test]`, otherwise as manual commands. Run `make test` before every
    phase-end commit.
11. **Keep a running log** in `docs/PROGRESS.md`: one dated bullet per completed phase, plus any
    deviations (recorded directly in the relevant phase section of this plan, not a separate
    deviations file — see the note in the header above).

---

## 2. Pinned technology stack (do not substitute)

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | in Docker: `python:3.11-slim` |
| Dependency mgmt | `pip` + `requirements.txt` | pin exact versions on first install (`pip freeze` the used subset) |
| Vector / search DB | **Qdrant** (docker image `qdrant/qdrant:latest`) | one collection, dense + sparse named vectors; hybrid via Query API prefetch + RRF fusion |
| Dense embeddings | `intfloat/multilingual-e5-small` via `sentence-transformers` | 384 dims, cosine. **MUST prefix** `"query: "` for queries and `"passage: "` for documents — this is required by E5 models |
| Sparse (keyword) | Qdrant built-in BM25 sparse vectors via `fastembed` (`Qdrant/bm25`) | this is our "text search" arm |
| Reranker (bonus) | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` via `sentence-transformers` CrossEncoder | small, multilingual, fine on M3 CPU |
| LLM (generation, question-gen, judge) | OpenAI `gpt-4o-mini` | via `openai` python SDK ≥1.x; temperature 0 for eval/judging, 0.3 for answers |
| Structured LLM output | Pydantic models + OpenAI `client.beta.chat.completions.parse` (or `response_format={"type":"json_object"}` fallback) | never regex-parse free text |
| UI | Streamlit | single-page chat app `app/app.py` |
| Feedback/monitoring store | PostgreSQL 16 (docker image `postgres:16`) | tables in §10 |
| Dashboard | Grafana (docker image `grafana/grafana:latest`) | provisioned datasource + dashboard JSON, ≥7 panels |
| Orchestration | `docker-compose.yml` + `Makefile` | ingestion runs as a make target / one-shot container |
| Testing | pytest | `tests/` |

Environment variables (define in `.env.example` with dummy values):

```
OPENAI_API_KEY=sk-...
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=stille
POSTGRES_USER=stille
POSTGRES_PASSWORD=stille_local_pw
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=benefits
EMBEDDING_MODEL=intfloat/multilingual-e5-small
RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
LLM_MODEL=gpt-4o-mini
APP_PORT=8501
```

Inside docker-compose, `POSTGRES_HOST=postgres` and `QDRANT_URL=http://qdrant:6333` are set
via the compose file's `environment:` section (compose service names as hosts).

---

## 3. Repository layout

As actually built (deviates from the original "create exactly this" instruction only in where
the planning docs live — see the note at the end of this list):

```
stille-ansprueche/
├── README.md                  # written incrementally; finalized in Phase 8
├── docs/
│   ├── PLAN.md                 # this file — moved here from root, see note below
│   ├── PROGRESS.md              # running log — moved here from root
│   ├── FOLLOWUP.md              # tracks post-submission follow-ups, outside this plan's scope
│   ├── README_PROJECT_EVALUATION.md  # rubric-by-rubric evidence mapping for reviewers (Phase 8)
│   ├── screenshot_app.png       # Phase 8
│   └── screenshot_grafana.png   # Phase 8
├── LICENSE                    # MIT for the code
├── .env.example
├── .gitignore                 # .env, data/raw_html/, __pycache__, *.pyc, .venv, models cache
├── Makefile
├── requirements.txt
├── docker-compose.yml
├── Dockerfile                 # for the Streamlit app (and reused by one-shot jobs)
├── data/
│   ├── ATTRIBUTION.md         # licenses + sources, written in Phase 1
│   ├── raw_html/              # scrape cache (git-ignored)
│   ├── ifo/                   # downloaded YAML files
│   ├── documents.jsonl        # final corpus (committed — it is small)
│   ├── ground_truth.jsonl     # committed
│   └── eval/                  # eval result CSVs/JSONs (committed)
├── src/
│   ├── __init__.py
│   ├── config.py              # loads .env, exposes constants (incl. LLM_CACHE_DIR, added Phase 7)
│   ├── llm.py                 # single OpenAI wrapper w/ cost tracking + disk cache
│   ├── ingest_ifo.py          # Phase 1
│   ├── enrich_portals.py      # Phase 1b
│   ├── build_corpus.py        # Phase 1 → data/documents.jsonl
│   ├── index_qdrant.py        # Phase 2
│   ├── search.py              # Phase 2: text/vector/hybrid/rerank/rewrite functions
│   ├── generate_ground_truth.py  # Phase 3
│   ├── eval_retrieval.py      # Phase 3
│   ├── rag.py                 # Phase 4: prompts + answer pipeline
│   ├── eval_rag.py            # Phase 4
│   ├── db.py                  # Phase 5: postgres init + insert/read helpers
│   └── seed_traffic.py        # Phase 6: demo-traffic seeding for the dashboard
├── app/
│   └── app.py                 # Streamlit UI
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasource.yml
│   │   └── dashboards/dashboards.yml
│   └── dashboards/stille.json
├── notebooks/
│   └── exploration.ipynb      # optional scratch; keep outputs cleared
└── tests/
    ├── test_corpus.py
    ├── test_search.py
    └── test_rag.py
```

**Planning-doc location, by direct instruction from the human (before Phase 1b):** `PLAN.md`,
`PROGRESS.md`, and (formerly) `DEVIATIONS.md` were moved into `docs/` instead of living at repo
root as originally written above; `docs/FOLLOWUP.md` was added (outside this plan's original
scope) to track two kinds of post-submission items — **FOLLOWUP CHECKS** (things to verify
later, e.g. independently confirming the ifo inventory is complete) and **OUT-OF-SCOPE**
(deferred work) — both meant to be revisited only after Phase 8 is done, not during the phased
build-out. `docs/DEVIATIONS.md` briefly existed as a separate file tracking exactly this kind of
"reality vs. plan" note, but was later merged into this document (in place, phase by phase) and
removed, per a further direct instruction — this plan is now the single place both the intended
plan and what actually happened when it met reality are recorded.

---

## Phase 0 — Repository bootstrap

**Goal:** empty but fully wired repo.

Steps:
1. `mkdir stille-ansprueche && cd stille-ansprueche && git init -b main`
2. Create the full directory tree from §3 with placeholder files where content comes later.
3. Write `.gitignore`:
   ```
   .env
   .venv/
   __pycache__/
   *.pyc
   data/raw_html/
   data/.llm_cache/
   .ipynb_checkpoints/
   .DS_Store
   .claude/
   ```
   (`data/.llm_cache/` and `.claude/` — the latter a local Claude Code harness artifact, not
   project content — were added once those directories actually appeared.)
4. Write `.env.example` exactly as in §2. Copy to `.env` locally (agent: ask the human to fill
   `OPENAI_API_KEY`; do not proceed to Phase 3+ without it — Phases 0–2 work without it).
5. Write `requirements.txt` (unpinned first; pin at end of Phase 8):
   ```
   openai
   pydantic
   python-dotenv
   qdrant-client[fastembed]
   sentence-transformers
   requests
   beautifulsoup4
   pyyaml
   rapidfuzz
   pandas
   tqdm
   streamlit
   psycopg2-binary
   langdetect
   pytest
   ```
6. Create venv: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   (the dev machine had only Python 3.9.6 and no `gh` CLI installed; both were installed via
   `brew install python@3.11 gh` before this step, with the human's confirmation since it's a
   system-wide change.)
7. Write `src/config.py`: loads `.env` via `python-dotenv`, exposes every env var from §2 as a
   module-level constant with the same name, plus `DATA_DIR = Path(__file__).parent.parent / "data"`.
8. Write `src/llm.py` now (used from Phase 3 on):
   - `class LLMClient` with method
     `chat(messages: list[dict], model: str = config.LLM_MODEL, temperature: float = 0.0, response_model: Type[BaseModel] | None = None) -> tuple[Any, dict]`
     returning `(parsed_or_text, usage)` where `usage = {"prompt_tokens": int, "completion_tokens": int, "cost_usd": float}`.
   - Cost table (USD per 1M tokens) as a dict: `{"gpt-4o-mini": {"input": 0.15, "output": 0.60}}`.
     (If actual pricing differs, update the dict and note it here. In practice it didn't.)
   - Disk cache: SHA256 of `(model, temperature, json.dumps(messages))` → JSON file under
     `data/.llm_cache/` (git-ignored — add to .gitignore). Cache hit returns cost 0. (Phase 7:
     the actual cache directory is `config.LLM_CACHE_DIR`, overridable via env var so it can be
     relocated outside a read-only mount in Docker — see Phase 7.)
   - A module-level running total `TOTAL_COST_USD`, printed by an `atexit` hook.
9. Write `Makefile` with (fill targets in as phases complete; create stubs now):
   `setup`, `ingest`, `index`, `ground-truth`, `eval-retrieval`, `eval-rag`, `app`, `test`,
   `up` (docker compose up -d), `down`.
10. Write initial `README.md`: project name, one-paragraph problem statement (§0), a
    "Status: under construction" note.
11. Create the GitHub repository (public) named `stille-ansprueche` and push. If the `gh` CLI
    is available and authenticated: `gh repo create stille-ansprueche --public --source=. --push`.
    Otherwise instruct the human to create it on github.com and run
    `git remote add origin <url> && git push -u origin main`.

**Acceptance criteria:**
- `make test` runs pytest (0 tests, exit 0). (In practice, pytest exits with code 5 — "no tests
  collected" — when `tests/` has only empty placeholder files, which `make` otherwise treats as
  a failure. The `test` Makefile target treats exit code 5 as success; this only matters while
  the test files are empty, and is inert once Phase 1 adds real tests to `tests/test_corpus.py`.)
- `python -c "from src import config, llm"` works.
- Repo pushed to GitHub with all placeholder structure.

**Commit:** `phase 0: repository bootstrap`

---

## Phase 1 — Ingestion pipeline part A: the ifo benefit inventory

**Goal:** `data/ifo/` contains the raw YAML; a parser turns it into normalized benefit records.

**Source:** https://github.com/ifo-institute/sozialleistungen — a YAML inventory of 500+
German social benefits. Structure (per the repo README): top-level keys are law books
(e.g. `SGB II`), containing categories, containing lists of entries with fields like
`leistung` (name + description), `rechtsnorm` (legal norm), `zielgruppen` (target groups,
ordered list), `themenfelder` (topic fields, ordered list). **Inspect the actual files first**
— field names/structure may differ slightly; adapt the parser to reality, not to this
paragraph.

Steps (`src/ingest_ifo.py`):
1. Download the repo as a zip via
   `https://github.com/ifo-institute/sozialleistungen/archive/refs/heads/main.zip`
   (use `requests`, save under `data/ifo/`). If the default branch is not `main`, try `master`.
   Unzip; locate all `*.yml`/`*.yaml` files and the LICENSE file.
2. Record license + citation into `data/ATTRIBUTION.md` (create the file; include repo URL,
   license name, access date, and the ifo press-release citation).
3. Parse every YAML entry into a `BenefitRecord` (Pydantic model):
   ```python
   class BenefitRecord(BaseModel):
       id: str                 # slug: lowercase, ascii-transliterated name + short hash, e.g. "wohngeld-3f2a"
       name: str               # short benefit name (first sentence/clause of `leistung`)
       description: str        # full `leistung` text
       legal_norm: str         # `rechtsnorm`
       law_book: str           # e.g. "SGB II"
       category: str           # the category heading under the law book
       target_groups: list[str]
       topic_fields: list[str]
       source: str = "ifo-institute/sozialleistungen"
   ```
4. Write all records to `data/ifo/benefits_parsed.jsonl`. Print a summary: total count,
   counts per law book, counts per primary target group.

**Fallback:** if the GitHub repo is unreachable, stop and ask the human to download it
manually into `data/ifo/`. Do not substitute another source. (Not needed — the repo downloaded
fine on the first try.)

**As actually run:** the real repo has a single `sozialleistungen.yml` (not multiple files),
21 law books, 502 entries — matching this paragraph's schema sketch almost exactly
(`leistung`/`rechtsnorm`/`zielgruppen`/`themenfelder`), so the parser needed no schema
adaptation. License confirmed CC-BY-SA-4.0. `name` is extracted as the text before the first
`.`/`,` in `leistung` (e.g. "Wohngeld, Zuschuss zur Miete..." → "Wohngeld"), which was confirmed
to split cleanly for the Phase 2 smoke test.

**Acceptance criteria [test in tests/test_corpus.py]:**
- ≥ 400 parsed records; every record has non-empty `name`, `legal_norm`, `law_book`,
  ≥1 target group. (Actual: 502/502 records, all fields populated, all ids unique.)
- No duplicate `id`s.

**Commit:** `phase 1a: ifo inventory ingestion`

---

## Phase 1b — Ingestion pipeline part B: plain-language enrichment (best effort)

**Goal:** enrich as many benefits as possible with citizen-facing plain-language text
(how to apply, requirements, amounts) from official portals. This step is **best-effort**:
the project remains viable with zero enrichment; every enrichment improves answer quality.

Sources, in priority order (`src/enrich_portals.py`):
1. **sozialplattform.de** (federal social services portal). Discover pages via its sitemap
   (`/sitemap.xml`; if absent, crawl the "Leistungen"/"Sozialleistungen" section index page
   only — no deep crawling). Target: individual benefit description pages.
2. **familienportal.de** (federal family portal, BMFSFJ). Same approach: sitemap or the
   "Familienleistungen" A–Z index.

Steps:
1. Fetch sitemaps/index pages (respecting §1 rule 7). Collect candidate URLs whose slug/title
   looks like a benefit name (heuristic: contains any token from any ifo benefit name with
   length ≥ 5 chars).
2. For each candidate URL: fetch (cached), parse with BeautifulSoup, extract `<h1>`, and main
   content text (strip nav/footer/script; prefer `<main>` or `article` tag; collapse
   whitespace). Store `{url, title, text}` in `data/raw_html/extracted.jsonl`.
3. Match extracted pages to ifo records with `rapidfuzz.fuzz.token_set_ratio(benefit_name,
   page_title)`; accept matches with score ≥ 85. One page may match multiple benefits; one
   benefit keeps only its best page.
4. Output `data/ifo/enrichment.jsonl`: `{benefit_id, url, title, text}`.
5. Print: number of benefits enriched / total. **Any number ≥ 30 is a success.** If scraping
   is blocked entirely (robots.txt disallows, or persistent 403s): skip, write the fact into
   `data/ATTRIBUTION.md` and note it here, continuing with zero enrichments.

**As actually run:** neither portal blocked scraping, so the fallback above wasn't needed.
sozialplattform.de's own `/sitemap.xml` turned out to list 5138 URLs (not a small
"Leistungen"-index page) — filtered down to candidates via the benefit-name-token heuristic
*before* fetching any of them. familienportal.de's `/sitemap.xml` itself 404s; its robots.txt
names the real sitemap index (one gzipped child sitemap, 127 URLs). Politeness: custom
User-Agent, sozialplattform.de's robots.txt `Crawl-delay: 10` honored via `urllib.robotparser`
(not just the ≥1.0s minimum), every response cached under `data/raw_html/`. Result: 117
candidates after token filtering → 83 usable pages extracted → **49 / 502 benefits enriched**
(9.8%), well above the ≥30 bar.

**Acceptance criteria:**
- Script completes without unhandled exceptions; cache directory populated; enrichment file
  exists (possibly with few/zero rows — that is acceptable).

**Commit:** `phase 1b: portal enrichment (best effort)`

---

## Phase 1c — Build the final corpus

**Goal:** `data/documents.jsonl` — the single knowledge base file everything downstream uses.

Steps (`src/build_corpus.py`):
1. Join parsed ifo records with enrichment (left join on `benefit_id`).
2. Build one document per benefit:
   ```python
   class Document(BaseModel):
       id: str                    # benefit id
       name: str
       law_book: str
       legal_norm: str
       category: str
       target_groups: list[str]
       topic_fields: list[str]
       text: str                  # see composition rule below
       official_url: str | None   # enrichment url if any
       enriched: bool
   ```
   **Text composition rule:** `text = f"{name}. {description} Rechtsgrundlage: {legal_norm}. Zielgruppen: {', '.join(target_groups)}. Themen: {', '.join(topic_fields)}."`
   If enriched: append `"\n\n" + enrichment_text[:4000]` (truncate enrichment at 4000 chars).
3. **Chunking rule:** if `len(text) > 6000` chars, split into chunks of ≤ 3000 chars with 300
   overlap, at sentence boundaries; chunk ids = `{id}--0`, `{id}--1`, ... All chunks keep the
   parent's metadata. (Most ifo-only docs will be one chunk — that is fine and expected.)
4. Write `data/documents.jsonl` (one JSON per line). Print corpus stats: docs, chunks,
   median text length, % enriched.

**As actually run:** 502 documents, all single-chunk — the longest composed text (with
enrichment appended) was 4555 chars, under the 6000-char chunking threshold, so the
chunk-splitting path never triggered on real data (it's covered by a synthetic unit test
instead). Median chunk length 310 chars; 49/502 (9.8%) enriched.

**Acceptance criteria [test]:**
- ≥ 400 documents; every document JSON-parses back into `Document`; no empty `text`;
  no duplicate ids. (Actual: 502 documents, all criteria met.)

**Commit:** `phase 1c: final corpus built`

---

## Phase 2 — Indexing & search (text, vector, hybrid, rerank)

**Goal:** Qdrant collection with dense + sparse vectors; `src/search.py` exposing 5 search
functions with a single common signature.

Steps:
1. Add `qdrant` service to `docker-compose.yml` now (image `qdrant/qdrant:latest`, port
   `6333:6333`, volume `qdrant_data:/qdrant/storage`). `make up` starts it.
2. `src/index_qdrant.py`:
   - Create collection `benefits` (from config) with **named vectors**:
     - dense: `"dense"`, size 384, distance Cosine
     - sparse: `"bm25"` (Qdrant sparse vector config, modifier IDF)
   - Embed each chunk's `text` with sentence-transformers `multilingual-e5-small`,
     **prefixing `"passage: "`**. Batch size 64. On Apple Silicon, pass `device="mps"` if
     `torch.backends.mps.is_available()` else CPU.
   - Sparse vectors via fastembed BM25 (`models.Document(text=..., model="Qdrant/bm25")` in
     the point's sparse vector field — use the current qdrant-client API; check its docs/
     docstrings if the API differs). **As actually built:** computed **client-side** instead,
     via `fastembed.SparseTextEmbedding("Qdrant/bm25")` directly in Python, rather than passing
     `models.Document` for Qdrant server-side inference — the installed `qdrant-client`/local
     `qdrant/qdrant:latest` combination's server-side inference path wasn't verified to work out
     of the box, and client-side computation is simpler to reason about and test. The resulting
     sparse vectors are stored identically either way (named vector `bm25`, IDF modifier).
   - Payload = the full document dict.
   - Recreate the collection idempotently (delete if exists, then create; guard with a
     `--keep` flag to skip reindexing when the point count already equals the chunk count).
   - **Point ids (not in the original plan):** Qdrant point ids must be an unsigned int or a
     UUID; the slug-style document ids (e.g. `wohngeld-3f2a`) are neither, so each point's id is
     a `uuid.uuid5` deterministically derived from the document id. The original id is
     unaffected in the payload (`payload["id"]`), which is what all downstream code (search,
     eval, RAG) reads.
3. `src/search.py` — all functions return `list[dict]` of payloads, length ≤ `k`:
   ```python
   def search_text(query: str, k: int = 10) -> list[dict]          # BM25 sparse only
   def search_vector(query: str, k: int = 10) -> list[dict]        # dense only ("query: " prefix!)
   def search_hybrid(query: str, k: int = 10) -> list[dict]        # Qdrant Query API: prefetch dense(top 20) + bm25(top 20), fusion=RRF
   def search_hybrid_rerank(query: str, k: int = 10) -> list[dict] # hybrid top 20 → CrossEncoder rerank → top k
   def rewrite_query(query: str) -> str                            # LLM: translate to German if not German (langdetect), expand with 2-4 Amtsdeutsch synonyms/official benefit terms; returns a single search string. Uses llm.py (cached).
   def search_hybrid_rewritten(query: str, k: int = 10) -> list[dict]  # rewrite_query → search_hybrid
   ```
   Load models lazily as module-level singletons.
4. Manual smoke test (put in `tests/test_search.py`, marked as integration test that skips if
   Qdrant is down): query `"Zuschuss zur Miete für Familien mit geringem Einkommen"` — assert
   that a document whose name contains `"Wohngeld"` appears in the top 5 of `search_hybrid`.

**Acceptance criteria:**
- `make index` completes; Qdrant reports point count == chunk count. (Actual: 502/502, confirmed
  idempotent via `--keep`.)
- Smoke test passes.
- `search_hybrid_rerank` returns in < 3 s on the M3 for a single query. (Actual warm-state
  latency ~0.2s; the first call in a fresh process pays a one-time model-load cost — expected,
  given the lazy singleton loading in step 3.)

**Commit:** `phase 2: qdrant indexing + five search modes`

---

## Phase 3 — Ground truth & retrieval evaluation

**Goal:** `data/ground_truth.jsonl` (~1,000 queries) and `data/eval/retrieval_results.csv`
comparing 5 retrieval strategies with Hit Rate and MRR.

### 3a. Ground truth generation (`src/generate_ground_truth.py`)
1. Sample documents: all enriched documents + a random sample (seed 42) of ifo-only documents,
   to a total of **200 documents** (if enriched > 200, cap at 200 prioritizing enriched).
2. For each sampled document, one LLM call (gpt-4o-mini, temperature 0.7, structured output):
   ```python
   class GeneratedQuestions(BaseModel):
       questions_de: list[str]   # exactly 4 German questions
       question_en: str          # exactly 1 English question
   ```
   Prompt (verbatim, as the user message; system message: "You generate realistic user
   questions for evaluating a retrieval system. Answer only with the requested JSON."):
   ```
   Du siehst den Eintrag einer deutschen Sozialleistung. Formuliere 4 realistische Fragen auf
   Deutsch, die eine betroffene Person stellen würde, OHNE den offiziellen Namen der Leistung
   zu verwenden. Die Fragen sollen Alltagssprache verwenden und die Lebenslage beschreiben
   (z.B. "Ich bin alleinerziehend und arbeite Teilzeit..."). Formuliere zusätzlich 1 Frage auf
   Englisch im gleichen Stil.

   LEISTUNG:
   {document_text_truncated_to_2000_chars}
   ```
3. Write one row per question: `{"question": str, "lang": "de"|"en", "doc_id": parent doc id}`.
   Ground truth maps a question to its source document (course Module 3 methodology).
   Expected: 200 docs × 5 = 1,000 rows. Cost estimate: ~200 calls ≈ well under $0.50.
   (Actual: exactly 1000 rows — 800 de, 200 en — cost $0.026.)

### 3b. Retrieval evaluation (`src/eval_retrieval.py`)
1. Metrics (implement exactly; k=5 primary, also report k=10):
   - **Hit Rate@k** = fraction of questions whose `doc_id` (parent id — strip `--N` chunk
     suffix when comparing) appears in the top k results.
   - **MRR@k** = mean of `1/rank` of the first correct result within top k, else 0.
2. Evaluate these 5 strategies over the full ground truth:
   `text`, `vector`, `hybrid`, `hybrid_rerank`, `hybrid_rewritten`.
   Additionally report every strategy **split by question language** (de vs en) — the
   cross-lingual comparison is a headline result of the project.
3. Output `data/eval/retrieval_results.csv` with columns:
   `strategy, lang, hit_rate@5, mrr@5, hit_rate@10, mrr@10, n_questions` and print a markdown
   table of it. Copy the table into README section "Retrieval evaluation" with 2–3 sentences
   interpreting it (which strategy wins overall; how badly text-only degrades on English
   queries; whether rewriting closes the gap).
4. **The best overall strategy (highest MRR@5, all languages) becomes `search_best` —**
   add `search_best = <winner>` alias in `src/search.py` and use it in the RAG flow.

**As actually run:** the first draft of `eval_retrieval.py` called every search function twice
per question (once each for the "de"/"en" split and again for "all", which is just their union)
— caught and fixed before the full 1000-question × 5-strategy run, to search once per question
and slice results into subsets instead. **Result: plain `vector` search won** (MRR@5 = 0.173
overall), beating `hybrid` (0.125), `hybrid_rerank` (0.164), and `hybrid_rewritten` (0.145) —
somewhat surprising, since hybrid/rerank/rewrite are usually expected to help. Root cause: the
ground-truth questions are deliberately phrased without the benefit's official name (per the
prompt above), so BM25 (`text`, MRR@5 = 0.025) contributes mostly noise, and naive RRF fusion in
`hybrid` lets that noise drag vector-only performance down; reranking recovers most but not all
of the gap. `search_best` in `src/search.py` was set to `search_vector` accordingly. Full
interpretation in the README "Retrieval evaluation" section — this is reported as an honest
negative-ish finding, not smoothed over.

**Acceptance criteria:**
- ground_truth.jsonl has ≥ 900 rows, ≥ 150 English. (Actual: 1000 rows, 200 English.)
- retrieval_results.csv has 5 strategies × 3 lang rows (de/en/all) = 15 rows. (Actual: matches
  exactly.)
- README updated with the results table.

**Commit:** `phase 3: ground truth + retrieval evaluation (5 strategies, cross-lingual)`

---

## Phase 4 — RAG flow & LLM/prompt evaluation

**Goal:** `src/rag.py` produces grounded answers; `data/eval/rag_results.csv` compares 3
prompt variants; the winner is pinned for the app.

### 4a. RAG pipeline (`src/rag.py`)
```python
class RagAnswer(BaseModel):
    answer: str
    benefits_mentioned: list[str]      # names of benefits the answer draws on
    sources: list[dict]                # [{"id":..., "name":..., "legal_norm":..., "official_url":...}]
    # ("id" added beyond the original sketch — needed so the Streamlit app / Postgres logging
    # can populate conversations.retrieved_ids without re-deriving ids from names.)
    model: str
    prompt_variant: str
    response_time_s: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

def answer(question: str, prompt_variant: str = "v_best", k: int = 5) -> RagAnswer
```
Pipeline inside `answer()`: detect language (`langdetect`) → `search_best(question, k)` →
build context block (for each hit: `## {name}\nRechtsgrundlage: {legal_norm}\n{text}\nOffizieller Link: {official_url or 'siehe zuständige Behörde'}`)
→ one LLM call → assemble `RagAnswer` (sources = the k hits' metadata).

**The three prompt variants** (store as constants `PROMPT_V1`, `PROMPT_V2`, `PROMPT_V3`;
all share the same hard grounding rules):

Shared grounding rules (include verbatim in every system prompt):
```
REGELN:
- Antworte AUSSCHLIESSLICH auf Basis des bereitgestellten KONTEXT.
- Erfinde NIEMALS Geldbeträge, Fristen oder Anspruchsvoraussetzungen. Wenn der Kontext eine
  Information nicht enthält, sage das ausdrücklich.
- Nenne für jede erwähnte Leistung die Rechtsgrundlage und, falls vorhanden, den offiziellen Link.
- Antworte in der Sprache der Frage (Deutsch oder Englisch).
- Schließe mit dem Hinweis ab, dass dies keine Rechtsberatung ist und die zuständige Behörde
  verbindliche Auskunft gibt.
```
- **V1 "baseline":** rules + "Beantworte die Frage der Person hilfreich und korrekt."
- **V2 "einfache_sprache":** rules + "Antworte in Einfacher Sprache: kurze Sätze (max. ~12
  Wörter), keine Fachbegriffe ohne Erklärung, direkte Ansprache, konkrete nächste Schritte
  als nummerierte Liste."
- **V3 "structured":** rules + "Strukturiere die Antwort: (1) Kurzantwort in 2 Sätzen,
  (2) 'Diese Leistungen kommen in Frage' als Liste mit je 1 Satz Begründung,
  (3) 'Nächste Schritte', (4) 'Quellen'."

### 4b. LLM evaluation (`src/eval_rag.py`)
1. Sample 100 ground-truth questions (seed 42; stratified: 80 de / 20 en).
2. For each question × each prompt variant: run `answer()`, then judge with **two** LLM-judge
   calls (gpt-4o-mini, temperature 0, structured output):
   - **Relevance judge** (Module 4 methodology): given question + answer, classify
     `RELEVANT | PARTLY_RELEVANT | NON_RELEVANT` with a 1-sentence explanation.
   - **Faithfulness judge**: given the retrieved context + answer, classify
     `FAITHFUL | MINOR_UNSUPPORTED | HALLUCINATED` — "does the answer assert any entitlement,
     amount, or condition not present in the context?" with a 1-sentence explanation.
3. Also compute a cheap readability proxy per answer: mean sentence length in words
   (split on `.!?`). Lower is better for V2.
4. Output `data/eval/rag_results.csv`: one row per (question, variant) with judgments,
   tokens, cost, response time; plus print an aggregate markdown table:
   `variant, %relevant, %faithful, mean_sentence_len, mean_cost_usd, mean_time_s`.
5. **Pick the winner** = highest `%faithful`, tie-broken by `%relevant`. Set
   `PROMPT_VBEST = <winner>` in `rag.py` (the `"v_best"` variant resolves to it). Copy the
   aggregate table + 2–3 interpretation sentences into README section "RAG evaluation".
6. Cost guard: 100 q × 3 variants × (1 answer + 2 judge calls) = 900 calls of gpt-4o-mini
   ≈ $1–2. All cached, so re-runs are free. Print total cost at the end.

**As actually run:** cost $0.177 for the 900 calls (well under the $1–2 estimate). **Result:
`einfache_sprache` won** (57% faithful) vs. `baseline` (41%) and `structured` (36%) —
`PROMPT_VBEST` set accordingly. Relevance was high and similar across all three variants
(80–91%), so retrieval quality (not prompt style) is the bottleneck there; faithfulness is what
separated them — `einfache_sprache`'s short, simple sentences (mean 6.1 words) left much less
room for the model to elaborate beyond the retrieved context than `structured`'s multi-section
format (mean 17.2 words/sentence), which invited more inferred, less-grounded detail. Full
interpretation in README "RAG evaluation".

**Acceptance criteria:**
- rag_results.csv has 300 answer rows, each with both judgments. (Actual: 300/300, all judged.)
- README updated with the aggregate table and the declared winner.
- `python -c "from src.rag import answer; print(answer('Ich bin Rentnerin mit sehr kleiner Rente und kann meine Miete kaum zahlen. Was steht mir zu?').answer)"`
  prints a German answer that mentions at least one plausible benefit and contains the
  disclaimer sentence. (Confirmed.)

**Commit:** `phase 4: RAG flow + 3-prompt evaluation with relevance & faithfulness judges`

---

## Phase 5 — Database & application (Streamlit UI + feedback)

**Goal:** a chat UI a reviewer can run with one command, storing every conversation and
thumbs up/down feedback in Postgres.

### 5a. Postgres (`src/db.py`)
1. Add `postgres` service to docker-compose (image `postgres:16`, env from §2, port
   `5432:5432`, volume `pg_data:/var/lib/postgresql/data`).
2. `src/db.py` exposes `init_db()` (CREATE TABLE IF NOT EXISTS) and typed insert/select
   helpers. Schema (execute verbatim):
   ```sql
   CREATE TABLE IF NOT EXISTS conversations (
       id UUID PRIMARY KEY,
       ts TIMESTAMPTZ NOT NULL DEFAULT now(),
       question TEXT NOT NULL,
       answer TEXT NOT NULL,
       lang TEXT,
       prompt_variant TEXT,
       model TEXT,
       retrieved_ids TEXT[],          -- benefit ids shown
       relevance TEXT,                -- judge label, nullable (filled async)
       relevance_explanation TEXT,
       prompt_tokens INT,
       completion_tokens INT,
       cost_usd NUMERIC(10,6),
       response_time_s NUMERIC(8,3)
   );
   CREATE TABLE IF NOT EXISTS feedback (
       id SERIAL PRIMARY KEY,
       conversation_id UUID REFERENCES conversations(id),
       ts TIMESTAMPTZ NOT NULL DEFAULT now(),
       value INT NOT NULL CHECK (value IN (-1, 1))
   );
   ```
3. `init_db()` is called on app startup (idempotent).

### 5b. Streamlit app (`app/app.py`)
Layout, top to bottom:
1. Title `Stille Ansprüche`, subtitle
   `Entdecke Sozialleistungen, die dir zustehen könnten — grounded in official sources.`
2. Permanent info box (st.info): the disclaimer —
   `Dies ist ein Informationsassistent und keine Rechtsberatung. Verbindliche Auskünfte gibt nur die zuständige Behörde. Datengrundlage: ifo-Institut Sozialleistungsinventur & offizielle Portale.`
3. `st.chat_input` for the question. On submit:
   - call `rag.answer(question)` with a spinner;
   - render the answer (markdown), then an expander `Quellen` listing each source's name,
     legal norm, and link;
   - insert the conversation row (relevance judged inline with the relevance judge from
     Phase 4 — acceptable latency for a demo; wrap in try/except so judging failures never
     break the app);
   - render 👍 / 👎 buttons (st.columns); clicking inserts into `feedback` and shows
     `st.toast("Danke!")`. Use `st.session_state` to remember the last conversation id and to
     keep chat history for the session (render history above the input).
4. Sidebar: choose prompt variant (default v_best), k (default 5), and a
   "show retrieved context" checkbox for debugging.

**As actually built:** `app/app.py` inserts `sys.path.insert(0, <repo root>)` before importing
`src.*` — caught during browser testing: `streamlit run app/app.py` sets `sys.path[0]` to
`app/`'s own directory (not the repo root, unlike `python -m`), so `from src import db` raised
`ModuleNotFoundError` at runtime despite working fine from every other entry point (`python -m
src.*`, pytest). Verified end-to-end in a real (headless) browser via Playwright — installed
temporarily into `.venv` for that check only, then uninstalled; it is not a project dependency
and is not in `requirements.txt`. That session: submitted the smoke question, got a rendered
answer + Quellen expander, clicked 👍, saw "Danke für dein Feedback!", zero console errors.

**Acceptance criteria:**
- `make up && make app` → UI answers the Phase 4 smoke question end-to-end; a row appears in
  `conversations`; clicking 👍 adds a row in `feedback` (verify with
  `docker compose exec postgres psql -U stille -d stille -c "select count(*) from conversations;"`).
  (Confirmed via the browser session above.)

**Commit:** `phase 5: streamlit app + postgres conversation/feedback logging`

---

## Phase 6 — Monitoring dashboard (Grafana)

**Goal:** a provisioned Grafana dashboard with ≥ 7 panels over the Postgres data; zero manual
clicking required after `docker compose up`.

Steps:
1. Add `grafana` service to docker-compose (port `3000:3000`,
   `GF_SECURITY_ADMIN_PASSWORD=admin`, volumes mounting `./grafana/provisioning` to
   `/etc/grafana/provisioning` and `./grafana/dashboards` to `/var/lib/grafana/dashboards`).
2. `grafana/provisioning/datasources/datasource.yml`: Postgres datasource pointing at service
   `postgres:5432`, db/user/password from §2. **As actually built:** the installed
   `grafana/grafana:latest` (13.1.1) Postgres plugin needs `database: stille` nested under
   `jsonData`, not only as a top-level key next to `url`/`user` — without it, every dashboard
   panel fails with "You do not currently have a default database configured for this data
   source", even though a manual `/api/ds/query` HTTP call against the same datasource UID
   (bypassing the dashboard's own panel-rendering code) had returned real rows with the pre-fix
   config. This gap is exactly why it was caught by opening the actual dashboard in a real
   (headless) browser via Playwright (installed temporarily, then uninstalled) instead of
   trusting an API-level smoke test alone.
3. `grafana/provisioning/dashboards/dashboards.yml`: file provider loading
   `/var/lib/grafana/dashboards`.
4. `grafana/dashboards/stille.json`: dashboard `Stille Ansprüche — Monitoring` with these
   panels (each an SQL query; use `$__timeFilter(ts)` where sensible):
   1. Stat: total conversations
   2. Time series: conversations per hour/day
   3. Pie: feedback 👍 vs 👎 (`select case value when 1 then 'up' else 'down' end, count(*) from feedback group by 1`)
   4. Pie: relevance label distribution
   5. Time series: avg response_time_s over time
   6. Time series: cumulative cost_usd (`sum(cost_usd)` over time buckets)
   7. Bar: question language distribution
   8. Table: top 10 retrieved benefits (`select unnest(retrieved_ids), count(*) ... group by 1 order by 2 desc limit 10`)
5. Generate ~30 rows of demo traffic so the dashboard isn't empty for reviewers: script
   `src/seed_traffic.py` that runs 15 random ground-truth questions through `rag.answer()`
   and random feedback; add `make seed`.
   Also needed (not in the original plan): every panel target in `stille.json` needs
   `"rawQuery": true, "editorMode": "code"` set, or the SQL datasource plugin ignores `rawSql`
   entirely and tries to use the (empty) visual query builder instead — panels would silently
   show no data.

**Acceptance criteria:**
- Fresh `docker compose up -d` → http://localhost:3000 (admin/admin) shows the dashboard with
  all 8 panels populated after `make seed`. (Confirmed via a real browser screenshot with all 8
  panels populated and zero console errors.)

**Commit:** `phase 6: provisioned grafana dashboard (8 panels)`

---

## Phase 7 — Full containerization & reproducibility

**Goal:** `docker compose up` runs *everything*; a stranger can reproduce the project from the
README alone.

Steps:
1. `Dockerfile` (app image): `python:3.11-slim`, install requirements, copy `src/` and
   `app/`, `CMD streamlit run app/app.py --server.port ${APP_PORT} --server.address 0.0.0.0`.
   Pre-download the two sentence-transformers models in a build layer
   (`RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('intfloat/multilingual-e5-small'); CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')"`)
   so the container starts offline-fast.
2. docker-compose final state — services: `qdrant`, `postgres`, `grafana`, `app`
   (build: ., depends_on the others, env overrides `QDRANT_URL=http://qdrant:6333`,
   `POSTGRES_HOST=postgres`, pass `OPENAI_API_KEY` through from host env / `.env`).
   `app` mounts `./data:/app/data` read-only so the corpus ships without rebuilding. **As
   actually built:** the LLM disk cache (`src/llm.py`) needs to write, so it's mounted as a
   *separate*, non-nested named volume at `/app/llm_cache` (sibling of `/app/data`), with
   `LLM_CACHE_DIR=/app/llm_cache` set for the `app` service and `src/config.py`/`src/llm.py`
   reading that env var (defaulting to `data/.llm_cache` for local runs). See the rehearsal note
   below for why nesting it inside `/app/data` instead doesn't work.
3. Indexing inside compose: `make index-docker` =
   `docker compose run --rm app python -m src.index_qdrant`.
4. Pin `requirements.txt` (`pip freeze` filtered to direct deps with `==` versions).
5. End-to-end fresh-clone rehearsal (do it literally): clone into /tmp, `.env` from example +
   key, `make up && make index-docker && make seed`, open app + grafana, run one question.
   Fix anything that breaks; that is the point of this phase.

**As actually run:** the literal fresh-clone rehearsal failed three separate ways on the first
two attempts — none of which showed up earlier because the local repo directory already had the
state each fix now handles generically:
1. **Nested volume in a read-only mount doesn't work on a fresh host.** Mounting the LLM cache
   nested at `/app/data/.llm_cache` (inside the read-only `./data:/app/data:ro` mount) worked
   locally (where `data/.llm_cache/` already existed on the host from prior runs) but fails on a
   truly fresh clone with "read-only file system" trying to create the mountpoint — Docker can't
   create a directory inside an already-read-only bind mount. Fixed as described in step 2 above.
2. **`make seed` assumed a local Python venv.** Its Makefile target originally activated
   `.venv/bin/activate`, which doesn't exist on a fresh clone that only ever ran things through
   Docker. Changed to `docker compose run --rm app python -m src.seed_traffic`, matching
   `index-docker`'s pattern.
3. **`docker compose up -d` silently reuses a stale image.** Compose only builds an image if one
   doesn't already exist under the project's derived image name; re-running `make up` after a
   code change (or, as tested here, a second fresh-clone attempt reusing the same directory
   name) kept the *old* image without rebuilding. Fixed by changing the `up` Makefile target to
   `docker compose up -d --build`.

All three were only caught because the rehearsal was actually run to convergence from a clean
`/tmp` clone (three attempts total) rather than trusting a single pass — a README/API-level
check alone would have missed all of them. The third, fully-fresh attempt passed
`make up && make index-docker && make seed` end-to-end, confirmed via `docker compose exec
postgres psql` (row counts matched the seed exactly — no leftover state) and a real browser
session (Playwright, installed temporarily then removed) against both the app and Grafana.

**Acceptance criteria:**
- The fresh-clone rehearsal passes start to finish following only README commands. (Confirmed
  on the third attempt, after the three fixes above.)

**Commit:** `phase 7: full docker-compose + reproducibility rehearsal`

---

## Phase 8 — README, rubric mapping & polish

**Goal:** the README is the submission. Write it for a peer reviewer who has 15 minutes.

README structure (write fully):
1. **Title + one-line pitch + banner screenshot** of the app.
2. **Problem description** (2–3 paragraphs): the non-take-up problem with the documented
   numbers (40–60% non-take-up of Grundsicherung im Alter per CityLAB Berlin/Google.org 2026;
   decades of IAB/DIW research; HRW 2025 report on burdensome processes; 500+ benefits per
   ifo 2025). Why RAG: information/discovery gap, not calculation gap. Link the ifo dataset,
   CityLAB Beyond Forms (and state the differentiation: single-benefit form-filling vs.
   cross-benefit discovery), and GETTSIM as future work.
3. **Dataset**: sources, license/attribution, corpus stats, `data/documents.jsonl` format.
4. **Architecture** diagram (ASCII or mermaid): ingestion → Qdrant → RAG → Streamlit →
   Postgres → Grafana.
5. **How to run** (the Phase 7 rehearsal commands, verbatim).
6. **Retrieval evaluation** (table from Phase 3 + interpretation).
7. **RAG evaluation** (table from Phase 4 + interpretation).
8. **Monitoring** (dashboard screenshot + panel list).
9. **Rubric self-assessment table** (see below).
10. **Cost report**: total OpenAI spend printed by llm.py across the project.
    (Actual: **$0.28** total — computed exactly, not estimated, by summing token counts from
    every unique cached call across every `.llm_cache` this project ever wrote to, local and
    both Docker volumes, since the disk cache means a unique call only ever costs money once.
    Breakdown: ground truth generation $0.026, retrieval-eval query rewriting $0.045, RAG
    evaluation (answers + judges) $0.177, demo seeding across 3 runs $0.021, incidental manual
    smoke tests ~$0.01.)
11. **Limitations & future work**: enrichment coverage, no entitlement *calculation* (→
    GETTSIM), no application form filling (→ Beyond Forms), evaluation on synthetic questions.
    (Also added: an open item to independently verify the ifo inventory's completeness — see
    `docs/FOLLOWUP.md`.)

**Rubric self-assessment table (include verbatim, verify each claim is true before writing):**

| Criterion | Points claimed | Evidence |
|---|---|---|
| Problem description | 2 | README §Problem |
| Retrieval flow (KB + LLM) | 2 | Qdrant + gpt-4o-mini in `src/rag.py` |
| Retrieval evaluation (multiple, best used) | 2 | 5 strategies, `data/eval/retrieval_results.csv`, winner = `search_best` |
| LLM evaluation (multiple, best used) | 2 | 3 prompts × 2 judges, `data/eval/rag_results.csv`, winner = `v_best` |
| Interface | 2 | Streamlit UI |
| Ingestion pipeline (automated) | 2 | `make ingest` (Python scripts, Phase 1) |
| Monitoring (feedback + dashboard ≥5 charts) | 2 | 👍/👎 + 8-panel Grafana |
| Containerization (everything in compose) | 2 | `docker-compose.yml` |
| Reproducibility | 2 | rehearsed instructions, pinned deps, committed data |
| Bonus: hybrid search | 1 | RRF in `search_hybrid` |
| Bonus: document re-ranking | 1 | CrossEncoder in `search_hybrid_rerank` |
| Bonus: query rewriting | 1 | `rewrite_query` + evaluated as its own strategy |

**As actually built — `docs/README_PROJECT_EVALUATION.md` (instruction outside this plan, given
by the human before Phase 2):** the human asked, before Phase 2 started, for a standalone
document mapping this project against the *actual* evaluation criteria at
https://github.com/abhirup-ghosh/llm-zoomcamp/blob/main/project.md, so a reviewer can quickly
check off each rubric line with evidence of where/how it's implemented. That real rubric mostly
matches the placeholder table above (18 core + 3 best-practice points) but additionally has an
explicit cloud-deployment bonus (marked unclaimed/0 here) and an open-ended "up to 3 extra"
bonus (left to reviewer discretion in that document, with candidate reasons listed rather than
presumptuously self-awarded). `docs/README_PROJECT_EVALUATION.md` is the authoritative,
evidence-linked version; the table above and the condensed one in `README.md` summarize it.

Also in Phase 8:
- Add 2 screenshots (`docs/screenshot_app.png`, `docs/screenshot_grafana.png`) — taken via a
  real headless browser (Playwright, installed temporarily then removed, not a project
  dependency). Two screenshot-specific quirks hit and fixed along the way: Streamlit's chat view
  auto-scrolls to the bottom (fixed by scrolling
  `[data-testid="stAppScrollToBottomContainer"]` back to 0 before capturing), and Grafana's
  dashboard-refresh websocket keeps Playwright's `networkidle` wait from ever resolving (fixed
  by waiting for `"load"` plus an explicit element instead).
- Clear notebook outputs (already empty — nothing to do); final `make test` green; final push.

**Commit:** `phase 8: README, rubric mapping, screenshots — submission ready`

---

## 13. Seven-day schedule mapping (for the human)

| Day | Phases |
|---|---|
| 1 | Phase 0 + 1a + 1b + 1c (corpus on disk) |
| 2 | Phase 2 (indexing + 5 search modes) |
| 3 | Phase 3 (ground truth + retrieval eval) |
| 4 | Phase 4 (RAG + prompt eval) |
| 5 | Phase 5 (app + feedback) |
| 6 | Phase 6 + 7 (dashboard + docker) |
| 7 | Phase 8 (README/polish) + buffer |

## 14. Known risks & pre-authorized fallbacks

**As it actually went: none of these risks materialized as written** — the ifo schema matched
closely (Phase 1), neither portal blocked scraping (Phase 1b, 49/502 enriched), the mmarco
reranker was fast enough (Phase 2, ~0.2s warm), and OpenAI's structured-output parse API worked
throughout. The one item below that *did* need a real decision (sparse/hybrid via qdrant-client)
was resolved for a different reason than "the API differs" — see Phase 2's "As actually built"
note (client-side BM25 chosen for simplicity, not because the server-side path was broken).

| Risk | Fallback (pre-authorized, logged directly in the relevant phase section above) |
|---|---|
| ifo YAML schema differs from §Phase 1a sketch | adapt parser to actual schema; keep `BenefitRecord` fields |
| Portals block scraping | ship ifo-only corpus (still ≥400 docs); note in README limitations |
| qdrant-client API for sparse/hybrid differs | consult installed client docstrings; keep the 5-function interface of `search.py` unchanged |
| mmarco reranker too slow on CPU in Docker | rerank top 10 instead of 20; if still >5 s, swap to `cross-encoder/ms-marco-MiniLM-L-6-v2` and note the multilingual limitation |
| OpenAI structured-output parse API unavailable | fall back to `response_format={"type":"json_object"}` + Pydantic validation |
| Docker Hub rate limits on M3 (arm64) | all chosen images are multi-arch; retry with `--pull always` off |

## 15. Definition of done

- All 8 phase commits on `main`, pushed to GitHub. ✅ (0, 1a, 1b, 1c, 2–8, all pushed to
  https://github.com/abhirup-ghosh/stille-ansprueche)
- Fresh-clone rehearsal (Phase 7) passes. ✅ (on the third attempt, after three fixes — see
  Phase 7)
- README rubric table claims 18 core + 3 bonus points, and every claim is verifiable in-repo. ✅
  (21 total claimed; full evidence in `docs/README_PROJECT_EVALUATION.md`)
- Total OpenAI cost < $5 (expected < $3), reported in README. ✅ ($0.28 actual, computed exactly)
