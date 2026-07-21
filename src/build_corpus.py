"""Phase 1c: join ifo records + portal enrichment into the final corpus, data/documents.jsonl.

One Document per benefit (chunked further if the composed text exceeds 6000 chars).
"""
import json
import re
import statistics
from pathlib import Path

from pydantic import BaseModel

from src import config

IFO_PARSED_PATH = config.DATA_DIR / "ifo" / "benefits_parsed.jsonl"
ENRICHMENT_PATH = config.DATA_DIR / "ifo" / "enrichment.jsonl"
DOCUMENTS_PATH = config.DATA_DIR / "documents.jsonl"

ENRICHMENT_TRUNCATE_CHARS = 4000
CHUNK_THRESHOLD_CHARS = 6000
CHUNK_SIZE_CHARS = 3000
CHUNK_OVERLAP_CHARS = 300


class Document(BaseModel):
    id: str
    name: str
    law_book: str
    legal_norm: str
    category: str
    target_groups: list[str]
    topic_fields: list[str]
    text: str
    official_url: str | None
    enriched: bool


def load_enrichment_by_benefit_id() -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    if ENRICHMENT_PATH.exists():
        with open(ENRICHMENT_PATH, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                by_id[row["benefit_id"]] = row
    return by_id


def compose_text(benefit: dict, enrichment: dict | None) -> str:
    text = (
        f"{benefit['name']}. {benefit['description']} "
        f"Rechtsgrundlage: {benefit['legal_norm']}. "
        f"Zielgruppen: {', '.join(benefit['target_groups'])}. "
        f"Themen: {', '.join(benefit['topic_fields'])}."
    )
    if enrichment is not None:
        text += "\n\n" + enrichment["text"][:ENRICHMENT_TRUNCATE_CHARS]
    return text


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_THRESHOLD_CHARS:
        return [text]

    sentences = _SENTENCE_SPLIT_RE.split(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > CHUNK_SIZE_CHARS and current:
            chunks.append(current)
            overlap = current[-CHUNK_OVERLAP_CHARS:]
            current = f"{overlap} {sentence}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_documents(benefits: list[dict], enrichment_by_id: dict[str, dict]) -> list[Document]:
    documents: list[Document] = []
    for benefit in benefits:
        enrichment = enrichment_by_id.get(benefit["id"])
        text = compose_text(benefit, enrichment)
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            chunk_id = benefit["id"] if len(chunks) == 1 else f"{benefit['id']}--{i}"
            documents.append(Document(
                id=chunk_id,
                name=benefit["name"],
                law_book=benefit["law_book"],
                legal_norm=benefit["legal_norm"],
                category=benefit["category"],
                target_groups=benefit["target_groups"],
                topic_fields=benefit["topic_fields"],
                text=chunk,
                official_url=enrichment["url"] if enrichment else None,
                enriched=enrichment is not None,
            ))
    return documents


def main():
    with open(IFO_PARSED_PATH, encoding="utf-8") as f:
        benefits = [json.loads(line) for line in f]
    enrichment_by_id = load_enrichment_by_benefit_id()

    documents = build_documents(benefits, enrichment_by_id)

    ids = [d.id for d in documents]
    assert len(ids) == len(set(ids)), "duplicate document ids produced"

    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DOCUMENTS_PATH, "w", encoding="utf-8") as f:
        for doc in documents:
            f.write(doc.model_dump_json() + "\n")

    n_docs = len(benefits)
    n_chunks = len(documents)
    n_enriched = sum(1 for b in benefits if b["id"] in enrichment_by_id)
    median_len = statistics.median(len(d.text) for d in documents)

    print(f"[build_corpus] Benefits (parent docs): {n_docs}")
    print(f"[build_corpus] Total chunks written: {n_chunks}")
    print(f"[build_corpus] Median chunk text length: {median_len:.0f} chars")
    print(f"[build_corpus] Enriched: {n_enriched}/{n_docs} ({100 * n_enriched / n_docs:.1f}%)")
    print(f"[build_corpus] Wrote {DOCUMENTS_PATH}")


if __name__ == "__main__":
    main()
