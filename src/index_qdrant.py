"""Phase 2: build the Qdrant collection with dense (E5) + sparse (BM25) named vectors."""
import argparse
import json
import uuid

import torch
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src import config

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
DENSE_DIM = 384
BATCH_SIZE = 64
# Qdrant point ids must be an unsigned int or a UUID; our slug-style document ids are
# neither, so every point gets a UUID deterministically derived from its document id
# (the original id is kept in the payload for lookups).
POINT_ID_NAMESPACE = uuid.UUID("c7b7f8f0-5b1a-4b3a-9b3a-9b7b8b7b8b7b")


def _point_id(doc_id: str) -> str:
    return str(uuid.uuid5(POINT_ID_NAMESPACE, doc_id))


def _device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_documents() -> list[dict]:
    with open(config.DATA_DIR / "documents.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def create_collection(client: QdrantClient) -> None:
    if client.collection_exists(config.QDRANT_COLLECTION):
        client.delete_collection(config.QDRANT_COLLECTION)
    client.create_collection(
        collection_name=config.QDRANT_COLLECTION,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF),
        },
    )


def index_documents(client: QdrantClient, documents: list[dict]) -> None:
    dense_model = SentenceTransformer(config.EMBEDDING_MODEL, device=_device())
    sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    for start in tqdm(range(0, len(documents), BATCH_SIZE), desc="indexing"):
        batch = documents[start:start + BATCH_SIZE]
        texts = [doc["text"] for doc in batch]

        dense_vecs = dense_model.encode([f"passage: {t}" for t in texts], batch_size=BATCH_SIZE)
        sparse_vecs = list(sparse_model.embed(texts))

        points = []
        for doc, dense_vec, sparse_vec in zip(batch, dense_vecs, sparse_vecs):
            points.append(models.PointStruct(
                id=_point_id(doc["id"]),
                vector={
                    DENSE_VECTOR_NAME: dense_vec.tolist(),
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
                payload=doc,
            ))
        client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="skip reindexing if point count already matches chunk count")
    args = parser.parse_args()

    documents = load_documents()
    client = QdrantClient(url=config.QDRANT_URL)

    if args.keep and client.collection_exists(config.QDRANT_COLLECTION):
        count = client.count(config.QDRANT_COLLECTION).count
        if count == len(documents):
            print(f"[index_qdrant] Collection already has {count} points matching {len(documents)} documents, skipping (--keep).")
            return

    create_collection(client)
    index_documents(client, documents)

    count = client.count(config.QDRANT_COLLECTION).count
    print(f"[index_qdrant] Indexed {count} points into collection '{config.QDRANT_COLLECTION}' (expected {len(documents)})")


if __name__ == "__main__":
    main()
