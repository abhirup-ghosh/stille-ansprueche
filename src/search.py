"""Phase 2: text / vector / hybrid / rerank / query-rewrite search over the Qdrant collection."""
import torch
from fastembed import SparseTextEmbedding
from langdetect import detect
from qdrant_client import QdrantClient, models
from sentence_transformers import CrossEncoder, SentenceTransformer

from src import config
from src.llm import LLMClient
from src.index_qdrant import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME

HYBRID_PREFETCH_LIMIT = 20

_client: QdrantClient | None = None
_dense_model: SentenceTransformer | None = None
_sparse_model: SparseTextEmbedding | None = None
_reranker: CrossEncoder | None = None
_llm_client: LLMClient | None = None


def _device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=config.QDRANT_URL)
    return _client


def _get_dense_model() -> SentenceTransformer:
    global _dense_model
    if _dense_model is None:
        _dense_model = SentenceTransformer(config.EMBEDDING_MODEL, device=_device())
    return _dense_model


def _get_sparse_model() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _sparse_model


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(config.RERANKER_MODEL, device=_device())
    return _reranker


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def _dense_vector(text: str, prefix: str) -> list[float]:
    return _get_dense_model().encode(f"{prefix}{text}").tolist()


def _sparse_vector(text: str) -> models.SparseVector:
    embedding = next(_get_sparse_model().embed([text]))
    return models.SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())


def _points_to_payloads(points) -> list[dict]:
    return [p.payload for p in points]


def search_text(query: str, k: int = 10) -> list[dict]:
    """BM25 sparse-only search."""
    result = _get_client().query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=_sparse_vector(query),
        using=SPARSE_VECTOR_NAME,
        limit=k,
    )
    return _points_to_payloads(result.points)


def search_vector(query: str, k: int = 10) -> list[dict]:
    """Dense-only search (E5 requires the "query: " prefix)."""
    result = _get_client().query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=_dense_vector(query, "query: "),
        using=DENSE_VECTOR_NAME,
        limit=k,
    )
    return _points_to_payloads(result.points)


def search_hybrid(query: str, k: int = 10) -> list[dict]:
    """Hybrid: dense + BM25 prefetch (top 20 each), fused with RRF."""
    prefetch = [
        models.Prefetch(query=_dense_vector(query, "query: "), using=DENSE_VECTOR_NAME, limit=HYBRID_PREFETCH_LIMIT),
        models.Prefetch(query=_sparse_vector(query), using=SPARSE_VECTOR_NAME, limit=HYBRID_PREFETCH_LIMIT),
    ]
    result = _get_client().query_points(
        collection_name=config.QDRANT_COLLECTION,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
    )
    return _points_to_payloads(result.points)


def search_hybrid_rerank(query: str, k: int = 10) -> list[dict]:
    """Hybrid top 20 -> CrossEncoder rerank -> top k."""
    candidates = search_hybrid(query, k=HYBRID_PREFETCH_LIMIT)
    if not candidates:
        return []
    pairs = [(query, doc["text"]) for doc in candidates]
    scores = _get_reranker().predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [doc for doc, _ in ranked[:k]]


REWRITE_SYSTEM_PROMPT = (
    "Du hilfst dabei, Suchanfragen fuer eine Datenbank deutscher Sozialleistungen zu "
    "verbessern. Antworte NUR mit der umformulierten Suchanfrage, ohne Erklaerung."
)

REWRITE_USER_PROMPT_NON_GERMAN = """\
Uebersetze die folgende Anfrage einer Person, die nach Sozialleistungen sucht, ins Deutsche \
und formuliere sie als EINE optimierte deutsche Suchanfrage um. Ergaenze 2-4 passende \
Amtsdeutsch-Begriffe/offizielle Leistungsbezeichnungen, die in einer Sozialleistungs-Datenbank \
vorkommen koennten (z.B. Rechtsnormen, offizielle Leistungsnamen). Antworte nur mit der \
Suchanfrage selbst, in einer Zeile.

ANFRAGE: {query}
"""

REWRITE_USER_PROMPT_GERMAN = """\
Formuliere die folgende Anfrage einer Person, die nach Sozialleistungen sucht, in EINE \
optimierte deutsche Suchanfrage um. Ergaenze 2-4 passende Amtsdeutsch-Begriffe/offizielle \
Leistungsbezeichnungen, die in einer Sozialleistungs-Datenbank vorkommen koennten (z.B. \
Rechtsnormen, offizielle Leistungsnamen). Antworte nur mit der Suchanfrage selbst, in einer \
Zeile.

ANFRAGE: {query}
"""


def rewrite_query(query: str) -> str:
    """LLM query rewrite: translate to German if needed (langdetect-gated), expand with
    Amtsdeutsch terms."""
    try:
        is_german = detect(query) == "de"
    except Exception:  # noqa: BLE001 — langdetect raises on very short/ambiguous input
        is_german = False

    template = REWRITE_USER_PROMPT_GERMAN if is_german else REWRITE_USER_PROMPT_NON_GERMAN
    llm = _get_llm_client()
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": template.format(query=query)},
    ]
    rewritten, _usage = llm.chat(messages, temperature=0.0)
    return rewritten.strip()


def search_hybrid_rewritten(query: str, k: int = 10) -> list[dict]:
    rewritten = rewrite_query(query)
    return search_hybrid(rewritten, k=k)


# Phase 3 retrieval evaluation winner (highest MRR@5 over all 1000 ground-truth questions,
# de+en): plain dense vector search, MRR@5=0.173 vs. 0.164 for hybrid_rerank, the runner-up.
# See data/eval/retrieval_results.csv and the README's "Retrieval evaluation" section for the
# full comparison and interpretation.
search_best = search_vector
