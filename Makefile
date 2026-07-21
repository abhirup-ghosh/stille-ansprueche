.PHONY: setup ingest index ground-truth eval-retrieval eval-rag app test up down seed index-docker

setup:
	python3.11 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

ingest:
	. .venv/bin/activate && python -m src.ingest_ifo
	. .venv/bin/activate && python -m src.enrich_portals
	. .venv/bin/activate && python -m src.build_corpus

index:
	. .venv/bin/activate && python -m src.index_qdrant

index-docker:
	docker compose run --rm app python -m src.index_qdrant

ground-truth:
	. .venv/bin/activate && python -m src.generate_ground_truth

eval-retrieval:
	. .venv/bin/activate && python -m src.eval_retrieval

eval-rag:
	. .venv/bin/activate && python -m src.eval_rag

app:
	. .venv/bin/activate && streamlit run app/app.py

seed:
	. .venv/bin/activate && python -m src.seed_traffic

test:
	. .venv/bin/activate && pytest; code=$$?; [ $$code -eq 5 ] && exit 0 || exit $$code

up:
	docker compose up -d

down:
	docker compose down
