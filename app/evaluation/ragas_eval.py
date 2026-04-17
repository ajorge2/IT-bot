"""
RAGAS evaluation framework — measures four metrics continuously:
  - Faithfulness:       Is the answer grounded in retrieved chunks?
  - Answer Relevancy:   Does it actually answer the question?
  - Context Precision:  Did retrieval surface the right chunks?
  - Context Recall:     Did retrieval miss anything important?

Usage:
    python -m app.evaluation.ragas_eval --golden tests/golden_set.json

Run after every ingestion pipeline change or model swap.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def run_evaluation(golden_path: str | Path) -> dict[str, float]:
    """
    Run RAGAS evaluation against a golden test set.

    The golden set is a JSON list of:
        {
            "question": "...",
            "ground_truth": "...",         # expected answer
            "ground_truth_context": ["..."] # expected source passages (optional)
        }

    Returns a dict of metric name → average score.
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from app.retrieval.pipeline import retrieve
    from app.confidence.handler import generate_answer

    golden_set = json.loads(Path(golden_path).read_text())
    log.info("RAGAS: evaluating %d golden questions", len(golden_set))

    questions, answers, contexts, ground_truths = [], [], [], []

    for item in golden_set:
        q = item["question"]
        chunks, top_sim = retrieve(q)
        response = generate_answer(q, chunks, top_sim)

        questions.append(q)
        answers.append(response.answer)
        contexts.append([c["content"] for c in chunks])
        ground_truths.append(item["ground_truth"])

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )

    scores = {
        "faithfulness": result["faithfulness"],
        "answer_relevancy": result["answer_relevancy"],
        "context_precision": result["context_precision"],
        "context_recall": result["context_recall"],
    }

    print("\n=== RAGAS Evaluation Results ===")
    for metric, score in scores.items():
        print(f"  {metric:<22} {score:.4f}")
    print("================================\n")

    return scores


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation")
    parser.add_argument(
        "--golden",
        default="tests/golden_set.json",
        help="Path to the golden test set JSON file",
    )
    args = parser.parse_args()
    run_evaluation(args.golden)
