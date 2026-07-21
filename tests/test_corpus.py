import json

from src import config
from src.build_corpus import DOCUMENTS_PATH, Document, chunk_text
from src.ingest_ifo import PARSED_PATH, BenefitRecord

IFO_ONLY_MIN_RECORDS = 400
CORPUS_MIN_DOCUMENTS = 400


def _load_ifo_records() -> list[BenefitRecord]:
    with open(PARSED_PATH, encoding="utf-8") as f:
        return [BenefitRecord.model_validate_json(line) for line in f]


def test_ifo_parsed_records_meet_minimum_count():
    records = _load_ifo_records()
    assert len(records) >= IFO_ONLY_MIN_RECORDS


def test_ifo_parsed_records_have_required_fields():
    records = _load_ifo_records()
    for rec in records:
        assert rec.name.strip()
        assert rec.legal_norm.strip()
        assert rec.law_book.strip()
        assert len(rec.target_groups) >= 1


def test_ifo_parsed_records_have_unique_ids():
    records = _load_ifo_records()
    ids = [rec.id for rec in records]
    assert len(ids) == len(set(ids))


def _load_documents() -> list[Document]:
    with open(DOCUMENTS_PATH, encoding="utf-8") as f:
        return [Document.model_validate_json(line) for line in f]


def test_documents_meet_minimum_count():
    documents = _load_documents()
    assert len(documents) >= CORPUS_MIN_DOCUMENTS


def test_documents_have_no_empty_text():
    documents = _load_documents()
    for doc in documents:
        assert doc.text.strip()


def test_documents_have_unique_ids():
    documents = _load_documents()
    ids = [d.id for d in documents]
    assert len(ids) == len(set(ids))


def test_chunk_text_short_text_is_single_chunk():
    assert chunk_text("Kurzer Text.") == ["Kurzer Text."]


def test_chunk_text_long_text_splits_with_overlap():
    sentence = "Dies ist ein Beispielsatz mit ausreichend Zeichen fuer den Test. "
    long_text = sentence * 200  # well over the 6000-char threshold
    chunks = chunk_text(long_text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 3300  # chunk size (3000) + a bit of overlap/sentence slack
