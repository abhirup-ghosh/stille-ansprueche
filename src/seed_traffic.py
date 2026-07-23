"""Phase 6: seed ~30 rows of demo traffic (15 conversations + 15 feedback) so the Grafana
dashboard isn't empty for reviewers."""
import json
import random

from langdetect import detect

from src import config, db
from src.eval_rag import judge_relevance
from src.llm import LLMClient
from src.rag import answer

N_QUESTIONS = 15
RANDOM_SEED = 7


def load_ground_truth() -> list[dict]:
    with open(config.DATA_DIR / "ground_truth.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main():
    db.init_db()
    rng = random.Random(RANDOM_SEED)
    ground_truth = load_ground_truth()
    sampled = rng.sample(ground_truth, N_QUESTIONS)

    llm = LLMClient()
    for i, q in enumerate(sampled, 1):
        rag_answer = answer(q["question"])
        try:
            lang = detect(q["question"])
        except Exception:  # noqa: BLE001 — langdetect raises on very short/ambiguous input
            lang = q["lang"]

        retrieved_ids = [s["id"] for s in rag_answer.sources]
        conversation_id = db.insert_conversation(q["question"], lang, retrieved_ids, rag_answer)

        try:
            relevance, _usage = judge_relevance(llm, q["question"], rag_answer.answer)
            db.update_conversation_relevance(conversation_id, relevance.label, relevance.explanation)
        except Exception:  # noqa: BLE001 — judging must never break seeding
            pass

        feedback_value = rng.choice([1, 1, 1, -1])  # skew positive, still some 👎 for the pie chart
        db.insert_feedback(conversation_id, feedback_value)

        print(f"[seed_traffic] {i}/{N_QUESTIONS} seeded (conversation {conversation_id}, feedback {feedback_value:+d})")

    print(f"[seed_traffic] Done: {N_QUESTIONS} conversations + {N_QUESTIONS} feedback rows inserted.")


if __name__ == "__main__":
    main()
