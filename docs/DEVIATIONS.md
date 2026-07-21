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
