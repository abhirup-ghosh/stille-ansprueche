"""Phase 4b: evaluate the 3 RAG prompt variants with relevance + faithfulness LLM judges."""
import csv
import json
import random
import re
from typing import Literal

from pydantic import BaseModel
from tqdm import tqdm

from src import config
from src.llm import LLMClient
from src.rag import PROMPT_VARIANTS, answer

SAMPLE_SIZE_DE = 80
SAMPLE_SIZE_EN = 20
RANDOM_SEED = 42
RESULTS_PATH = config.DATA_DIR / "eval" / "rag_results.csv"

RELEVANCE_JUDGE_SYSTEM = (
    "You are an expert evaluator judging whether an AI assistant's answer is relevant to the "
    "user's question. Answer only with the requested JSON."
)
RELEVANCE_JUDGE_USER_TEMPLATE = """\
QUESTION:
{question}

ANSWER:
{answer}

Classify how relevant the ANSWER is to the QUESTION and give a one-sentence explanation.
"""

FAITHFULNESS_JUDGE_SYSTEM = (
    "You are an expert evaluator judging whether an AI assistant's answer is faithful to "
    "(fully supported by) the provided context, with no invented amounts, deadlines, or "
    "eligibility conditions. Answer only with the requested JSON."
)
FAITHFULNESS_JUDGE_USER_TEMPLATE = """\
CONTEXT:
{context}

ANSWER:
{answer}

Does the ANSWER assert any entitlement, monetary amount, deadline, or eligibility condition
that is NOT present in the CONTEXT? Classify the answer's faithfulness to the context and give
a one-sentence explanation.
"""


class RelevanceJudgment(BaseModel):
    label: Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
    explanation: str


class FaithfulnessJudgment(BaseModel):
    label: Literal["FAITHFUL", "MINOR_UNSUPPORTED", "HALLUCINATED"]
    explanation: str


def load_ground_truth() -> list[dict]:
    with open(config.DATA_DIR / "ground_truth.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def sample_questions(ground_truth: list[dict]) -> list[dict]:
    rng = random.Random(RANDOM_SEED)
    de = [q for q in ground_truth if q["lang"] == "de"]
    en = [q for q in ground_truth if q["lang"] == "en"]
    return rng.sample(de, SAMPLE_SIZE_DE) + rng.sample(en, SAMPLE_SIZE_EN)


def mean_sentence_length(text: str) -> float:
    sentences = [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def judge_relevance(llm: LLMClient, question: str, answer_text: str) -> tuple[RelevanceJudgment, dict]:
    messages = [
        {"role": "system", "content": RELEVANCE_JUDGE_SYSTEM},
        {"role": "user", "content": RELEVANCE_JUDGE_USER_TEMPLATE.format(question=question, answer=answer_text)},
    ]
    return llm.chat(messages, temperature=0.0, response_model=RelevanceJudgment)


def judge_faithfulness(llm: LLMClient, context: str, answer_text: str) -> tuple[FaithfulnessJudgment, dict]:
    messages = [
        {"role": "system", "content": FAITHFULNESS_JUDGE_SYSTEM},
        {"role": "user", "content": FAITHFULNESS_JUDGE_USER_TEMPLATE.format(context=context, answer=answer_text)},
    ]
    return llm.chat(messages, temperature=0.0, response_model=FaithfulnessJudgment)


def main():
    ground_truth = load_ground_truth()
    sampled = sample_questions(ground_truth)
    print(f"[eval_rag] Sampled {len(sampled)} questions ({SAMPLE_SIZE_DE} de / {SAMPLE_SIZE_EN} en)")

    llm = LLMClient()
    rows = []
    for q in tqdm(sampled, desc="questions"):
        for variant in PROMPT_VARIANTS:
            rag_answer = answer(q["question"], prompt_variant=variant)
            context = "\n\n".join(f"{s['name']}: {s['legal_norm']}" for s in rag_answer.sources)

            relevance, relevance_usage = judge_relevance(llm, q["question"], rag_answer.answer)
            faithfulness, faithfulness_usage = judge_faithfulness(llm, context, rag_answer.answer)

            row_cost = rag_answer.cost_usd + relevance_usage["cost_usd"] + faithfulness_usage["cost_usd"]
            rows.append({
                "question": q["question"],
                "lang": q["lang"],
                "doc_id": q["doc_id"],
                "variant": variant,
                "answer": rag_answer.answer,
                "relevance_label": relevance.label,
                "relevance_explanation": relevance.explanation,
                "faithfulness_label": faithfulness.label,
                "faithfulness_explanation": faithfulness.explanation,
                "mean_sentence_len": mean_sentence_length(rag_answer.answer),
                "prompt_tokens": rag_answer.prompt_tokens,
                "completion_tokens": rag_answer.completion_tokens,
                "cost_usd": row_cost,
                "response_time_s": rag_answer.response_time_s,
            })

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[eval_rag] Wrote {RESULTS_PATH} ({len(rows)} rows)")

    aggregates = []
    for variant in PROMPT_VARIANTS:
        variant_rows = [r for r in rows if r["variant"] == variant]
        n = len(variant_rows)
        pct_relevant = sum(1 for r in variant_rows if r["relevance_label"] == "RELEVANT") / n
        pct_faithful = sum(1 for r in variant_rows if r["faithfulness_label"] == "FAITHFUL") / n
        mean_sent_len = sum(r["mean_sentence_len"] for r in variant_rows) / n
        mean_cost = sum(r["cost_usd"] for r in variant_rows) / n
        mean_time = sum(r["response_time_s"] for r in variant_rows) / n
        aggregates.append({
            "variant": variant,
            "pct_relevant": pct_relevant,
            "pct_faithful": pct_faithful,
            "mean_sentence_len": mean_sent_len,
            "mean_cost_usd": mean_cost,
            "mean_time_s": mean_time,
        })

    print("\n| variant | %relevant | %faithful | mean_sentence_len | mean_cost_usd | mean_time_s |")
    print("|---|---|---|---|---|---|")
    for a in aggregates:
        print(f"| {a['variant']} | {a['pct_relevant']:.1%} | {a['pct_faithful']:.1%} | "
              f"{a['mean_sentence_len']:.1f} | {a['mean_cost_usd']:.5f} | {a['mean_time_s']:.2f} |")

    winner = max(aggregates, key=lambda a: (a["pct_faithful"], a["pct_relevant"]))
    print(f"\n[eval_rag] Winner (highest %faithful, tie-broken by %relevant): {winner['variant']}")


if __name__ == "__main__":
    main()
