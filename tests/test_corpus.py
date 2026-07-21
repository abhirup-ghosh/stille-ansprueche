import json

from src import config
from src.ingest_ifo import PARSED_PATH, BenefitRecord

IFO_ONLY_MIN_RECORDS = 400


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
