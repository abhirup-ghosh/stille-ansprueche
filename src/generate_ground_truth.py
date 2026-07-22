"""Phase 3a: generate ~1000 realistic user questions (200 docs x 5) as retrieval ground truth."""
import json
import random

from pydantic import BaseModel
from tqdm import tqdm

from src import config
from src.llm import LLMClient

SAMPLE_SIZE = 200
RANDOM_SEED = 42
DOC_TEXT_TRUNCATE_CHARS = 2000
GROUND_TRUTH_PATH = config.DATA_DIR / "ground_truth.jsonl"

SYSTEM_PROMPT = "You generate realistic user questions for evaluating a retrieval system. Answer only with the requested JSON."

USER_PROMPT_TEMPLATE = """\
Du siehst den Eintrag einer deutschen Sozialleistung. Formuliere 4 realistische Fragen auf
Deutsch, die eine betroffene Person stellen würde, OHNE den offiziellen Namen der Leistung
zu verwenden. Die Fragen sollen Alltagssprache verwenden und die Lebenslage beschreiben
(z.B. "Ich bin alleinerziehend und arbeite Teilzeit..."). Formuliere zusätzlich 1 Frage auf
Englisch im gleichen Stil.

LEISTUNG:
{document_text}
"""


class GeneratedQuestions(BaseModel):
    questions_de: list[str]
    question_en: str


def load_documents() -> list[dict]:
    with open(config.DATA_DIR / "documents.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def sample_documents(documents: list[dict]) -> list[dict]:
    enriched = [d for d in documents if d["enriched"]]
    ifo_only = [d for d in documents if not d["enriched"]]

    if len(enriched) >= SAMPLE_SIZE:
        rng = random.Random(RANDOM_SEED)
        return rng.sample(enriched, SAMPLE_SIZE)

    remaining = SAMPLE_SIZE - len(enriched)
    rng = random.Random(RANDOM_SEED)
    sampled_ifo_only = rng.sample(ifo_only, min(remaining, len(ifo_only)))
    return enriched + sampled_ifo_only


def generate_questions_for_document(llm: LLMClient, document: dict) -> GeneratedQuestions:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(document_text=document["text"][:DOC_TEXT_TRUNCATE_CHARS])},
    ]
    parsed, _usage = llm.chat(messages, temperature=0.7, response_model=GeneratedQuestions)
    return parsed


def main():
    documents = load_documents()
    sampled = sample_documents(documents)
    print(f"[generate_ground_truth] Sampled {len(sampled)} documents ({sum(d['enriched'] for d in sampled)} enriched)")

    llm = LLMClient()
    rows = []
    for doc in tqdm(sampled, desc="generating questions"):
        questions = generate_questions_for_document(llm, doc)
        for q in questions.questions_de:
            rows.append({"question": q, "lang": "de", "doc_id": doc["id"]})
        rows.append({"question": questions.question_en, "lang": "en", "doc_id": doc["id"]})

    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    n_de = sum(1 for r in rows if r["lang"] == "de")
    n_en = sum(1 for r in rows if r["lang"] == "en")
    print(f"[generate_ground_truth] Wrote {len(rows)} rows ({n_de} de, {n_en} en) to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
