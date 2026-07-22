"""Phase 3b: evaluate 5 retrieval strategies (Hit Rate@k, MRR@k), overall and by language."""
import csv
import json
import re

from tqdm import tqdm

from src import config
from src import search as search_module

STRATEGIES = {
    "text": search_module.search_text,
    "vector": search_module.search_vector,
    "hybrid": search_module.search_hybrid,
    "hybrid_rerank": search_module.search_hybrid_rerank,
    "hybrid_rewritten": search_module.search_hybrid_rewritten,
}

K_VALUES = [5, 10]
MAX_K = max(K_VALUES)
RESULTS_PATH = config.DATA_DIR / "eval" / "retrieval_results.csv"

_CHUNK_SUFFIX_RE = re.compile(r"--\d+$")


def strip_chunk_suffix(doc_id: str) -> str:
    return _CHUNK_SUFFIX_RE.sub("", doc_id)


def load_ground_truth() -> list[dict]:
    with open(config.DATA_DIR / "ground_truth.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _rank_result_ids(fn, questions: list[dict]) -> list[list[str]]:
    """Run the search function once per question; return each question's ranked, chunk-suffix-stripped result ids."""
    all_result_ids = []
    for q in questions:
        results = fn(q["question"], k=MAX_K)
        all_result_ids.append([strip_chunk_suffix(r["id"]) for r in results])
    return all_result_ids


def _metrics_for_subset(questions: list[dict], result_ids: list[list[str]]) -> dict[int, dict[str, float]]:
    hits = {k: 0 for k in K_VALUES}
    rr_sums = {k: 0.0 for k in K_VALUES}

    for q, ids in zip(questions, result_ids):
        for k in K_VALUES:
            topk = ids[:k]
            if q["doc_id"] in topk:
                hits[k] += 1
                rank = topk.index(q["doc_id"]) + 1
                rr_sums[k] += 1.0 / rank

    n = len(questions)
    return {k: {"hit_rate": hits[k] / n, "mrr": rr_sums[k] / n} for k in K_VALUES}


def main():
    ground_truth = load_ground_truth()

    rows = []
    for strategy_name, fn in STRATEGIES.items():
        print(f"[eval_retrieval] Running '{strategy_name}' over all {len(ground_truth)} questions...")
        result_ids = _rank_result_ids(fn, tqdm(ground_truth, desc=strategy_name))

        by_lang = {
            "de": ([q for q in ground_truth if q["lang"] == "de"], [r for q, r in zip(ground_truth, result_ids) if q["lang"] == "de"]),
            "en": ([q for q in ground_truth if q["lang"] == "en"], [r for q, r in zip(ground_truth, result_ids) if q["lang"] == "en"]),
            "all": (ground_truth, result_ids),
        }
        for lang, (questions, ids_subset) in by_lang.items():
            metrics = _metrics_for_subset(questions, ids_subset)
            rows.append({
                "strategy": strategy_name,
                "lang": lang,
                "hit_rate@5": metrics[5]["hit_rate"],
                "mrr@5": metrics[5]["mrr"],
                "hit_rate@10": metrics[10]["hit_rate"],
                "mrr@10": metrics[10]["mrr"],
                "n_questions": len(questions),
            })

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["strategy", "lang", "hit_rate@5", "mrr@5", "hit_rate@10", "mrr@10", "n_questions"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[eval_retrieval] Wrote {RESULTS_PATH}\n")
    print("| strategy | lang | hit_rate@5 | mrr@5 | hit_rate@10 | mrr@10 | n_questions |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['strategy']} | {row['lang']} | {row['hit_rate@5']:.3f} | {row['mrr@5']:.3f} | "
              f"{row['hit_rate@10']:.3f} | {row['mrr@10']:.3f} | {row['n_questions']} |")

    best_row = max((r for r in rows if r["lang"] == "all"), key=lambda r: r["mrr@5"])
    print(f"\n[eval_retrieval] Best strategy overall (highest MRR@5, all languages): {best_row['strategy']} "
          f"(MRR@5={best_row['mrr@5']:.3f})")


if __name__ == "__main__":
    main()
