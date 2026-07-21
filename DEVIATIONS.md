# Deviations from PLAN.md

- **Phase 0:** `pytest` exits with code 5 ("no tests collected") when the `tests/` directory
  contains only empty placeholder files, which `make` treats as a failure. The `test` Makefile
  target now treats exit code 5 as success. This only applies while test files are empty; once
  Phase 1 adds real tests to `tests/test_corpus.py`, normal pytest exit codes (0 on pass, 1 on
  failure) apply and this special-case is inert.
