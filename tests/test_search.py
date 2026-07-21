import pytest
from qdrant_client import QdrantClient

from src import config


def _qdrant_is_up() -> bool:
    try:
        QdrantClient(url=config.QDRANT_URL).get_collections()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _qdrant_is_up(), reason="Qdrant is not reachable")


def test_search_hybrid_finds_wohngeld_for_rent_subsidy_query():
    from src.search import search_hybrid

    results = search_hybrid("Zuschuss zur Miete für Familien mit geringem Einkommen", k=5)
    assert any("Wohngeld" in r["name"] for r in results)
