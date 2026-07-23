"""Phase 5a: Postgres schema + typed insert/select helpers for conversations and feedback."""
import uuid
from contextlib import contextmanager

import psycopg2

from src import config
from src.rag import RagAnswer

CREATE_CONVERSATIONS_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    lang TEXT,
    prompt_variant TEXT,
    model TEXT,
    retrieved_ids TEXT[],
    relevance TEXT,
    relevance_explanation TEXT,
    prompt_tokens INT,
    completion_tokens INT,
    cost_usd NUMERIC(10,6),
    response_time_s NUMERIC(8,3)
);
"""

CREATE_FEEDBACK_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    value INT NOT NULL CHECK (value IN (-1, 1))
);
"""


@contextmanager
def _connection():
    conn = psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_CONVERSATIONS_SQL)
        cur.execute(CREATE_FEEDBACK_SQL)
        conn.commit()


def insert_conversation(question: str, lang: str, retrieved_ids: list[str], rag_answer: RagAnswer) -> str:
    conversation_id = str(uuid.uuid4())
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations
                (id, question, answer, lang, prompt_variant, model, retrieved_ids,
                 prompt_tokens, completion_tokens, cost_usd, response_time_s)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                conversation_id, question, rag_answer.answer, lang, rag_answer.prompt_variant,
                rag_answer.model, retrieved_ids, rag_answer.prompt_tokens,
                rag_answer.completion_tokens, rag_answer.cost_usd, rag_answer.response_time_s,
            ),
        )
        conn.commit()
    return conversation_id


def update_conversation_relevance(conversation_id: str, relevance: str, explanation: str) -> None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE conversations SET relevance = %s, relevance_explanation = %s WHERE id = %s",
            (relevance, explanation, conversation_id),
        )
        conn.commit()


def insert_feedback(conversation_id: str, value: int) -> None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (conversation_id, value) VALUES (%s, %s)",
            (conversation_id, value),
        )
        conn.commit()
